"""Tests for per-anime download preference overrides."""

import tempfile
import unittest
from pathlib import Path

from aniyori.services.anime_release_preferences import (
    AnimeReleasePreferenceError, AnimeReleasePreferenceStore,
    normalize_anime_release_preference,
)


class AnimeReleasePreferenceTests(unittest.TestCase):
    def test_round_trip_persists_overrides_privately(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AnimeReleasePreferenceStore(Path(directory) / "anime-prefs.json")
            store.save_for(42, {
                "enabled": False,
                "min_file_size_mb": 100,
                "max_file_size_mb": 800,
                "preferences": {
                    "resolution": {"preferred": ["1080p"], "rejected": ["480p"]},
                    "release_group": {"preferred": ["Group A"]},
                },
            })
            loaded = store.load_for(42)
            self.assertFalse(loaded["enabled"])
            self.assertEqual(loaded["min_file_size_mb"], 100.0)
            self.assertEqual(loaded["max_file_size_mb"], 800.0)
            self.assertEqual(loaded["preferences"]["resolution"]["preferred"], ["1080p"])
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_missing_anime_inherits_defaults_and_reset_removes_override(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AnimeReleasePreferenceStore(Path(directory) / "anime-prefs.json")
            self.assertTrue(store.load_for(7)["enabled"])
            store.save_for(7, {"enabled": False})
            self.assertTrue(store.reset_for(7))
            self.assertFalse(store.reset_for(7))
            self.assertTrue(store.load_for(7)["enabled"])

    def test_per_anime_attributes_remain_partial_for_global_inheritance(self):
        normalized = normalize_anime_release_preference({
            "preferences": {"resolution": {"preferred": ["1080p"]}}
        })
        self.assertEqual(list(normalized["preferences"]), ["resolution"])

    def test_rejects_invalid_size_ranges_and_preferences(self):
        for value in (
            {"min_file_size_mb": 100, "max_file_size_mb": 10},
            {"enabled": "false"},
            {"preferences": {"unknown": {"preferred": ["x"]}}},
            {"min_file_size_mb": float("nan")},
        ):
            with self.subTest(value=value), self.assertRaises(AnimeReleasePreferenceError):
                normalize_anime_release_preference(value)

    def test_rejects_invalid_library_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AnimeReleasePreferenceStore(Path(directory) / "anime-prefs.json")
            with self.assertRaises(AnimeReleasePreferenceError):
                store.save_for(0, {})


if __name__ == "__main__":
    unittest.main()
