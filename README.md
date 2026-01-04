# adrf-caching

A high-performance library that extends **ADRF (Asynchronous Django REST Framework)** with intelligent, per-user async caching. It reduces database load and decreases response times by leveraging asynchronous cache operations and a smart invalidation strategy based on user-specific versioning.

## 🚀 Key Features
#### Contains asynchronous caching mixins, generics and viewsets for Async Django Rest Framework and Django 5.0+:
* **100% Asynchronous:** Built from the ground up with `async/await`, ensuring non-blocking I/O for database and cache operations.
* **Automatic Async Caching:** Seamlessly caches results to your configured cache backend (e.g., Redis) using Django Async Caching.
* **Smart Invalidation (Cache Versioning):** Instead of manually clearing complex cache keys, it uses a versioning system. When a user modifies data, their specific version increments, instantly invalidating outdated lists.
* **Secure Data Isolation:** Prevents data leakage by incorporating unique user hashes and versions into cache keys.
* **MD5 Hashing:** Optimized performance using MD5 for compact and consistent cache keys.

## 🛠 Prerequisites

* **Python:** 3.10+
* **Django:** 4.2+ (with an async-capable cache backend)
* **ADRF:** [Asynchronous Django REST Framework](https://github.com/vbabiy/adrf)

## 📖 Usage Guide

This library provides three levels of integration: **Generics** (pre-built views), **ViewSets** (ready-to-use CRUD classes), and **Mixins** (for custom logic).

### 1. Using Cached ViewSets (Recommended for CRUD)
The easiest way to implement full CRUD with caching is to inherit from our cached ViewSet classes. These classes bridge ADRF's async capabilities with our caching logic.

```python
from your_app.viewsets import ModelViewSetCached, ReadOnlyModelViewSetCached
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
The simplest way is to inherit from pre-built generic views in `generics.py`. These already include both ADRF's async logic and our caching mixins.

```python
from your_app.generics import ListCreateAPIView
from .models import Book
from .serializers import BookSerializer

class BookListCreateView(ListCreateAPIView):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
```

### 3. Adding Mixins to Existing ADRF Classes (Flexible)
If you already have a class based on adrf.generics.GenericAPIView, you can inject our caching logic by placing our mixins before any other classes in the inheritance chain.

```python
from adrf.viewsets import GenericViewSet
from caching.mixins import ListModelMixin, RetrieveModelMixin
from .models import Profile
from .serializers import ProfileSerializer

class ProfileViewSet(ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
```

### Extra
To ensure correct object caching after creation or updates, the library looks for the id field by default. If your model uses a different primary key (e.g., uuid or slug or one to one relation), you must specify it in the serializer using the 'custom_id' attribute:
```python
class MySerializer(serializers.ModelSerializer):
    custom_id = "uuid"  # Set this if your primary key is not 'id'
    
    class Meta:
        model = MyModel
        fields = "__all__"
```

## License
Apache 2.0 License

django async, drf async, adrf, django 5 async views, async serializers, async caching, drf caching, asynchronous drf, adrf, django rest framework, python async api
