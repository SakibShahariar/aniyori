"""Tests for SQLite library storage."""

import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry, WatchStatus
from aniyori.storage import LibraryStorage


class LibraryStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "test-library.sqlite3"
        self.storage = LibraryStorage(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_and_reload_entry(self):
        entry = AnimeEntry(
            title="Example Anime",
            episodes_total=12,
            episodes_watched=4,
            status=WatchStatus.WATCHING,
        )
        self.storage.add(entry)
        reopened = LibraryStorage(self.database)
        self.assertEqual(reopened.list_entries(), [entry])

    def test_update_progress(self):
        self.storage.add(AnimeEntry(title="Example Anime", episodes_total=12))
        self.assertTrue(self.storage.update_progress("Example Anime", 12))
        entry = self.storage.list_entries()[0]
        self.assertEqual(entry.episodes_watched, 12)
        self.assertEqual(entry.status, WatchStatus.COMPLETED)

    def test_update_missing_title_returns_false(self):
        self.assertFalse(self.storage.update_progress("Missing", 1))

    def test_progress_cannot_exceed_total(self):
        self.storage.add(AnimeEntry(title="Example Anime", episodes_total=4))
        with self.assertRaises(ValueError):
            self.storage.update_progress("Example Anime", 5)

    def test_remove(self):
        self.storage.add(AnimeEntry(title="Example Anime"))
        self.assertTrue(self.storage.remove("Example Anime"))
        self.assertEqual(self.storage.list_entries(), [])


if __name__ == "__main__":
    unittest.main()
