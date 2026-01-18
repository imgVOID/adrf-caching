import unittest
from hashlib import md5
from unittest.mock import MagicMock

from django.test import TransactionTestCase
from django.core.cache import cache

from adrf_caching.utils import CacheUtils


class TestCacheUtilsUnit(TransactionTestCase):
    def setUp(self):
        cache.clear()

    # --- 1. MODEL HASHING ---

    async def test_get_model_hash_logic(self):
        """Verify hash is md5 of lowercase model name."""
        mock_view = MagicMock()
        mock_serializer = MagicMock()
        # Mocking the Meta.model.__name__ path used in your code
        mock_serializer.Meta.model.__name__ = "User"
        mock_view.get_serializer_class.return_value = mock_serializer

        result = await CacheUtils.get_model_hash(mock_view)
        expected = md5("user".encode()).hexdigest()
        
        self.assertEqual(result, expected)

    # --- 2. USER VERSIONING ---

    async def test_get_user_version_initialization(self):
        """Should return 1 and persist to cache if missing."""
        version = await CacheUtils.get_user_version(user_id=1)
        self.assertEqual(version, 1)
        
        # Verify it actually hit the cache
        self.assertEqual(await cache.aget("u_ver:1"), 1)

    async def test_incr_user_version_logic(self):
        """Should handle both existing and missing keys."""
        # Case: Key exists
        await cache.aset("u_ver:1", 10)
        await CacheUtils.incr_user_version(1)
        self.assertEqual(await cache.aget("u_ver:1"), 11)

        # Case: Key missing (triggers the try/except in your code)
        await CacheUtils.incr_user_version(99)
        self.assertEqual(await cache.aget("u_ver:99"), 2)

    # --- 3. LIST KEY GENERATION ---

    async def test_generate_list_key_params_sorting(self):
        """?a=1&b=2 must produce the same key as ?b=2&a=1."""
        mock_view = MagicMock()
        mock_ser = MagicMock()
        mock_ser.Meta.model.__name__ = "User"
        mock_view.get_serializer_class.return_value = mock_ser

        def setup_req(params):
            req = MagicMock()
            req.user.is_authenticated = False
            req.query_params.items.return_value = params.items()
            req.parser_context = {'view': mock_view}
            return req

        key_1 = await CacheUtils.generate_list_key(setup_req({'page': '1', 'sort': 'id'}))
        key_2 = await CacheUtils.generate_list_key(setup_req({'sort': 'id', 'page': '1'}))

        self.assertEqual(key_1, key_2)

    async def test_generate_list_key_anonymous_suffix(self):
        """
        Anonymous keys end in ':v0'.
        The 'anonymous' string is assigned to user_id but not used in the return f-string.
        """
        mock_view = MagicMock()
        mock_ser = MagicMock()
        mock_ser.Meta.model.__name__ = "User"
        mock_view.get_serializer_class.return_value = mock_ser

        req = MagicMock()
        req.user.is_authenticated = False
        req.query_params.items.return_value = {}.items()
        req.parser_context = {'view': mock_view}

        key = await CacheUtils.generate_list_key(req)
        self.assertTrue(key.endswith(":v0"))
        self.assertNotIn("anonymous", key) 


if __name__ == "__main__":
    unittest.main()
