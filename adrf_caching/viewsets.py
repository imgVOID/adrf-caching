from adrf.viewsets import GenericViewSet
from .mixins import *


class ReadOnlyModelViewSetCached(
    RetrieveModelMixin,
    ListModelMixin, 
    GenericViewSet
):
    """
    A viewset that provides default asynchronous `alist()` and `aretrieve()` actions. Cached.
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
    A viewset that provides default asynchronous `acreate()`, `aretrieve()`, `aupdate()`,
    `partial_aupdate()`, `adestroy()` and `alist()` actions. Cached.
    """
    pass
