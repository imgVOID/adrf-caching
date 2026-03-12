from adrf import mixins
from rest_framework import status
from rest_framework.response import Response
from asgiref.sync import sync_to_async

from .utils import cache, CacheUtils, lib_settings


class CreateModelMixin(mixins.CreateModelMixin):
    """
    Create and cache a model instance.
    Invalidates user list version.
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
        if request.user.is_authenticated:
            await CacheUtils.incr_user_version(request.user.id)
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
    """
    Update and cache a model instance.
    """
    async def aupdate(self, request, *args, **kwargs):
        response = await super().aupdate(request, *args, **kwargs)
        m_hash = await CacheUtils.get_model_hash(self)
        await cache.aset(
            f"{lib_settings.PREFIX}:obj:{m_hash}:{self.kwargs['pk']}", 
            response.data, timeout=lib_settings.TTL_OBJECT
        )
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
        await cache.adelete(f"{lib_settings.PREFIX}:obj:{m_hash}:{self.kwargs['pk']}")
        if request.user.is_authenticated:
            await CacheUtils.incr_user_version(request.user.id)
        return response


class CacheInvalidationMixin:
    """
    Mixin for ADRF views to automatically invalidate user cache 
    during update and destroy operations.
    Use if the object has more than one owner.
    Please specify owners "id" fields in invalidate_fields.
    """
    invalidate_fields = []

    async def _perform_invalidation(self, instance):
        target_ids = set()

        # 1. Requester ID
        if self.request.user.is_authenticated:
            target_ids.add(self.request.user.id)

        # 2. Related user IDs from the instance
        if instance:
            for field in self.invalidate_fields:
                u_id = getattr(instance, field, None)
                if u_id:
                    target_ids.add(u_id)

        # 3. Trigger async increment
        for u_id in target_ids:
            await CacheUtils.incr_user_version(u_id)

    async def perform_aupdate(self, serializer):
        # adrf serializers use asave()
        instance = await serializer.asave()
        await self._perform_invalidation(instance)

    async def perform_adestroy(self, instance):
        # Invalidate before deletion to ensure related IDs are accessible
        await self._perform_invalidation(instance)
        await instance.adelete()

    async def perform_acreate(self, serializer):
        instance = await serializer.asave()
        await self._perform_invalidation(instance)
