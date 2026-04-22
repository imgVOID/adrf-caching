# adrf-caching

[![PyPI](https://img.shields.io/badge/pypi-package-blue)](https://pypi.org/project/adrf-caching/)
[![Tests](https://github.com/imgvoid/adrf-caching/actions/workflows/tests.yml/badge.svg)](https://github.com/imgvoid/adrf-caching/actions/workflows/tests.yml)
[![Socket Badge](https://badge.socket.dev/pypi/package/adrf-caching/latest)](https://badge.socket.dev/pypi/package/adrf-caching/latest)

A high-performance library that extends **ADRF (Asynchronous Django REST Framework)** with asynchronous Django-based per-user caching.

## 🚀 Key Features
#### Contains asynchronous caching mixins, generics and viewsets for Async Django Rest Framework and Django 5.0+:
* **100% Asynchronous:** Built from the ground up with `async/await`, ensuring non-blocking I/O for database and cache operations.
* **Automatic Async Caching:** Seamlessly caches results to your configured cache backend (e.g., Redis) using Django Async Caching.
* **Smart Invalidation (Cache Versioning):** Instead of manually clearing complex cache keys, it uses a versioning system. When a user modifies data, their specific version increments, instantly invalidating outdated lists.
* **Secure Data Isolation:** Prevents data leakage by incorporating unique user hashes and versions into cache keys.
* **MD5 Hashing:** Optimized performance using `md5` for compact and consistent cache keys.
* **OpenAPI Support:** Fully compatible with `drf-spectacular` scheme generator.

## 🛠 Prerequisites

* **Python:** 3.10+
* **Django:** 4.2+ (with an async-capable cache backend)
* **ADRF:** [Asynchronous Django REST Framework](https://github.com/em1208/adrf)
* **drf-spectacular** (Optional): [OpenAPI 3.0 schema generation for DRF](https://github.com/tfranzel/drf-spectacular)


## ⚙️ Installation
```
pip install adrf-caching
```

## 📖 Usage Guide

This library provides three levels of integration: **Generics** (pre-built views), **ViewSets** (ready-to-use CRUD classes), and **Mixins** (for custom logic).

### 1. Using Cached ViewSets (Recommended for CRUD)
The easiest way to implement full CRUD with caching is to inherit from the cached ViewSet classes. These classes bridge ADRF's async capabilities with the caching logic.

```python
from adrf_caching.viewsets import ModelViewSetCached, ReadOnlyModelViewSetCached
from .models import Post
from .serializers import PostSerializer

# Full CRUD (Create, List, Retrieve, Update, Delete) with Cache
class PostViewSet(ModelViewSetCached):
    queryset = Post.objects.all()
    serializer_class = PostSerializer

# Read-only API (List, Retrieve) with Cache
class PostReadOnlyViewSet(ReadOnlyModelViewSetCached):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
```

### 2. Using Concrete Generics (Fastest)
The simplest way is to inherit from pre-built generic views in `generics.py`. These already include both ADRF's async logic and the caching mixins.

```python
from adrf_caching.generics import ListCreateAPIView
from .models import Book
from .serializers import BookSerializer

class BookListCreateView(ListCreateAPIView):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
```

### 3. Adding Mixins to Existing ADRF Classes (Flexible)
If you already have a class based on adrf.generics.GenericAPIView, you can inject the caching logic by placing the mixins before any other classes in the inheritance chain.

```python
from adrf.viewsets import GenericViewSet
from adrf_caching.mixins import ListModelMixin, RetrieveModelMixin
from .models import Profile
from .serializers import ProfileSerializer

class ProfileViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
```

### 4. Changing TTL and prefix
The library works out-of-the-box with sensible defaults, but you can customize its behavior by adding the `ADRF_CACHING_SETTINGS` dictionary to your Django `settings.py`. 
The settings include built-in validation: providing a non-integer value for TTL settings will raise an `ImproperlyConfigured` error during startup to prevent runtime failures.

```python
# settings.py
ADRF_CACHING_SETTINGS = {
    "TTL_OBJECT": 600,             # Cache duration for single objects (seconds)
    "TTL_LIST": 300,               # Cache duration for lists (seconds)
    "TTL_USER_VER": 86400,         # How long the user's version key lives
    "PREFIX": "adrf_caching",      # Global prefix for all cache keys
}
```

### 5. Automated Multi-User Invalidation

In many cases, an update to a resource should invalidate the cache for multiple users associated with that resource. The `CacheInvalidationMixin` automates this process by incrementing the cache version for all relevant parties during update and destroy operations.

Standard caching usually only invalidates the requester's view. This mixin ensures that if `User Type A` modifies a shared resource, `User Type B` (and any others linked to the object) will instantly see the updated data because their specific cache versions are also incremented. That is, if the administrator changes an object, the cache is invalidated for the owners of this object.

```
from adrf_caching.mixins import CacheInvalidationMixin
from adrf_caching.generics import RetrieveUpdateDestroyAPIView

class SharedResourceView(CacheInvalidationMixin, RetrieveUpdateDestroyAPIView):
    queryset = SharedResource.objects.all()
    serializer_class = SharedResourceSerializer
    
    # List the foreign key fields containing User IDs to be invalidated
    invalidate_fields = ("participant_one_id", "participant_two_id")
```

### 📜 OpenAPI Schema & Documentation

##### The library is optimized for **[drf-spectacular](https://github.com/tfranzel/drf-spectacular)**.

Since `drf-spectacular` and many other libs expects standard DRF action names, we need to directly map async methods (like alist, aretrieve) back to their standard counterparts during schema generation. This ensures that features like pagination, filters, and correct response types are automatically detected.

```python
class CustomReadOnlyViewSet(ReadOnlyModelViewSetCached):
    queryset = Test.objects.all()

    @extend_schema(summary="retrieve by id", description="retrieve")
    async def aretrieve(self, request, *args, **kwargs):
        return await super().aretrieve(request, *args, **kwargs)
```

You can use explicit method mapping in `urls.py` or the adrf async router. This helps the schema inspector distinguish between different actions (like `list` and `alist`, `retrieve` and `aretrieve`) and prevents collisions.

```python
from django.urls import path
from . import views

urlpatterns = [
    # Explicit mapping for ViewSets ensures clean async OpenAPI
    # Or you can use adrf.routers.DefaultRouter
    path("items/", views.ItemViewSet.as_view({'get': 'alist', 'post': 'acreate'})),
    path("items/<int:pk>/", views.ItemViewSet.as_view({'get': 'aretrieve', 'put': 'aupdate'})),
]
```

Remember to use regular method names without the 'a' prefix. Actions have a prefix, methods do not.

```python
class RetrieveUpdateCustomView(RetrieveUpdateAPIView):
    queryset = Test.objects.all()

    @extend_schema(summary="Async GET")
    async def get(self, request, *args, **kwargs):
        return await super().get(request, *args, **kwargs)
```

#### Extra
To ensure correct object caching after creation or updates, the library looks for the id field by default. If your model uses a different primary key (e.g., uuid or slug or one to one relation), you must specify it in the serializer using the 'custom_id' attribute:
```python
class MySerializer(serializers.ModelSerializer):
    custom_id = "uuid"  # Set this if your primary key is not 'id'
    
    class Meta:
        model = MyModel
        fields = "__all__"
```
### 🏃 Running Tests

The library uses `pytest` to ensure database integrity during async operations.
```
# Exec command to run all tests from the main dir
pytest
# Or as a module
python -m pytest -v
```

## License
Apache 2.0 License

django async, drf async, adrf, django 5 async views, async serializers, async caching, drf caching, asynchronous drf, adrf, django rest framework, python async api, drf-spectacular, OpenAPI 3.0, Swagger, Redoc, async api documentation, schema generation, adrf-spectacular
