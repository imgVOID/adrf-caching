import unittest
import tests.config
from asgiref.sync import sync_to_async
from django.test import TransactionTestCase
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.parsers import JSONParser
from adrf.serializers import ModelSerializer as AsyncModelSerializer

from caching.generics import (
    ListCreateAPIView, RetrieveUpdateDestroyAPIView, 
    RetrieveUpdateAPIView, ListAPIView
)
from caching.utils import CacheUtils


class UserSerializer(AsyncModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']


class TestConcreteGenericsCache(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.username = "generic_user"
        self.user = User.objects.create_user(username=self.username)
        self.client.force_authenticate(user=self.user)
        self.path = "/api/users/"
        cache.clear()

    def _prepare_generic_view(self, view_class, method='get', url=None, data=None, kwargs=None):
        """
        Helper to initialize GenericAPIView subclasses with a real request 
        passing through the DRF internal initialization logic.
        """
        view = view_class()
        view.kwargs = kwargs or {}
        view.format_kwarg = None
        view.parser_classes = [JSONParser]
        
        # Simulate request via client to get a proper WSGI request
        client_func = getattr(self.client, method)
        wsgi_req = client_func(url or self.path, data=data, format='json').wsgi_request
        
        # ADRF/DRF initialization
        view.request = view.initialize_request(wsgi_req)
        return view

    # --- 1. LIST & CREATE (ListCreateAPIView) ---

    async def test_list_create_api_view_flow(self):
        """Verify ListCreateAPIView correctly caches lists and invalidates on create."""
        
        class UserListCreate(ListCreateAPIView):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        # 1. Warm list cache via alist
        view = self._prepare_generic_view(UserListCreate, method='get')
        await view.alist(view.request)
        
        list_key = await CacheUtils.generate_list_key(view.request)
        self.assertIsNotNone(await cache.aget(list_key), "List should be cached")

        # 2. Perform Create via acreate
        create_view = self._prepare_generic_view(
            UserListCreate, method='post', data={"username": "new_generic"}
        )
        await create_view.acreate(create_view.request)

        # 3. Verify Version Bump
        new_list_key = await CacheUtils.generate_list_key(view.request)
        self.assertNotEqual(list_key, new_list_key, "Creation must bump the list version")

    # --- 2. RETRIEVE, UPDATE, DESTROY (RetrieveUpdateDestroyAPIView) ---

    async def test_full_detail_lifecycle(self):
        """Verify GET, PUT, and DELETE flow for RetrieveUpdateDestroyAPIView."""
        
        class UserDetail(RetrieveUpdateDestroyAPIView):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        target_user = await User.objects.acreate(username="target")
        obj_url = f"{self.path}{target_user.id}/"
        m_hash = await CacheUtils.get_model_hash(UserDetail())
        obj_key = f"obj:{m_hash}:{target_user.id}"

        # 1. Retrieve (aretrieve)
        view = self._prepare_generic_view(UserDetail, url=obj_url, kwargs={'pk': target_user.id})
        await view.aretrieve(view.request, pk=target_user.id)
        self.assertIsNotNone(await cache.aget(obj_key))

        # 2. Update (aupdate - PUT)
        upd_view = self._prepare_generic_view(
            UserDetail, method='put', url=obj_url, 
            data={"username": "updated"}, kwargs={'pk': target_user.id}
        )
        await upd_view.aupdate(upd_view.request, pk=target_user.id)
        
        cached_val = await cache.aget(obj_key)
        self.assertEqual(cached_val['username'], "updated")

        # 3. Destroy (adestroy)
        del_view = self._prepare_generic_view(
            UserDetail, method='delete', url=obj_url, kwargs={'pk': target_user.id}
        )
        await del_view.adestroy(del_view.request, pk=target_user.id)
        self.assertIsNone(await cache.aget(obj_key), "Cache must be purged")

    # --- 3. PARTIAL UPDATE (UpdateAPIView / RetrieveUpdateAPIView) ---

    async def test_partial_update_refreshes_cache(self):
        """Verify that PATCH calls partial_aupdate and updates the cache."""
        
        class UserUpdate(RetrieveUpdateAPIView):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        target = await User.objects.acreate(username="old_name")
        obj_url = f"{self.path}{target.id}/"
        
        # Manually seed cache
        m_hash = await CacheUtils.get_model_hash(UserUpdate())
        obj_key = f"obj:{m_hash}:{target.id}"
        await cache.aset(obj_key, {"username": "old_name"})

        # PATCH request
        patch_view = self._prepare_generic_view(
            UserUpdate, method='patch', url=obj_url, 
            data={"username": "new_name"}, kwargs={'pk': target.id}
        )
        # Use partial=True to simulate the partial_aupdate logic
        await patch_view.partial_aupdate(patch_view.request, pk=target.id)

        self.assertEqual((await cache.aget(obj_key))['username'], "new_name")

    # --- 4. CACHE ISOLATION ---

    async def test_list_params_isolation_in_generics(self):
        """Ensure ListAPIView creates separate keys for different filters."""
        
        class UserList(ListAPIView):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        # Query 1
        v1 = self._prepare_generic_view(UserList, url=f"{self.path}?search=a")
        await v1.alist(v1.request)
        key1 = await CacheUtils.generate_list_key(v1.request)

        # Query 2
        v2 = self._prepare_generic_view(UserList, url=f"{self.path}?search=b")
        await v2.alist(v2.request)
        key2 = await CacheUtils.generate_list_key(v2.request)

        self.assertNotEqual(key1, key2)

    async def test_guest_vs_user_caching_generics(self):
        """Ensure guests and users don't share list cache in concrete views."""
        
        class UserList(ListAPIView):
            queryset = User.objects.all()
            serializer_class = UserSerializer

        # Auth User Key
        v_auth = self._prepare_generic_view(UserList)
        key_auth = await CacheUtils.generate_list_key(v_auth.request)

        # Logout to Guest
        await sync_to_async(self.client.force_authenticate)(user=None)
        
        # Guest Key
        v_guest = self._prepare_generic_view(UserList)
        key_guest = await CacheUtils.generate_list_key(v_guest.request)

        self.assertNotEqual(key_auth, key_guest)

if __name__ == "__main__":
    unittest.main()
