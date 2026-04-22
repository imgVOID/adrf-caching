import asyncio
from hashlib import md5
from json import dumps
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

DEFAULTS = {
    "TTL_OBJECT": 600,
    "TTL_LIST": 300,
    "TTL_USER_VER": 86400,
    "PREFIX": "adrf_caching",
}

class LibSettings:
    def __init__(self):
        self.user_settings = getattr(settings, "ADRF_CACHING_SETTINGS", {})

    def __getattr__(self, name):
        if name not in DEFAULTS:
            raise AttributeError(f"'{name}' does not exist in ADRF_CACHE_SETTINGS.")

        value = self.user_settings.get(name, DEFAULTS[name])

        if name.startswith("TTL_") and not isinstance(value, int):
            raise ImproperlyConfigured(
                f"Error ADRF_CACHE_SETTINGS: {name} must be int, not {type(value).__name__}."
            )
        return value

lib_settings = LibSettings()


class CacheUtils:
    @staticmethod
    async def get_model_hash(view):
        """Generates a hash based on the serializer's model name."""
        serializer_class = view.get_serializer_class()
        model_name = serializer_class.Meta.model.__name__.lower()
        return md5(f"{lib_settings.PREFIX}:{model_name}".encode()).hexdigest()

    @staticmethod
    async def get_user_version(user_id):
        """Retrieves or initializes the cache version for a specific user."""
        cache_key = f"u_ver:{user_id}"
        version = await cache.aget(cache_key)
        if version is None:
            version = 1
            await cache.aset(cache_key, version, timeout=lib_settings.TTL_USER_VER)
        return version

    @staticmethod
    async def incr_user_version(user_id):
        """Increments the user's cache version to invalidate list caches."""
        cache_key = f"u_ver:{user_id}"
        try:
            await cache.aincr(cache_key)
            await cache.atouch(cache_key, timeout=lib_settings.TTL_USER_VER)
        except (ValueError, TypeError):
            await cache.aset(cache_key, 2, timeout=lib_settings.TTL_USER_VER)

    @classmethod
    async def generate_list_key(cls, request, view=None):
        """Generates a stable, sorted, user-specific cache key for list views."""
        view = view or getattr(request, 'parser_context', {}).get('view')
        if not view:
            raise AttributeError(
                "Could not determine 'view' from request. "
                "Ensure the request is processed by a DRF View or pass 'view' explicitly."
            )
        model_hash = await cls.get_model_hash(view)
        params = getattr(request, 'query_params', request.GET)
        query_params = dict(params.items())
        sorted_params = sorted(query_params.items())
        params_hash = md5(dumps(sorted_params).encode()).hexdigest()
        user = getattr(request, 'user', None)
        user_id = user.id if user and user.is_authenticated else "anonymous"
        if user_id != "anonymous":
            version = await cls.get_user_version(user_id)
            return f"list:{model_hash}:{user_id}:v{version}:{params_hash}"
        return f"list:{model_hash}:anon:v0:{params_hash}"

    @staticmethod
    async def invalidate_list_cache(request, view, instance=None):
        """Invalidates cache for the request user and any specified owners."""
        target_ids = set()
        
        # 1. Add current user
        if request and getattr(request, 'user', None) and request.user.is_authenticated:
            target_ids.add(request.user.id)
            
        # 2. Add extra owners if defined in view.invalidate_fields
        invalidate_fields = getattr(view, 'invalidate_fields', [])
        if instance and invalidate_fields:
            for field in invalidate_fields:
                if not hasattr(instance, field):
                    raise ImproperlyConfigured(
                        f"Field '{field}' not found in {instance.__class__.__name__}. "
                        f"Check your 'invalidate_fields' in the ViewSet."
                    )
                u_id = getattr(instance, field, None)
                if u_id:
                    target_ids.add(u_id)
                    
        # 3. Fire parallel invalidation
        if target_ids:
            tasks = [CacheUtils.incr_user_version(u_id) for u_id in target_ids]
            await asyncio.gather(*tasks)
