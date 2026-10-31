"""Tests for configured local library scanning orchestration."""

import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry
from aniyori.services.scan_library import scan_configured_library
from aniyori.services.scan_locations import ScanLocationStore


class ConfiguredLibraryScanTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.folder = self.root / "Anime"
        self.folder.mkdir()
        self.store = ScanLocationStore(self.root / "config" / "locations.json")
        self.store.add_location(self.folder)
        self.entry = AnimeEntry(
            title="Frieren", provider="anilist", provider_id="10", episodes_total=3
        )
        self.candidates = [{"id": 10, "title": "Frieren"}]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scans_configured_folders_and_builds_episode_inventory(self):
        (self.folder / "[Group] Frieren - 01.mkv").touch()
        (self.folder / "[Group] Frieren - 03.mkv").touch()

        result = scan_configured_library(
            self.store, self.candidates, [self.entry]
        )

        self.assertEqual(result.locations, (self.folder,))
        self.assertEqual(len(result.matches), 2)
        self.assertEqual(result.inventory[0].available_episodes, (1, 3))
        self.assertEqual(result.inventory[0].missing_episodes, (2,))
        self.assertEqual(result.inventory[0].next_episode, 2)

    def test_no_configured_folders_returns_empty_inventory_snapshot(self):
        empty_store = ScanLocationStore(self.root / "empty.json")

        result = scan_configured_library(empty_store, self.candidates, [self.entry])

        self.assertEqual(result.locations, ())
        self.assertEqual(result.matches, ())
        self.assertEqual(result.inventory[0].missing_episodes, (1, 2, 3))

    def test_scan_respects_cancellation(self):
        (self.folder / "[Group] Frieren - 01.mkv").touch()

        result = scan_configured_library(
            self.store, self.candidates, [self.entry], is_cancelled=lambda: True
        )

        self.assertEqual(result.matches, ())
        self.assertEqual(result.inventory[0].available_episodes, ())

    def test_scan_uses_catalogue_candidates_for_recognition(self):
        (self.folder / "[Group] Frieren - 01.mkv").touch()
        result = scan_configured_library(
            self.store, [{"id": 99, "title": "Other Anime"}], [self.entry]
        )
        self.assertEqual(result.matches[0].result.status, "no_match")
        self.assertEqual(result.inventory[0].available_episodes, ())


if __name__ == "__main__":
    unittest.main()
