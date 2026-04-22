import pytest
import asyncio
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate
from adrf.serializers import ModelSerializer
from django.contrib.auth.models import AnonymousUser

from adrf_caching.viewsets import ModelViewSetCached
from adrf_caching.utils import cache, lib_settings, CacheUtils

User = get_user_model()

# --- Mock Models & Serializers ---

class MockModel(models.Model):
    __test__ = False
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, default="general")
    owner_id = models.IntegerField(null=True)
    secondary_owner_id = models.IntegerField(null=True)

    class Meta:
        app_label = 'tests'

class MockSerializer(ModelSerializer):
    __test__ = False
    class Meta:
        model = MockModel
        fields = '__all__'

class MockViewSet(ModelViewSetCached):
    __test__ = False
    queryset = MockModel.objects.all()
    serializer_class = MockSerializer

class MultiOwnerViewSet(MockViewSet):
    invalidate_fields = ['owner_id', 'secondary_owner_id']

class BadConfigViewSet(MockViewSet):
    invalidate_fields = ['non_existent_field']

# --- Advanced Test Suite ---

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestCachierPro:
    """
    Production-grade test suite for adrf-caching.
    Covers: Key stability, User isolation, Atomic invalidation, and Race conditions.
    """

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.factory = APIRequestFactory()
        self.user = await User.objects.acreate(username="dev_user")
        self.other_user = await User.objects.acreate(username="other_user")
        self.view_list = MockViewSet.as_view({'get': 'alist', 'post': 'acreate'})
        self.view_detail = MockViewSet.as_view({
            'get': 'aretrieve', 
            'put': 'aupdate', 
            'patch': 'partial_aupdate',
            'delete': 'adestroy'
        })
        await cache.aclear()

    # --- 1. Key Integrity & Determinism ---

    async def test_key_determinism_and_sorting(self):
        """Ensure keys are stable regardless of query param order (RFC 7234 compliance)."""
        urls = [
            '/api/?page=1&sort=name&filter=active',
            '/api/?filter=active&page=1&sort=name',
            '/api/?sort=name&filter=active&page=1'
        ]
        keys = []
        for url in urls:
            req = self.factory.get(url)
            req.user = self.user
            keys.append(await CacheUtils.generate_list_key(req, view=MockViewSet()))
        
        assert len(set(keys)) == 1, "Cache keys must be identical for reordered params"

    async def test_key_isolation_between_users(self):
        """Strict check: User A must never hit User B's cache."""
        req_a = self.factory.get('/api/')
        req_a.user = self.user
        key_a = await CacheUtils.generate_list_key(req_a, view=MockViewSet())

        req_b = self.factory.get('/api/')
        req_b.user = self.other_user
        key_b = await CacheUtils.generate_list_key(req_b, view=MockViewSet())

        assert key_a != key_b
        assert str(self.user.id) in key_a
        assert str(self.other_user.id) in key_b

    # --- 2. Granular Invalidation Logic ---

    async def test_patch_updates_cache_partially(self):
        """Verify PATCH correctly updates object cache without full re-creation."""
        obj = await MockModel.objects.acreate(name="Initial", category="test")
        obj_key = await CacheUtils.get_model_hash(MockViewSet())
        full_key = f"{lib_settings.PREFIX}:obj:{obj_key}:{obj.id}"

        # Warm up
        await cache.aset(full_key, {'id': obj.id, 'name': 'Initial', 'category': 'test'})

        # Patch only name
        req = self.factory.patch(f'/{obj.id}/', {'name': 'Patched'})
        force_authenticate(req, user=self.user)
        await self.view_detail(req, pk=obj.id)

        cached = await cache.aget(full_key)
        assert cached['name'] == 'Patched'
        assert cached['category'] == 'test', "Unchanged fields must persist in cache"

    async def test_delete_cascades_to_list_invalidation(self):
        """Deleting an object must invalidate ALL lists for that user (version bump)."""
        # 1. Capture initial version
        v_start = await CacheUtils.get_user_version(self.user.id)
        
        # 2. Create object WITH owner_id (теперь миксин увидит владельца)
        obj = await MockModel.objects.acreate(name="Short-lived", owner_id=self.user.id)
        
        # 3. Delete through API
        req = self.factory.delete(f'/{obj.id}/')
        force_authenticate(req, user=self.user)
        await self.view_detail(req, pk=obj.id)

        # 4. Check version increment
        v_end = await CacheUtils.get_user_version(self.user.id)
        assert v_end > v_start, "Version must increment after object deletion"

    # --- 3. Performance & Resilience ---

    async def test_db_bypass_verification(self):
        """
        The 'Gold Standard' test: Prove the database isn't even touched on a cache hit.
        """
        obj = await MockModel.objects.acreate(name="Real DB Name")
        model_hash = await CacheUtils.get_model_hash(MockViewSet())
        obj_key = f"{lib_settings.PREFIX}:obj:{model_hash}:{obj.id}"
        
        # Inject "poisoned" data into cache
        await cache.aset(obj_key, {'id': obj.id, 'name': 'I AM FROM CACHE'})

        req = self.factory.get(f'/{obj.id}/')
        # We don't even need force_authenticate here if caching is public
        resp = await self.view_detail(req, pk=obj.id)
        
        assert resp.status_code == 200
        assert resp.data['name'] == 'I AM FROM CACHE', "Response data must come from cache, bypassing DB"

    async def test_high_concurrency_initialization(self):
        """Simulate a 'Thundering Herd' for user version initialization."""
        new_user_id = 9999
        # Fire 50 concurrent requests to get/init version
        results = await asyncio.gather(*(
            CacheUtils.get_user_version(new_user_id) for _ in range(50)
        ))
        
        assert all(v == 1 for v in results), "All concurrent requests should see the same initial version"
        # Verify it's actually in Redis
        assert await cache.aget(f"u_ver:{new_user_id}") == 1

    # --- 4. Anonymous User Constraints ---

    async def test_anonymous_shared_cache_stable(self):
        """Anon users should share 'v0' cache and NOT affect each other's versions."""
        req = self.factory.get('/api/')
        req.user = AnonymousUser()
        
        key1 = await CacheUtils.generate_list_key(req, view=MockViewSet())
        
        # Simulate some activity
        await MockModel.objects.acreate(name="New Stuff")
        
        key2 = await CacheUtils.generate_list_key(req, view=MockViewSet())
        assert key1 == key2, "Anonymous cache version must remain v0 (Shared Cache)"

    async def test_multi_owner_invalidation(self):
        """Verify that multiple owners get their cache invalidated simultaneously."""
        user1_id = self.user.id
        user2_id = self.other_user.id
        
        v1_start = await CacheUtils.get_user_version(user1_id)
        v2_start = await CacheUtils.get_user_version(user2_id)

        # Create object belonging to both users directly in the DB
        obj = await MockModel.objects.acreate(
            name="Shared", 
            owner_id=user1_id,
            secondary_owner_id=user2_id
        )
        
        # Use custom viewset for the test
        view = MultiOwnerViewSet.as_view({'delete': 'adestroy'})
        
        req = self.factory.delete(f'/{obj.id}/')
        force_authenticate(req, user=self.user)
        
        # Call deletion through viewset with two invalidation fields
        await view(req, pk=obj.id)

        assert (await CacheUtils.get_user_version(user1_id)) > v1_start
        assert (await CacheUtils.get_user_version(user2_id)) > v2_start

    async def test_fallback_to_request_user(self):
        """If invalidate_fields is empty, fallback to the person making the request."""
        v_start = await CacheUtils.get_user_version(self.user.id)
        
        obj = await MockModel.objects.acreate(name="No fields")
        req = self.factory.delete(f'/{obj.id}/')
        force_authenticate(req, user=self.user)
        
        await self.view_detail(req, pk=obj.id)
        
        v_end = await CacheUtils.get_user_version(self.user.id)
        assert v_end > v_start, "Should fallback to request.user when fields are empty"

    async def test_improper_configuration_raises_error(self):
        """Ensure the system crashes loudly if developer provides a wrong field name."""
        obj = await MockModel.objects.acreate(name="Error Test")
        view = BadConfigViewSet.as_view({'put': 'aupdate'})
        
        req = self.factory.put(f'/{obj.id}/', {'name': 'Broken'})
        force_authenticate(req, user=self.user)

        with pytest.raises(ImproperlyConfigured) as exc:
            await view(req, pk=obj.id)
        
        assert "non_existent_field" in str(exc.value)
