"""Edge-case tests for library storage operations."""

import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry, WatchStatus
from aniyori.storage import LibraryStorage


class StorageEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = LibraryStorage(Path(self.temp_dir.name) / "library.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_unknown_database_id_returns_false(self):
        self.assertFalse(self.storage.update_progress(9999, 1))
        self.assertFalse(self.storage.remove(9999))

    def test_negative_progress_is_rejected(self):
        self.storage.add(AnimeEntry(title="Example", episodes_total=12))
        entry = self.storage.list_entries()[0]
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            self.storage.update_progress(entry.storage_id, -1)

    def test_progress_updates_reject_non_integer_values_without_mutation(self):
        self.storage.add(AnimeEntry(title="Example", episodes_total=12))
        entry = self.storage.list_entries()[0]

        for value in (True, False, 1.5, "2"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "whole number"):
                    self.storage.update_progress(entry.storage_id, value)
                self.assertEqual(
                    self.storage.list_entries()[0].episodes_watched,
                    0,
                )

    def test_progress_cannot_exceed_model_limit_when_total_is_unknown(self):
        self.storage.add(AnimeEntry(title="Unknown total"))
        entry = self.storage.list_entries()[0]

        with self.assertRaisesRegex(ValueError, "cannot exceed 10,000"):
            self.storage.update_progress(entry.storage_id, 10_001)

        # Invalid progress must not poison the database or break later reads.
        stored = self.storage.list_entries()[0]
        self.assertEqual(stored.episodes_watched, 0)

    def test_progress_cannot_exceed_selected_entry_total(self):
        self.storage.add(AnimeEntry(title="Example", episodes_total=3))
        entry = self.storage.list_entries()[0]
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            self.storage.update_progress(entry.storage_id, 4)
        self.assertEqual(self.storage.list_entries()[0].episodes_watched, 0)

    def test_replace_all_replaces_entries_atomically(self):
        self.storage.add(AnimeEntry(title="Old"))
        self.storage.replace_all([
            AnimeEntry(title="New", episodes_total=10, episodes_watched=2,
                       status=WatchStatus.WATCHING)
        ])
        entries = self.storage.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "New")
        self.assertEqual(entries[0].episodes_watched, 2)


if __name__ == "__main__":
    unittest.main()
