from hashlib import md5
from adrf import mixins
from adrf.viewsets import GenericViewSet
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response

# --- Cache Utility Class ---

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

    @staticmethod
    async def generate_list_key(request, is_personal=False):
        """Generates a cache key for list views, including versioning for personal data."""
        path_hash = md5(request.get_full_path().encode()).hexdigest()
        if request.user.is_authenticated:
            version = await CacheUtils.get_user_version(request.user.id)
            user_hash = md5(str(request.user.id).encode()).hexdigest()
            return f"list:{path_hash}:{user_hash}:v{version}"
        return f"list:g:{path_hash}"

# --- Mixins ---

class ListModelMixin(mixins.ListModelMixin):
    async def alist(self, request, *args, **kwargs):
        cache_key = await CacheUtils.generate_list_key(request)
        if (cached := await cache.aget(cache_key)):
            return Response(cached, status=status.HTTP_200_OK)
        queryset = await self.afilter_queryset(self.get_queryset())
        page = await self.apaginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        data = await serializer.adata
        if page is not None:
            paginated_response = await self.get_apaginated_response(data)
            data = paginated_response.data
            
        await cache.aset(cache_key, data, timeout=300)
        return Response(data, status=status.HTTP_200_OK)


class RetrieveModelMixin(mixins.RetrieveModelMixin):
    async def aretrieve(self, request, *args, **kwargs):
        m_hash = await CacheUtils.get_model_hash(self)
        cache_key = f"obj:{m_hash}:{self.kwargs['pk']}"
        if (cached := await cache.aget(cache_key)):
            return Response(cached, status=status.HTTP_200_OK)
        instance = await self.aget_object()
        serializer = self.get_serializer(instance)
        data = await serializer.adata
        await cache.aset(cache_key, data, timeout=600)
        return Response(data, status=status.HTTP_200_OK)


class CreateModelMixin(mixins.CreateModelMixin):
    async def acreate(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        await serializer.ais_valid(raise_exception=True)
        await self.perform_acreate(serializer)
        data = await serializer.adata
        m_hash = await CacheUtils.get_model_hash(self)
        id_field = getattr(self.serializer_class, "custom_id", "id")
        obj_pk = data.get(id_field)
        if obj_pk:
            await cache.aset(f"obj:{m_hash}:{obj_pk}", data, timeout=600)
        if request.user.is_authenticated:
            await CacheUtils.incr_user_version(request.user.id)
        return Response(data, status=status.HTTP_201_CREATED)


class UpdateModelMixin(mixins.UpdateModelMixin):
    async def aupdate(self, request, *args, **kwargs):
        response = await super().aupdate(request, *args, **kwargs)
        m_hash = await CacheUtils.get_model_hash(self)
        await cache.aset(f"obj:{m_hash}:{self.kwargs['pk']}", response.data, timeout=600)
        if request.user.is_authenticated:
            await CacheUtils.incr_user_version(request.user.id)
        return response


class DestroyModelMixin(mixins.DestroyModelMixin):
    async def adestroy(self, request, *args, **kwargs):
        m_hash = await CacheUtils.get_model_hash(self)
        response = await super().adestroy(request, *args, **kwargs)
        await cache.adelete(f"obj:{m_hash}:{self.kwargs['pk']}")
        if request.user.is_authenticated:
            await CacheUtils.incr_user_version(request.user.id)
        return response

# --- ViewSets ---

class CachedModelReadOnlyViewSet(
    RetrieveModelMixin,
    ListModelMixin, 
    GenericViewSet
):
    pass


class CachedModelViewSet(
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    GenericViewSet,
):
    pass
