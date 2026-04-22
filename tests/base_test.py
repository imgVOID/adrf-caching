import pytest
from django.db import models
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate
from adrf.serializers import ModelSerializer

from adrf_caching.viewsets import ModelViewSetCached
from adrf_caching.utils import cache, lib_settings, CacheUtils
from adrf_caching.mixins import CacheInvalidationMixin

User = get_user_model()

# --- Test Models & Serializers ---

class TestModel(models.Model):
    """
    Standard model for testing basic cache invalidation.
    """
    __test__ = False
    name = models.CharField(max_length=100)
    owner_id = models.IntegerField(null=True)

    class Meta:
        app_label = 'tests'  # Critical for table discovery in pytest


class TestSerializer(ModelSerializer):
    """
    Standard serializer for basic cache testing.
    """
    __test__ = False
    class Meta:
        model = TestModel
        fields = ['id', 'name', 'owner_id']


class TestViewSet(ModelViewSetCached):
    """
    Cached ViewSet using standard ModelViewSetCached logic.
    """
    __test__ = False
    queryset = TestModel.objects.all()
    serializer_class = TestSerializer


# --- Basic Invalidation Tests ---

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestCacheInvalidationHandlers:
    """
    Tests for basic CRUD cache invalidation and isolated caching.
    """

    @pytest.fixture(autouse=True)
    async def setup_test(self):
        self.factory = APIRequestFactory()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user, _ = await User.objects.aget_or_create(username="cleaner")
        
        # Initialize view methods
        self.view_list = TestViewSet.as_view({'get': 'alist', 'post': 'acreate'})
        self.view_detail = TestViewSet.as_view({
            'get': 'aretrieve', 
            'put': 'aupdate', 
            'patch': 'partial_aupdate', 
            'delete': 'adestroy'
        })
        await cache.aclear()

    async def _get_list_key(self, path='/test/'):
        request = self.factory.get(path)
        request.user = self.user 
        return await CacheUtils.generate_list_key(request, view=TestViewSet())

    async def _get_obj_key(self, obj_id):
        m_hash = await CacheUtils.get_model_hash(TestViewSet())
        return f"{lib_settings.PREFIX}:obj:{m_hash}:{obj_id}"

    # --- 1. CREATE ---
    async def test_create_invalidates_list(self):
        """
        Verify that creating an object increments the user version and changes the list cache key.
        """
        # Warm up the list cache
        req = self.factory.get('/test/')
        force_authenticate(req, user=self.user)
        await self.view_list(req)
        
        key_v1 = await self._get_list_key()
        assert await cache.aget(key_v1) is not None

        # Create new object
        req_post = self.factory.post('/test/', {'name': 'New'})
        force_authenticate(req_post, user=self.user)
        await self.view_list(req_post)

        # Key must change
        key_v2 = await self._get_list_key()
        assert key_v1 != key_v2
        assert await cache.aget(key_v2) is None

    # --- 2. UPDATE (PUT) ---
    async def test_update_updates_obj_and_invalidates_list(self):
        """
        Verify that a PUT request updates the object cache directly and invalidates list versions.
        """
        obj = await TestModel.objects.acreate(name="Old", owner_id=self.user.id)
        obj_key = await self._get_obj_key(obj.id)
        list_key_v1 = await self._get_list_key()

        # Warm up retrieve and list
        req_det = self.factory.get(f'/test/{obj.id}/')
        force_authenticate(req_det, user=self.user)
        await self.view_detail(req_det, pk=obj.id)
        
        req_list = self.factory.get('/test/')
        force_authenticate(req_list, user=self.user)
        await self.view_list(req_list)

        # Update object
        req_put = self.factory.put(f'/test/{obj.id}/', {'name': 'Updated'})
        force_authenticate(req_put, user=self.user)
        await self.view_detail(req_put, pk=obj.id)

        # Object check: data in cache must be updated
        cached_obj = await cache.aget(obj_key)
        assert cached_obj['name'] == 'Updated'

        # List check: version must be incremented
        list_key_v2 = await self._get_list_key()
        assert list_key_v1 != list_key_v2

    # --- 3. PARTIAL UPDATE (PATCH) ---
    async def test_patch_invalidates_correctly(self):
        """
        Verify that PATCH requests correctly update the cached object data.
        """
        obj = await TestModel.objects.acreate(name="PatchMe", owner_id=self.user.id)
        obj_key = await self._get_obj_key(obj.id)
        
        req_patch = self.factory.patch(f'/test/{obj.id}/', {'name': 'Patched'})
        force_authenticate(req_patch, user=self.user)
        await self.view_detail(req_patch, pk=obj.id)

        cached_obj = await cache.aget(obj_key)
        assert cached_obj['name'] == 'Patched'

    # --- 4. DESTROY ---
    async def test_destroy_removes_obj_and_invalidates_list(self):
        """
        Verify that DELETE requests remove the object from cache and reset list versions.
        """
        obj = await TestModel.objects.acreate(name="ToDie", owner_id=self.user.id)
        obj_key = await self._get_obj_key(obj.id)
        list_key_v1 = await self._get_list_key()

        # Retrieve
        req_det = self.factory.get(f'/test/{obj.id}/')
        force_authenticate(req_det, user=self.user)
        await self.view_detail(req_det, pk=obj.id)
        assert await cache.aget(obj_key) is not None

        # Delete
        req_del = self.factory.delete(f'/test/{obj.id}/')
        force_authenticate(req_del, user=self.user)
        await self.view_detail(req_del, pk=obj.id)

        # Key must be gone, list must be invalidated
        assert await cache.aget(obj_key) is None
        # The list must change version
        list_key_v2 = await self._get_list_key()
        assert list_key_v1 != list_key_v2

    async def test_query_params_hashing(self):
        """
        Verify that query parameters are correctly hashed and sorted to prevent cache duplication.
        """
        key_a = await self._get_list_key('/test/?name=Item1')
        key_b = await self._get_list_key('/test/?name=Item2')
        assert key_a != key_b
        
        # Order stability check
        key_c1 = await self._get_list_key('/test/?name=A&owner=1')
        key_c2 = await self._get_list_key('/test/?owner=1&name=A')
        assert key_c1 == key_c2
        
        # Separation check
        req_a = self.factory.get('/test/?name=Item1')
        force_authenticate(req_a, user=self.user)
        await cache.aset(key_a, {'results': ['item1']}, timeout=300)
        assert await cache.aget(key_b) is None

    async def test_anonymous_user_caching(self):
        """
        Verify that anonymous users use a shared 'v0' version and are isolated from authenticated users.
        """
        from django.contrib.auth.models import AnonymousUser
        request_anon = self.factory.get('/test/')
        request_anon.user = AnonymousUser()
        
        key_anon = await CacheUtils.generate_list_key(request_anon, view=TestViewSet())
        assert ":anon:v0:" in key_anon

        key_user = await self._get_list_key('/test/')
        assert key_anon != key_user
        
        # Create object from auth user
        req_post = self.factory.post('/test/', {'name': 'New'})
        force_authenticate(req_post, user=self.user)
        await self.view_list(req_post)
        
        # Anon key must remain unchanged (always v0)
        key_anon_after = await CacheUtils.generate_list_key(request_anon, view=TestViewSet())
        assert key_anon == key_anon_after

# --- Multi-Owner Test Infrastructure ---

class MultiOwnerModel(models.Model):
    """
    Model simulating shared resources (e.g., Psychologist and Patient).
    """
    __test__ = False
    name = models.CharField(max_length=100)
    user_one_id = models.IntegerField()
    user_two_id = models.IntegerField()

    class Meta:
        app_label = 'tests'


class MultiOwnerSerializer(ModelSerializer):
    """
    Serializer for multi-owner model.
    """
    __test__ = False
    class Meta:
        model = MultiOwnerModel
        fields = ['id', 'name', 'user_one_id', 'user_two_id']


class MultiOwnerViewSet(CacheInvalidationMixin, ModelViewSetCached):
    """
    ViewSet utilizing CacheInvalidationMixin for distributed invalidation.
    """
    __test__ = False
    queryset = MultiOwnerModel.objects.all()
    serializer_class = MultiOwnerSerializer
    invalidate_fields = ['user_one_id', 'user_two_id']


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestMultiOwnerInvalidation:
    """
    Targeted tests for Multi-Owner invalidation triggers.
    """

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.factory = APIRequestFactory()
        self.user1, _ = await User.objects.aget_or_create(username="user1")
        self.user2, _ = await User.objects.aget_or_create(username="user2")
        await cache.aclear()

    async def test_create_invalidates_multiple_users(self):
        """
        Verify that creating an object invalidates versions for all linked users.
        """
        view = MultiOwnerViewSet.as_view({'post': 'acreate'})
        v1_initial = await CacheUtils.get_user_version(self.user1.id)
        v2_initial = await CacheUtils.get_user_version(self.user2.id)

        data = {'name': 'Shared', 'user_one_id': self.user1.id, 'user_two_id': self.user2.id}
        request = self.factory.post('/multi/', data)
        force_authenticate(request, user=self.user1)
        await view(request)

        assert await CacheUtils.get_user_version(self.user1.id) > v1_initial
        assert await CacheUtils.get_user_version(self.user2.id) > v2_initial

    async def test_destroy_invalidates_multiple_users(self):
        """
        Verify that deletion triggers invalidation for all owners before the object is purged.
        """
        obj = await MultiOwnerModel.objects.acreate(
            name="DeleteMe", user_one_id=self.user1.id, user_two_id=self.user2.id
        )
        view = MultiOwnerViewSet.as_view({'delete': 'adestroy'})
        v1_before = await CacheUtils.get_user_version(self.user1.id)
        v2_before = await CacheUtils.get_user_version(self.user2.id)

        request = self.factory.delete(f'/multi/{obj.id}/')
        force_authenticate(request, user=self.user1)
        await view(request, pk=obj.id)

        assert await CacheUtils.get_user_version(self.user1.id) > v1_before
        assert await CacheUtils.get_user_version(self.user2.id) > v2_before


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestMultiOwnerFullCycle:
    """
    Scenario-based test covering the full CRUD lifecycle of a multi-owner resource.
    """

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.factory = APIRequestFactory()
        self.u1, _ = await User.objects.aget_or_create(username="u1")
        self.u2, _ = await User.objects.aget_or_create(username="u2")
        self.u3, _ = await User.objects.aget_or_create(username="u3")
        
        self.view_list = MultiOwnerViewSet.as_view({'post': 'acreate'})
        self.view_detail = MultiOwnerViewSet.as_view({
            'put': 'aupdate', 
            'patch': 'partial_aupdate', 
            'delete': 'adestroy'
        })
        await cache.aclear()

    async def test_multi_owner_scenario(self):
        """
        Full scenario: Create (u1, u2) -> Patch owner (u2 to u3) -> Update -> Delete.
        Ensures appropriate invalidation at every state transition.
        """
        # Step 1: Create
        v1 = await CacheUtils.get_user_version(self.u1.id)
        v2 = await CacheUtils.get_user_version(self.u2.id)
        
        data = {'name': 'Init', 'user_one_id': self.u1.id, 'user_two_id': self.u2.id}
        req = self.factory.post('/multi/', data)
        force_authenticate(req, user=self.u1)
        resp = await self.view_list(req)
        obj_id = resp.data['id']

        assert await CacheUtils.get_user_version(self.u1.id) > v1
        assert await CacheUtils.get_user_version(self.u2.id) > v2

        # Step 2: Patch (Transfer ownership from u2 to u3)
        v1 = await CacheUtils.get_user_version(self.u1.id)
        v3 = await CacheUtils.get_user_version(self.u3.id)
        
        req_patch = self.factory.patch(f'/multi/{obj_id}/', {'user_two_id': self.u3.id})
        force_authenticate(req_patch, user=self.u1)
        await self.view_detail(req_patch, pk=obj_id)

        assert await CacheUtils.get_user_version(self.u1.id) > v1
        assert await CacheUtils.get_user_version(self.u3.id) > v3

        # Step 3: Put
        v1 = await CacheUtils.get_user_version(self.u1.id)
        v3 = await CacheUtils.get_user_version(self.u3.id)
        
        data_update = {'name': 'Updated', 'user_one_id': self.u1.id, 'user_two_id': self.u3.id}
        req_put = self.factory.put(f'/multi/{obj_id}/', data_update)
        force_authenticate(req_put, user=self.u1)
        await self.view_detail(req_put, pk=obj_id)

        assert await CacheUtils.get_user_version(self.u1.id) > v1
        assert await CacheUtils.get_user_version(self.u3.id) > v3

        # Step 4: Delete
        v1 = await CacheUtils.get_user_version(self.u1.id)
        v3 = await CacheUtils.get_user_version(self.u3.id)
        
        req_del = self.factory.delete(f'/multi/{obj_id}/')
        force_authenticate(req_del, user=self.u1)
        await self.view_detail(req_del, pk=obj_id)

        assert await CacheUtils.get_user_version(self.u1.id) > v1
        assert await CacheUtils.get_user_version(self.u3.id) > v3

