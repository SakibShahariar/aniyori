"""Tests for the bounded persistent AniList metadata cache."""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from aniyori.services.metadata_cache import MetadataCache


class MetadataCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = MetadataCache(self.temp_dir.name, ttl=60, max_entries=2)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_xdg_cache_home_uses_default_cache_directory(self):
        with patch.dict("os.environ", {"XDG_CACHE_HOME": ""}):
            with patch("pathlib.Path.home", return_value=Path("/home/test")):
                cache = MetadataCache()
        self.assertEqual(cache.directory, Path("/home/test/.cache/aniyori/metadata"))

    def test_round_trips_json_values_and_reports_freshness(self):
        value = [{"id": 21, "title": "Example", "genres": ["Adventure"]}]
        self.cache.set("search", "example", value)

        self.assertEqual(self.cache.get("search", "example"), (value, True))

    def test_expired_entries_remain_available_as_stale_fallback(self):
        cache = MetadataCache(self.temp_dir.name, ttl=0)
        cache.set("details", "21", {"id": 21, "title": "Example"})

        result = cache.get("details", "21")

        self.assertIsNotNone(result)
        self.assertEqual(result[0]["id"], 21)
        self.assertFalse(result[1])

    def test_corrupt_timestamps_are_discarded(self):
        invalid_timestamps = (True, -1, 10**400, float("inf"), float("nan"))
        for index, timestamp in enumerate(invalid_timestamps):
            with self.subTest(timestamp=repr(timestamp)):
                key = f"invalid-{index}"
                path = self.cache._path("details", key)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    __import__("json").dumps(
                        {"stored_at": timestamp, "value": {"id": index}}
                    ),
                    encoding="utf-8",
                )
                self.assertIsNone(self.cache.get("details", key))
                self.assertFalse(path.exists())

    def test_namespaces_and_keys_do_not_collide(self):
        self.cache.set("search", "21", {"kind": "search"})
        self.cache.set("details", "21", {"kind": "details"})

        self.assertEqual(self.cache.get("search", "21")[0]["kind"], "search")
        self.assertEqual(self.cache.get("details", "21")[0]["kind"], "details")

    def test_cache_prunes_oldest_entries_to_configured_limit(self):
        self.cache.set("details", "one", {"id": 1})
        self.cache.set("details", "two", {"id": 2})
        self.cache.set("details", "three", {"id": 3})

        files = list(Path(self.temp_dir.name).glob("*.json"))
        self.assertEqual(len(files), 2)
        self.assertIsNone(self.cache.get("details", "one"))
        self.assertIsNotNone(self.cache.get("details", "three"))

    def test_clear_removes_metadata_entries(self):
        self.cache.set("search", "example", [{"id": 1}])
        self.cache.clear()

        self.assertEqual(list(Path(self.temp_dir.name).glob("*.json")), [])

    def test_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            MetadataCache(self.temp_dir.name, ttl=-1)
        with self.assertRaises(ValueError):
            MetadataCache(self.temp_dir.name, max_entries=0)


if __name__ == "__main__":
    unittest.main()
