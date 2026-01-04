
from adrf.generics import GenericAPIView

from . import mixins


class CreateAPIView(mixins.CreateModelMixin, GenericAPIView):
    """
    Concrete async cached view for creating a model instance.
    """


class ListAPIView(mixins.ListModelMixin, GenericAPIView):
    """
    Concrete async cached view for listing a queryset.
    """



class RetrieveAPIView(mixins.RetrieveModelMixin, GenericAPIView):
    """
    Concrete async cached view for retrieving a model instance.
    """


class DestroyAPIView(mixins.DestroyModelMixin, GenericAPIView):
    """
    Concrete async cached view for deleting a model instance.
    """


class UpdateAPIView(mixins.UpdateModelMixin, GenericAPIView):
    """
    Concrete async cached view for updating a model instance.
    """


class ListCreateAPIView(mixins.ListModelMixin, mixins.CreateModelMixin, GenericAPIView):
    """
    Concrete async cached view for listing a queryset or creating a model instance.
    """


class RetrieveUpdateAPIView(
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin, GenericAPIView
):
    """
    Concrete async cached view for retrieving, updating a model instance.
    """


class RetrieveDestroyAPIView(
    mixins.RetrieveModelMixin, mixins.DestroyModelMixin, GenericAPIView
):
    """
    Concrete async cached view for retrieving or deleting a model instance.
    """


class RetrieveUpdateDestroyAPIView(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericAPIView,
):
    """
    Concrete async cached view for retrieving, updating or deleting a model instance.
    """
