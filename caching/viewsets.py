from adrf.viewsets import GenericViewSet
from .mixins import *


class ReadOnlyModelViewSetCached(
    RetrieveModelMixin,
    ListModelMixin, 
    GenericViewSet
):
    """
    A viewset that provides default asynchronous `list()` and `retrieve()` actions. Cached.
    """
    async def list(self, request, *args, **kwargs):
        return await self.alist(request, *args, **kwargs)

    async def retrieve(self, request, pk=None, *args, **kwargs):
        return await self.aretrieve(request, pk=pk, *args, **kwargs)


class ModelViewSetCached(
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    GenericViewSet
):
    """
    A viewset that provides default asynchronous `create()`, `retrieve()`, `update()`,
    `partial_update()`, `destroy()` and `list()` actions. Cached.
    """

    async def list(self, request, *args, **kwargs):
        return await self.alist(request, *args, **kwargs)

    async def create(self, request, *args, **kwargs):
        return await self.acreate(request, *args, **kwargs)

    async def retrieve(self, request, pk=None, *args, **kwargs):
        return await self.aretrieve(request, pk=pk, *args, **kwargs)

    async def update(self, request, *args, **kwargs):
        return await self.aupdate(request, *args, **kwargs)

    async def partial_update(self, request, *args, **kwargs):
        return await self.partial_aupdate(request, *args, **kwargs)

    async def destroy(self, request, *args, **kwargs):
        return await self.adestroy(request, *args, **kwargs)
