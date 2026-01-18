import unittest
import tests.config  # Must be the first import to initialize Django
from asgiref.sync import sync_to_async
from django.test import TransactionTestCase
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.parsers import JSONParser
from rest_framework.exceptions import ValidationError

from adrf.viewsets import GenericViewSet
from adrf.serializers import ModelSerializer as AsyncModelSerializer

from caching.mixins import (
    CreateModelMixin, ListModelMixin, RetrieveModelMixin, 
    UpdateModelMixin, DestroyModelMixin
)
from caching.utils import CacheUtils

# --- Mock Components ---

class UserSerializer(AsyncModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']


class UserViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, 
                  UpdateModelMixin, DestroyModelMixin, GenericViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

# --- Integration Tests ---

class TestCacheSystem(TransactionTestCase):
    def setUp(self):
        self.client = APIClient()
        self.username = "primary_user"
        self.user = User.objects.create_user(username=self.username)
        self.client.force_authenticate(user=self.user)
        self.path = "/api/users/"
        cache.clear()

    def _prepare_view(self, action, method='get', url=None, data=None, kwargs=None):
        view = UserViewSet()
        view.action = action
        view.action_map = {
            'get': 'alist' if action == 'alist' else 'aretrieve',
            'post': 'acreate',
            'put': 'aupdate',
            'patch': 'aupdate',
            'delete': 'adestroy'
        }
        view.kwargs = kwargs or {}
        view.format_kwarg = None
        view.parser_classes = [JSONParser]
        
        client_func = getattr(self.client, method)
        wsgi_req = client_func(url or self.path, data=data, format='json').wsgi_request
        view.request = view.initialize_request(wsgi_req)
        return view

    # --- 1. BASIC CRUD CASES ---

    async def test_basic_retrieve_populates_cache(self):
        """Verify that a standard GET request fills the cache."""
        obj_url = f"{self.path}{self.user.id}/"
        view = self._prepare_view('aretrieve', url=obj_url, kwargs={'pk': self.user.id})
        
        await view.aretrieve(view.request, pk=self.user.id)
        
        m_hash = await CacheUtils.get_model_hash(view)
        cached_data = await cache.aget(f"obj:{m_hash}:{self.user.id}")
        self.assertEqual(cached_data['username'], self.username)

    async def test_basic_full_update_put(self):
        """Verify that a PUT request refreshes the object cache."""
        obj_url = f"{self.path}{self.user.id}/"
        new_name = "fully_updated_name"
        
        view = self._prepare_view('aupdate', method='put', url=obj_url, 
                                 data={"username": new_name}, kwargs={'pk': self.user.id})
        await view.aupdate(view.request, pk=self.user.id)
        
        m_hash = await CacheUtils.get_model_hash(view)
        cached_val = await cache.aget(f"obj:{m_hash}:{self.user.id}")
        self.assertEqual(cached_val['username'], new_name)

    async def test_basic_partial_update_patch(self):
        """Verify that a PATCH request correctly updates the cache."""
        obj_url = f"{self.path}{self.user.id}/"
        new_name = "partial_patch_name"
        
        view = self._prepare_view('aupdate', method='patch', url=obj_url, 
                                 data={"username": new_name}, kwargs={'pk': self.user.id})
        # We simulate the partial flag that DRF usually sets during dispatch
        await view.aupdate(view.request, pk=self.user.id, partial=True)
        
        m_hash = await CacheUtils.get_model_hash(view)
        cached_val = await cache.aget(f"obj:{m_hash}:{self.user.id}")
        self.assertEqual(cached_val['username'], new_name)

    async def test_basic_delete_purges_cache(self):
        """Verify that deleting an object removes it from the cache."""
        obj_url = f"{self.path}{self.user.id}/"
        m_hash = await CacheUtils.get_model_hash(UserViewSet())
        obj_key = f"obj:{m_hash}:{self.user.id}"

        await cache.aset(obj_key, {"username": "exists"})
        
        view = self._prepare_view('adestroy', method='delete', url=obj_url, kwargs={'pk': self.user.id})
        await view.adestroy(view.request, pk=self.user.id)
        
        self.assertIsNone(await cache.aget(obj_key))

    # --- 2. PEDANTIC INTEGRITY CASES ---

    async def test_integrity_stale_cache_hit(self):
        """Confirm the view serves from cache even if the DB is changed externally."""
        obj_url = f"{self.path}{self.user.id}/"
        view = self._prepare_view('aretrieve', url=obj_url, kwargs={'pk': self.user.id})
        
        # Warm cache
        await view.aretrieve(view.request, pk=self.user.id)
        
        # DB manipulation
        await User.objects.filter(id=self.user.id).aupdate(username="hacker_change")
        
        # Result should still be the setup username
        response = await view.aretrieve(view.request, pk=self.user.id)
        self.assertEqual(response.data['username'], self.username)

    async def test_failed_validation_no_cache_poisoning(self):
        """Failed updates should not change the cache."""
        obj_url = f"{self.path}{self.user.id}/"
        m_hash = await CacheUtils.get_model_hash(UserViewSet())
        obj_key = f"obj:{m_hash}:{self.user.id}"

        # Warm cache
        view_ret = self._prepare_view('aretrieve', url=obj_url, kwargs={'pk': self.user.id})
        await view_ret.aretrieve(view_ret.request, pk=self.user.id)

        # Fail update
        view_bad = self._prepare_view('aupdate', method='patch', url=obj_url, 
                                     data={"username": ""}, kwargs={'pk': self.user.id})
        with self.assertRaises(ValidationError):
            await view_bad.aupdate(view_bad.request, pk=self.user.id)

        # Cache remains unchanged
        cached_val = await cache.aget(obj_key)
        self.assertEqual(cached_val['username'], self.username)

    async def test_query_param_ordering_stability(self):
        """?a=1&b=2 must equal ?b=2&a=1."""
        v1 = self._prepare_view('alist', url=f"{self.path}?first=1&second=2")
        key1 = await CacheUtils.generate_list_key(v1.request)

        v2 = self._prepare_view('alist', url=f"{self.path}?second=2&first=1")
        key2 = await CacheUtils.generate_list_key(v2.request)

        self.assertEqual(key1, key2, "Cache keys must be order-insensitive.")

    async def test_list_query_params_isolation(self):
        """Ensure ?page=1 and ?page=2 produce distinct cache entries."""
        # Call Page 1
        v1 = self._prepare_view('alist', url=f"{self.path}?page=1")
        await v1.alist(v1.request)
        key1 = await CacheUtils.generate_list_key(v1.request)

        # Call Page 2
        v2 = self._prepare_view('alist', url=f"{self.path}?page=2")
        await v2.alist(v2.request)
        key2 = await CacheUtils.generate_list_key(v2.request)

        self.assertNotEqual(key1, key2, "Cache keys must differ based on query parameters.")

    async def test_unauthorized_list_caching(self):
        """Verify guests get a different cache key structure than authenticated users."""
        
        # 1. Authenticated call (User already set in setUp)
        v_auth = self._prepare_view('alist')
        key_auth = await CacheUtils.generate_list_key(v_auth.request)

        # 2. Logout / Switch to Guest
        # We wrap the sync call to avoid SynchronousOnlyOperation
        await sync_to_async(self.client.force_authenticate)(user=None)
        
        # 3. Guest call
        v_guest = self._prepare_view('alist')
        key_guest = await CacheUtils.generate_list_key(v_guest.request)

        self.assertNotEqual(key_auth, key_guest)

    # --- OBJECT CACHING: DEEP DIVE ---

    async def test_retrieve_integrity_after_direct_db_manipulation(self):
        """Verify that retrieve strictly follows cache even if DB is modified externally."""
        obj_url = f"{self.path}{self.user.id}/"
        view = self._prepare_view('retrieve', url=obj_url, kwargs={'pk': self.user.id})
        
        # 1. Warm up cache
        await view.aretrieve(view.request, pk=self.user.id)
        
        # 2. Modify DB directly (bypassing Mixins)
        await User.objects.filter(id=self.user.id).aupdate(username="db_only_change")
        
        # 3. Request again: should return cached "primary_user"
        response = await view.aretrieve(view.request, pk=self.user.id)
        self.assertEqual(response.data['username'], "primary_user", "Should serve from cache, ignoring DB change.")

    async def test_partial_update_refreshes_object_cache(self):
        """Check if PATCH correctly updates the existing object cache entry."""
        obj_url = f"{self.path}{self.user.id}/"
        m_hash = await CacheUtils.get_model_hash(UserViewSet())
        obj_key = f"obj:{m_hash}:{self.user.id}"

        # 1. Populate initial cache
        view_ret = self._prepare_view('retrieve', url=obj_url, kwargs={'pk': self.user.id})
        await view_ret.aretrieve(view_ret.request, pk=self.user.id)

        # 2. Patch
        view_patch = self._prepare_view('patch', method='patch', url=obj_url, 
                                        data={"username": "patched_name"}, kwargs={'pk': self.user.id})
        await view_patch.aupdate(view_patch.request, pk=self.user.id)

        # 3. Verify cache is fresh
        cached_val = await cache.aget(obj_key)
        self.assertEqual(cached_val['username'], "patched_name")

    # --- CROSS-ENTITY INVALIDATION ---

    async def test_create_invalidates_all_user_lists(self):
        """Every list cache key for the user must be invalidated on acreate."""
        view_list = self._prepare_view('alist')
        await view_list.alist(view_list.request)
        key_before = await CacheUtils.generate_list_key(view_list.request)
        self.assertTrue(await cache.adelete(key_before), "Cache should exist before creation")

        # Create new user
        view_create = self._prepare_view('acreate', method='post', data={"username": "new_guy"})
        await view_create.acreate(view_create.request)

        # Key should now be different
        key_after = await CacheUtils.generate_list_key(view_list.request)
        self.assertNotEqual(key_before, key_after)
        self.assertIsNone(await cache.aget(key_after), "New versioned key should be empty.")

    async def test_user_version_isolation(self):
        """Verify that User A creating an object does NOT invalidate User B's list cache."""
        # 1. Store User A's list key
        v_a = self._prepare_view('alist')
        await v_a.alist(v_a.request)
        key_a_before = await CacheUtils.generate_list_key(v_a.request)

        # 2. Switch to User B
        user_b = await sync_to_async(User.objects.create_user)(username="user_b")
        await sync_to_async(self.client.force_authenticate)(user=user_b)
        
        # 3. User B creates an object
        v_b_create = self._prepare_view('acreate', method='post', data={"username": "b_item"})
        await v_b_create.acreate(v_b_create.request)

        # 4. Check User A's key again
        await sync_to_async(self.client.force_authenticate)(user=self.user)
        key_a_after = await CacheUtils.generate_list_key(v_a.request)

        self.assertEqual(key_a_before, key_a_after, "User B's activity should not affect User A's list version.")

    # --- 2. VALIDATION FAILURE INTEGRITY ---

    async def test_failed_update_does_not_corrupt_cache(self):
        """Verify that if a serializer fails validation, the cache is NOT updated."""
        obj_url = f"{self.path}{self.user.id}/"
        m_hash = await CacheUtils.get_model_hash(UserViewSet())
        obj_key = f"obj:{m_hash}:{self.user.id}"

        # 1. Populate cache with valid data
        view_ret = self._prepare_view('retrieve', url=obj_url, kwargs={'pk': self.user.id})
        await view_ret.aretrieve(view_ret.request, pk=self.user.id)

        # 2. Attempt update with INVALID data
        v_bad_upd = self._prepare_view('patch', method='patch', url=obj_url, 
                                    data={"username": ""}, kwargs={'pk': self.user.id})
        
        # We expect a ValidationError to be raised by the serializer
        with self.assertRaises(ValidationError):
            await v_bad_upd.aupdate(v_bad_upd.request, pk=self.user.id)

        # 3. Verify cache STILL contains the ORIGINAL name
        # This proves the cache didn't get poisoned by a failed request
        cached_val = await cache.aget(obj_key)
        self.assertEqual(cached_val['username'], "primary_user", 
                        "Cache must stay stale/correct even if the update request fails.")

    # --- 3. DESTROY INVALIDATION ---

    async def test_destroy_invalidates_both_object_and_list(self):
        """Deleting an object must remove its cache AND bump the list version."""
        obj_url = f"{self.path}{self.user.id}/"
        m_hash = await CacheUtils.get_model_hash(UserViewSet())
        obj_key = f"obj:{m_hash}:{self.user.id}"

        # 1. Warm list and object cache
        v_list = self._prepare_view('alist')
        await v_list.alist(v_list.request)
        list_key_before = await CacheUtils.generate_list_key(v_list.request)
        
        v_ret = self._prepare_view('retrieve', url=obj_url, kwargs={'pk': self.user.id})
        await v_ret.aretrieve(v_ret.request, pk=self.user.id)

        # 2. Destroy the object
        v_del = self._prepare_view('delete', method='delete', url=obj_url, kwargs={'pk': self.user.id})
        await v_del.adestroy(v_del.request, pk=self.user.id)

        # 3. Assert Object Cache is GONE
        self.assertIsNone(await cache.aget(obj_key))

        # 4. Assert List Version is BUMPED
        list_key_after = await CacheUtils.generate_list_key(v_list.request)
        self.assertNotEqual(list_key_before, list_key_after, "List version must bump after deletion.")

    # --- 4. QUERY PARAMETER NORMALIZATION ---

    async def test_list_query_param_ordering_stability(self):
        """?a=1&b=2 should ideally equal ?b=2&a=1 to avoid cache fragmentation."""
        url_a = f"{self.path}?first=1&second=2"
        url_b = f"{self.path}?second=2&first=1"

        v_a = self._prepare_view('alist', url=url_a)
        key_a = await CacheUtils.generate_list_key(v_a.request)

        v_b = self._prepare_view('alist', url=url_b)
        key_b = await CacheUtils.generate_list_key(v_b.request)

        self.assertEqual(key_a, key_b, "Cache keys should be identical regardless of query parameter order.")


if __name__ == "__main__":
    unittest.main()
