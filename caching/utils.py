from hashlib import md5
from json import dumps
from django.core.cache import cache


class CacheUtils:
    @staticmethod
    async def get_model_hash(view):
        """Generates a hash based on the serializer's model name."""
        serializer_class = view.get_serializer_class()
        model_name = serializer_class.Meta.model.__name__.lower()
        return md5(model_name.encode()).hexdigest()

    @staticmethod
    async def get_user_version(user_id):
        """Retrieves or initializes the cache version for a specific user."""
        version = await cache.aget(f"u_ver:{user_id}")
        if version is None:
            version = 1
            await cache.aset(f"u_ver:{user_id}", version, timeout=None)
        return version

    @staticmethod
    async def incr_user_version(user_id):
        """Increments the user's cache version to invalidate list caches."""
        try:
            await cache.aincr(f"u_ver:{user_id}")
        except (ValueError, TypeError):
            await cache.aset(f"u_ver:{user_id}", 2, timeout=None)

    @classmethod
    async def generate_list_key(cls, request):
        """
        Generates a stable, sorted cache key for list views.
        """
        view = request.parser_context.get('view')
        model_hash = await cls.get_model_hash(view)
        query_params = dict(request.query_params.items())
        sorted_params = sorted(query_params.items())
        params_hash = md5(dumps(sorted_params).encode()).hexdigest()
        user_id = request.user.id if request.user.is_authenticated else "anonymous"
        version = "v0"
        if user_id != "anonymous":
            version = f"v{await cls.get_user_version(user_id)}"
        return f"list:{model_hash}:{params_hash}:{version}"


def preprocess_async_actions(endpoints, **kwargs):
    """
    Preprocessing hook for drf-spectacular using Python 3.10+ match statement.
    """
    for (path, path_regex, method, callback) in endpoints:
        if hasattr(callback, 'actions'):
            actions = callback.actions
            for http_method, action in actions.items():
                match action:
                    case 'alist':
                        actions[http_method] = 'list'
                    case 'aretrieve':
                        actions[http_method] = 'retrieve'
                    case 'acreate':
                        actions[http_method] = 'create'
                    case 'aupdate':
                        actions[http_method] = 'update'
                    case 'partial_aupdate':
                        actions[http_method] = 'partial_update'
                    case 'adestroy':
                        actions[http_method] = 'destroy'
    return endpoints
