"""Tests for persistent local media scan folder configuration."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aniyori.services.scan_locations import (
    ScanLocationStore, default_scan_locations_path, normalize_scan_location,
)


class ScanLocationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config = self.root / "config" / "scan-locations.json"
        self.store = ScanLocationStore(self.config)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_configuration_is_empty(self):
        self.assertEqual(self.store.list_locations(), ())

    def test_add_and_reload_locations(self):
        first, second = self.root / "Anime", self.root / "Other Anime"
        self.assertTrue(self.store.add_location(first))
        self.assertTrue(self.store.add_location(second))
        self.assertEqual(ScanLocationStore(self.config).list_locations(), (first, second))

    def test_duplicate_paths_are_not_added_twice(self):
        folder = self.root / "Anime"
        self.assertTrue(self.store.add_location(folder))
        self.assertFalse(self.store.add_location(folder / "."))
        self.assertEqual(self.store.list_locations(), (folder,))

    def test_remove_location(self):
        folder = self.root / "Anime"
        self.store.add_location(folder)
        self.assertFalse(self.store.remove_location(self.root / "Missing"))
        self.assertTrue(self.store.remove_location(folder))
        self.assertEqual(self.store.list_locations(), ())

    def test_unavailable_removable_drive_path_is_retained(self):
        offline = self.root / "unmounted-drive" / "Anime"
        self.store.add_location(offline)
        self.assertEqual(self.store.list_locations(), (offline,))
        self.assertFalse(offline.exists())

    def test_rejects_empty_and_relative_paths(self):
        for value in ("", "relative/anime"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_scan_location(value)

    def test_malformed_existing_configuration_is_not_overwritten(self):
        self.config.parent.mkdir(parents=True)
        original = "{not valid json"
        self.config.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid"):
            self.store.add_location(self.root / "Anime")
        self.assertEqual(self.config.read_text(encoding="utf-8"), original)

    def test_rejects_unsupported_configuration_version(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text(json.dumps({
            "format": "aniyori-scan-locations", "version": 99, "locations": [],
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.store.list_locations()

    def test_rejects_malformed_location_entries(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text(json.dumps({
            "format": "aniyori-scan-locations", "version": 1,
            "locations": ["/valid", 42],
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "malformed"):
            self.store.list_locations()

    def test_uses_xdg_config_home_and_falls_back_for_relative_value(self):
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": "/custom/config"}):
            self.assertEqual(default_scan_locations_path(),
                Path("/custom/config/aniyori/scan-locations.json"))
        with patch.dict("os.environ", {"XDG_CONFIG_HOME": "relative/config"}):
            with patch("pathlib.Path.home", return_value=Path("/home/test")):
                self.assertEqual(default_scan_locations_path(),
                    Path("/home/test/.config/aniyori/scan-locations.json"))


if __name__ == "__main__":
    unittest.main()
