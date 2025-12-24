# adrf-caching

**Asynchronous Mixins and Serializer Utilities for Django REST Framework, ADRF, and Django 5.0+ Async Views**

---

## Overview

`adrf-caching` provides a set of asynchronous mixins and serializer tools designed to seamlessly integrate **Django 5.0+ native async views** into existing Django REST Framework (DRF) projects. It also supports ADRF (Asynchronous DRF), enabling developers to build fully async REST APIs with minimal changes.

This package solves a key challenge: extending traditional DRF functionality with native async support while maintaining full compatibility with existing DRF and ADRF codebases.

---

## Key Features

- 🔄 **Native async API support:** Write async views using Django 5.0+ `async def` with familiar DRF mixins.
- 🔐 **Built-in async caching:** Integrated async cache support using Django 5.0+ cache API (`aget`, `aset`, `ahas_key`) to reduce redundant DB queries.
- 🧩 **Async Serializer mixins:** Async-compatible `is_valid()` and `to_representation()` for serializers to support async validation and serialization pipelines.
- 🤝 **Full compatibility:** Works smoothly with traditional DRF, ADRF, and Django 5 async class-based views.
- ⚙️ **Easy to integrate:** Drop-in extensions for existing DRF views and serializers enabling async capabilities.

---

## Why Use adrf-caching?
1. Seamlessly extend DRF with async Django 5.0+ views. No need to rewrite your entire API.
2. Leverage async caching to reduce redundant database queries and improve response consistency.
3. Compatible with ADRF if you are already using or experimenting with official async DRF package.
4. Modern async serializers simplify building fully async data pipelines with nested relations.

## Example
```
from caching.mixins import CachedModelViewSet

class MyCachedModelViewSet(CachedModelViewSet):
    queryset = MyModel.objects.all()
    serializer_class = MyModelSerializer
```

## Requirements
* Python 3.10+
* Django 5.0+
* Django REST Framework
* Optional: ADRF (Asynchronous Django REST Framework) for extended async support

## License
Apache 2.0 License

django async, drf async, adrf, django 5 async views, async serializers, async caching, drf caching, asynchronous drf, adrf, django rest framework, python async api
