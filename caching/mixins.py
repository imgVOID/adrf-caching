from adrf import mixins
from rest_framework import status
from rest_framework.response import Response

from .utils import cache, CacheUtils


class CreateModelMixin(mixins.CreateModelMixin):
    """
    Create and cache a model instance.
    """
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


class ListModelMixin(mixins.ListModelMixin):
    """
    List or cache a queryset.
    """

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
    """
    Retrieve and cache a model instance.
    """

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


class UpdateModelMixin(mixins.UpdateModelMixin):
    """
    Update and cache a model instance.
    """
    async def aupdate(self, request, *args, **kwargs):
        response = await super().aupdate(request, *args, **kwargs)
        m_hash = await CacheUtils.get_model_hash(self)
        await cache.aset(f"obj:{m_hash}:{self.kwargs['pk']}", response.data, timeout=600)
        if request.user.is_authenticated:
            await CacheUtils.incr_user_version(request.user.id)
        return response


class DestroyModelMixin(mixins.DestroyModelMixin):
    """
    Destroy a model instance and clear cache.
    """
    async def adestroy(self, request, *args, **kwargs):
        m_hash = await CacheUtils.get_model_hash(self)
        response = await super().adestroy(request, *args, **kwargs)
        await cache.adelete(f"obj:{m_hash}:{self.kwargs['pk']}")
        if request.user.is_authenticated:
            await CacheUtils.incr_user_version(request.user.id)
        return response
