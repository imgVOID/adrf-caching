import unittest
from django.test import TransactionTestCase
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIRequestFactory, force_authenticate
from unittest.mock import AsyncMock, MagicMock
from rest_framework import status
from adrf.serializers import ModelSerializer as AsyncModelSerializer

from caching.utils import CacheUtils
from caching.viewsets import ModelViewSetCached, ReadOnlyModelViewSetCached


class UserSerializer(AsyncModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']


class TestViewSetIntegration(TransactionTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(username="testadmin", password="password")
        self.path = "/api/users/"
        cache.clear()

    # --- 1. ReadOnlyModelViewSetCached Tests ---

    async def test_readonly_list_integration_no_mocks(self):
        """Verify ReadOnlyModelViewSetCached.list calls alist and caches without any mocks."""
        
        class UserReadOnlyViewSet(ReadOnlyModelViewSetCached):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        # 1. Setup real request
        request = self.factory.get(self.path)
        force_authenticate(request, user=self.user)
        
        # 2. Instantiate view via as_view()
        view_func = UserReadOnlyViewSet.as_view({'get': 'list'})
        response = await view_func(request)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 3. Retrieve the cache key using the actual request object
        # ADRF/DRF attaches the view and parser_context to the request during dispatch.
        # We use the request that has already passed through the view logic.
        list_key = await CacheUtils.generate_list_key(response.renderer_context['request'])
        
        cached_data = await cache.aget(list_key)
        self.assertIsNotNone(cached_data, "Cache key should exist in the backend")
        self.assertEqual(len(cached_data), 1)
        self.assertEqual(cached_data[0]['username'], "testadmin")

    async def test_model_viewset_full_cycle_no_mocks(self):
        """Verify ModelViewSetCached.partial_update updates real cache."""
        
        class UserFullViewSet(ModelViewSetCached):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        # Create a user to update
        target_user = await User.objects.acreate(username="original_name")
        obj_url = f"{self.path}{target_user.id}/"

        # 1. Warm cache via retrieve
        get_req = self.factory.get(obj_url)
        force_authenticate(get_req, user=self.user)
        await UserFullViewSet.as_view({'get': 'retrieve'})(get_req, pk=target_user.id)

        # 2. Update via partial_update
        patch_req = self.factory.patch(obj_url, data={"username": "new_name"}, format='json')
        force_authenticate(patch_req, user=self.user)
        view_func = UserFullViewSet.as_view({'patch': 'partial_update'})
        response = await view_func(patch_req, pk=target_user.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 3. Verify object cache specifically
        # We use CacheUtils directly to find the key name
        view_instance = UserFullViewSet()
        m_hash = await CacheUtils.get_model_hash(view_instance)
        obj_key = f"obj:{m_hash}:{target_user.id}"
        
        cached_val = await cache.aget(obj_key)
        self.assertEqual(cached_val['username'], "new_name")

    async def test_model_viewset_delete_invalidates_no_mocks(self):
        """Verify destroy removes items from cache."""
        
        class UserFullViewSet(ModelViewSetCached):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        target_user = await User.objects.acreate(username="bye_bye")
        view_instance = UserFullViewSet()
        m_hash = await CacheUtils.get_model_hash(view_instance)
        obj_key = f"obj:{m_hash}:{target_user.id}"

        # Seed cache manually
        await cache.aset(obj_key, {"username": "bye_bye"})

        # Delete via ViewSet action
        del_req = self.factory.delete(f"{self.path}{target_user.id}/")
        force_authenticate(del_req, user=self.user)
        await UserFullViewSet.as_view({'delete': 'destroy'})(del_req, pk=target_user.id)

        # Assert cache is purged
        self.assertIsNone(await cache.aget(obj_key))

    # --- 2. ModelViewSetCached Tests ---

    async def test_model_viewset_create_integration(self):
        """Verify ModelViewSetCached.create calls acreate and invalidates lists."""

        class UserFullViewSet(ModelViewSetCached):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        # 1. Warm list cache
        list_req = self.factory.get(self.path)
        force_authenticate(list_req, user=self.user)
        await UserFullViewSet.as_view({'get': 'list'})(list_req)
        
        u_ver_before = await CacheUtils.get_user_version(self.user.id)

        # 2. Perform Create
        create_data = {"username": "newuser", "password": "password123"}
        request = self.factory.post(self.path, data=create_data, format='json')
        force_authenticate(request, user=self.user)
        
        view = UserFullViewSet.as_view({'post': 'create'})
        response = await view(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # 3. Verify Version Bump (proving acreate logic was executed)
        u_ver_after = await cache.aget(f"u_ver:{self.user.id}")
        self.assertEqual(u_ver_after, u_ver_before + 1)

    async def test_model_viewset_partial_update_integration(self):
        """Verify partial_update proxies to partial_aupdate and updates obj cache."""

        class UserFullViewSet(ModelViewSetCached):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        target_user = await User.objects.acreate(username="target")
        obj_url = f"{self.path}{target_user.id}/"
        
        # 1. Warm Object Cache via retrieve()
        get_req = self.factory.get(obj_url)
        force_authenticate(get_req, user=self.user)
        await UserFullViewSet.as_view({'get': 'retrieve'})(get_req, pk=target_user.id)

        # 2. Patch via partial_update()
        patch_data = {"username": "patched_name"}
        request = self.factory.patch(obj_url, data=patch_data, format='json')
        force_authenticate(request, user=self.user)
        
        view = UserFullViewSet.as_view({'patch': 'partial_update'})
        response = await view(request, pk=target_user.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 3. Verify Object Cache is updated
        m_hash = await CacheUtils.get_model_hash(UserFullViewSet())
        cached_obj = await cache.aget(f"obj:{m_hash}:{target_user.id}")
        self.assertEqual(cached_obj['username'], "patched_name")

    async def test_model_viewset_destroy_integration(self):
        """Verify destroy proxies to adestroy and purges cache."""

        class UserFullViewSet(ModelViewSetCached):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        target_user = await User.objects.acreate(username="to_delete")
        m_hash = await CacheUtils.get_model_hash(UserFullViewSet())
        obj_key = f"obj:{m_hash}:{target_user.id}"
        
        # Seed cache
        await cache.aset(obj_key, {"username": "to_delete"})

        # Delete
        request = self.factory.delete(f"{self.path}{target_user.id}/")
        force_authenticate(request, user=self.user)
        
        view = UserFullViewSet.as_view({'delete': 'destroy'})
        response = await view(request, pk=target_user.id)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNone(await cache.aget(obj_key))
