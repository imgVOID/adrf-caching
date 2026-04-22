from adrf import mixins
from rest_framework import status
from rest_framework.response import Response
from asgiref.sync import sync_to_async

from .utils import cache, CacheUtils, lib_settings


class CreateModelMixin(mixins.CreateModelMixin):
    """
    Create and cache a model instance.
    Invalidates user list version and any owners specified in invalidate_fields.
    """
    async def acreate(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        await sync_to_async(serializer.is_valid, thread_sensitive=True)(raise_exception=True)
        await self.perform_acreate(serializer)
        data = await serializer.adata
        
        m_hash = await CacheUtils.get_model_hash(self)
        id_field = getattr(self.serializer_class, "custom_id", "id")
        obj_pk = data.get(id_field)
        
        if obj_pk:
            await cache.aset(
                f"{lib_settings.PREFIX}:obj:{m_hash}:{obj_pk}", 
                data, timeout=lib_settings.TTL_OBJECT
            )
            
        await CacheUtils.invalidate_list_cache(request, self, getattr(serializer, 'instance', None))
        return Response(data, status=status.HTTP_201_CREATED)


class ListModelMixin(mixins.ListModelMixin):
    """
    List or cache a queryset with user isolation.
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
        await cache.aset(cache_key, data, timeout=lib_settings.TTL_LIST)
        return Response(data, status=status.HTTP_200_OK)


class RetrieveModelMixin(mixins.RetrieveModelMixin):
    """
    Retrieve and cache a model instance.
    """
    async def aretrieve(self, request, *args, **kwargs):
        instance = await self.aget_object()
        m_hash = await CacheUtils.get_model_hash(self)
        cache_key = f"{lib_settings.PREFIX}:obj:{m_hash}:{instance.pk}"
        if (cached := await cache.aget(cache_key)):
            return Response(cached, status=status.HTTP_200_OK)
        serializer = self.get_serializer(instance)
        data = await serializer.adata
        await cache.aset(cache_key, data, timeout=lib_settings.TTL_OBJECT)
        return Response(data, status=status.HTTP_200_OK)


class UpdateModelMixin(mixins.UpdateModelMixin):
    async def aupdate(self, request, *args, **kwargs):
        response = await super().aupdate(request, *args, **kwargs)
        
        instance = await self.aget_object() 
        
        m_hash = await CacheUtils.get_model_hash(self)
        await cache.aset(
            f"{lib_settings.PREFIX}:obj:{m_hash}:{self.kwargs['pk']}", 
            response.data, timeout=lib_settings.TTL_OBJECT
        )
        
        await CacheUtils.invalidate_list_cache(request, self, instance)
        return response


class DestroyModelMixin(mixins.DestroyModelMixin):
    """
    Destroy a model instance and clear cache.
    """
    async def adestroy(self, request, *args, **kwargs):
        # Fetch instance BEFORE deletion to ensure related fields are accessible
        instance = await self.aget_object()
        m_hash = await CacheUtils.get_model_hash(self)
        
        await CacheUtils.invalidate_list_cache(request, self, instance)
        
        response = await super().adestroy(request, *args, **kwargs)
        
        await cache.adelete(f"{lib_settings.PREFIX}:obj:{m_hash}:{self.kwargs['pk']}")
        return response


class CacheInvalidationMixin:
    """
    Declarative mixin for ADRF views to specify multiple owners.
    The list caches for these owners will be invalidated on updates/deletes.
    """
    invalidate_fields = []
