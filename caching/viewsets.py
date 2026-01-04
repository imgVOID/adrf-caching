from adrf.viewsets import GenericViewSet

from mixins import *


class ReadOnlyModelViewSetCached(
    RetrieveModelMixin,
    ListModelMixin, 
    GenericViewSet
):
    
    """
    A viewset that provides default asynchronous `list()` and `retrieve()` actions. Cached.
    """
    pass


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
    pass
