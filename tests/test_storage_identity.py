"""Regression tests for duplicate-title entry identity."""

import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry
from aniyori.storage import LibraryStorage


class EntryIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = LibraryStorage(Path(self.temp_dir.name) / "library.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_progress_updates_only_selected_duplicate_title(self):
        self.storage.add(AnimeEntry(title="Same Title", episodes_total=12))
        self.storage.add(AnimeEntry(title="Same Title", episodes_total=24))
        first, second = self.storage.list_entries()

        self.assertTrue(self.storage.update_progress(second.storage_id, 3))
        entries = self.storage.list_entries()
        self.assertEqual(entries[0].episodes_watched, 0)
        self.assertEqual(entries[1].episodes_watched, 3)

    def test_remove_deletes_only_selected_duplicate_title(self):
        self.storage.add(AnimeEntry(title="Same Title"))
        self.storage.add(AnimeEntry(title="Same Title"))
        first, second = self.storage.list_entries()

        self.assertTrue(self.storage.remove(second.storage_id))
        entries = self.storage.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].storage_id, first.storage_id)


if __name__ == "__main__":
    unittest.main()
