
from adrf.generics import GenericAPIView

from . import mixins


class CreateAPIView(mixins.CreateModelMixin, GenericAPIView):
    """
    Concrete async cached view for creating a model instance.
    """

    async def post(self, request, *args, **kwargs):
        return await self.acreate(request, *args, **kwargs)


class ListAPIView(mixins.ListModelMixin, GenericAPIView):
    """
    Concrete async cached view for listing a queryset.
    """

    async def get(self, request, *args, **kwargs):
        return await self.alist(request, *args, **kwargs)


class RetrieveAPIView(mixins.RetrieveModelMixin, GenericAPIView):
    """
    Concrete async cached view for retrieving a model instance.
    """

    async def get(self, request, *args, **kwargs):
        return await self.aretrieve(request, *args, **kwargs)


class DestroyAPIView(mixins.DestroyModelMixin, GenericAPIView):
    """
    Concrete async cached view for deleting a model instance.
    """

    async def delete(self, request, *args, **kwargs):
        return await self.adestroy(request, *args, **kwargs)


class UpdateAPIView(mixins.UpdateModelMixin, GenericAPIView):
    """
    Concrete async cached view for updating a model instance.
    """

    async def put(self, request, *args, **kwargs):
        return await self.aupdate(request, *args, **kwargs)

    async def patch(self, request, *args, **kwargs):
        return await self.partial_aupdate(request, *args, **kwargs)


class ListCreateAPIView(mixins.ListModelMixin, mixins.CreateModelMixin, GenericAPIView):
    """
    Concrete async cached view for listing a queryset or creating a model instance.
    """

    async def get(self, request, *args, **kwargs):
        return await self.alist(request, *args, **kwargs)

    async def post(self, request, *args, **kwargs):
        return await self.acreate(request, *args, **kwargs)


class RetrieveUpdateAPIView(
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericAPIView
):
    """
    Concrete async cached view for retrieving, updating a model instance.
    """

    async def get(self, request, *args, **kwargs):
        return await self.aretrieve(request, *args, **kwargs)

    async def put(self, request, *args, **kwargs):
        return await self.aupdate(request, *args, **kwargs)

    async def patch(self, request, *args, **kwargs):
        return await self.partial_aupdate(request, *args, **kwargs)


class RetrieveDestroyAPIView(
    mixins.RetrieveModelMixin, mixins.DestroyModelMixin, GenericAPIView
):
    """
    Concrete async cached view for retrieving or deleting a model instance.
    """

    async def get(self, request, *args, **kwargs):
        return await self.aretrieve(request, *args, **kwargs)

    async def delete(self, request, *args, **kwargs):
        return await self.adestroy(request, *args, **kwargs)


class RetrieveUpdateDestroyAPIView(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericAPIView,
):
    """
    Concrete async cached view for retrieving, updating or deleting a model instance.
    """


    async def get(self, request, *args, **kwargs):
        return await self.aretrieve(request, *args, **kwargs)

    async def put(self, request, *args, **kwargs):
        return await self.aupdate(request, *args, **kwargs)

    async def patch(self, request, *args, **kwargs):
        return await self.partial_aupdate(request, *args, **kwargs)

    async def delete(self, request, *args, **kwargs):
        return await self.adestroy(request, *args, **kwargs)
