"""Tests for editing stored anime entries."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry, WatchStatus
from aniyori.storage import LibraryStorage


class UpdateEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = LibraryStorage(Path(self.temp_dir.name) / "library.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_edit_updates_only_target_entry(self):
        self.storage.add(AnimeEntry(title="Duplicate", episodes_total=12))
        self.storage.add(AnimeEntry(title="Duplicate", episodes_total=24))
        first, second = self.storage.list_entries()
        edited = AnimeEntry(
            title="Renamed",
            episodes_total=24,
            episodes_watched=5,
            status=WatchStatus.WATCHING,
            storage_id=second.storage_id,
        )

        self.assertTrue(self.storage.update_entry(edited))
        entries = self.storage.list_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].title, "Duplicate")
        renamed = next(item for item in entries if item.storage_id == second.storage_id)
        self.assertEqual(renamed.title, "Renamed")
        self.assertEqual(renamed.episodes_watched, 5)

    def test_edit_rejects_duplicate_catalogue_identity(self):
        self.storage.add(AnimeEntry(title="First", provider="anilist", provider_id="101"))
        self.storage.add(AnimeEntry(title="Second", provider="anilist", provider_id="202"))
        first, second = self.storage.list_entries()
        edited = AnimeEntry(
            title="Second",
            provider="anilist",
            provider_id="202",
            storage_id=first.storage_id,
        )

        with self.assertRaisesRegex(ValueError, "already in your library"):
            self.storage.update_entry(edited)

        unchanged = {entry.storage_id: entry for entry in self.storage.list_entries()}
        self.assertEqual(unchanged[first.storage_id].title, "First")
        self.assertEqual(unchanged[second.storage_id].title, "Second")


    def test_edit_does_not_mask_unrelated_integrity_errors(self):
        self.storage.add(AnimeEntry(title="Existing", provider="anilist", provider_id="303"))
        entry = self.storage.list_entries()[0]
        edited = AnimeEntry(
            title="Edited",
            provider="anilist",
            provider_id="303",
            storage_id=entry.storage_id,
        )
        with sqlite3.connect(self.storage.path) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_anime_update
                BEFORE UPDATE ON anime
                BEGIN
                    SELECT RAISE(ABORT, 'forced integrity failure');
                END
                """
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "forced integrity failure"):
            self.storage.update_entry(edited)

    def test_add_does_not_mask_unrelated_integrity_errors(self):
        with sqlite3.connect(self.storage.path) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_anime_insert
                BEFORE INSERT ON anime
                BEGIN
                    SELECT RAISE(ABORT, 'forced integrity failure');
                END
                """
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "forced integrity failure"):
            self.storage.add(
                AnimeEntry(title="New", provider="anilist", provider_id="404")
            )

    def test_edit_requires_stored_id(self):
        with self.assertRaisesRegex(ValueError, "storage ID"):
            self.storage.update_entry(AnimeEntry(title="Not stored"))

    def test_edit_missing_id_returns_false(self):
        entry = AnimeEntry(title="Gone", storage_id=9876)
        self.assertFalse(self.storage.update_entry(entry))


if __name__ == "__main__":
    unittest.main()
