"""Tests for SQLite library storage."""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from aniyori.models import AnimeEntry, WatchStatus
from aniyori.storage import LibraryStorage, default_database_path


class LibraryStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "test-library.sqlite3"
        self.storage = LibraryStorage(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_xdg_data_home_uses_default_data_directory(self):
        with patch.dict("os.environ", {"XDG_DATA_HOME": ""}):
            with patch("pathlib.Path.home", return_value=Path("/home/test")):
                self.assertEqual(
                    default_database_path(),
                    Path("/home/test/.local/share/aniyori/library.sqlite3"),
                )

    def test_relative_xdg_data_home_uses_default_data_directory(self):
        with patch.dict("os.environ", {"XDG_DATA_HOME": "relative/data"}):
            with patch("pathlib.Path.home", return_value=Path("/home/test")):
                self.assertEqual(
                    default_database_path(),
                    Path("/home/test/.local/share/aniyori/library.sqlite3"),
                )

    def test_add_and_reload_entry(self):
        entry = AnimeEntry(
            title="Example Anime",
            episodes_total=12,
            episodes_watched=4,
            status=WatchStatus.WATCHING,
            provider="anilist",
            provider_id="21",
            cover_image="https://s4.anilist.co/file/cover.jpg",
        )
        self.storage.add(entry)
        reopened = LibraryStorage(self.database)
        self.assertEqual(reopened.list_entries(), [entry])

    def test_replace_all_preserves_cover_image_urls(self):
        entry = AnimeEntry(
            title="Cover Anime",
            provider="anilist",
            provider_id="789",
            cover_image="https://s4.anilist.co/file/cover.jpg",
        )

        self.storage.replace_all([entry])

        stored = self.storage.list_entries()[0]
        self.assertEqual(stored.cover_image, entry.cover_image)

    def test_update_progress(self):
        self.storage.add(AnimeEntry(title="Example Anime", episodes_total=12))
        entry = self.storage.list_entries()[0]
        self.assertTrue(self.storage.update_progress(entry.storage_id, 12))
        entry = self.storage.list_entries()[0]
        self.assertEqual(entry.episodes_watched, 12)
        self.assertEqual(entry.status, WatchStatus.COMPLETED)

    def test_update_missing_storage_id_returns_false(self):
        self.assertFalse(self.storage.update_progress(9876, 1))

    def test_update_progress_requires_storage_id(self):
        with self.assertRaisesRegex(ValueError, "storage ID"):
            self.storage.update_progress("Example Anime", 1)

    def test_progress_cannot_exceed_total(self):
        self.storage.add(AnimeEntry(title="Example Anime", episodes_total=4))
        entry = self.storage.list_entries()[0]
        with self.assertRaises(ValueError):
            self.storage.update_progress(entry.storage_id, 5)

    def test_duplicate_provider_entry_is_rejected(self):
        entry = AnimeEntry(title="Example Anime", provider="anilist", provider_id="21")
        self.storage.add(entry)
        with self.assertRaisesRegex(ValueError, "already in your library"):
            self.storage.add(entry)

    def test_manual_duplicate_titles_are_allowed(self):
        entry = AnimeEntry(title="Example Anime")
        self.storage.add(entry)
        self.storage.add(entry)
        self.assertEqual(len(self.storage.list_entries()), 2)

    def test_find_manual_title_matches_ignores_case_and_extra_whitespace(self):
        self.storage.add(AnimeEntry(title="  Fullmetal   Alchemist "))
        self.storage.add(AnimeEntry(title="Fullmetal Alchemist Brotherhood"))
        matches = self.storage.find_manual_title_matches("fullmetal alchemist")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].title, "Fullmetal   Alchemist")

    def test_find_manual_title_matches_excludes_catalogue_entries(self):
        self.storage.add(AnimeEntry(
            title="Example Anime", provider="anilist", provider_id="123"
        ))
        self.assertEqual(self.storage.find_manual_title_matches("Example Anime"), [])

    def test_find_manual_title_matches_returns_all_intentional_editions(self):
        self.storage.add(AnimeEntry(title="Fate/stay night", episodes_total=24))
        self.storage.add(AnimeEntry(title="Fate/stay night", episodes_total=12))
        matches = self.storage.find_manual_title_matches("Fate/stay night")
        self.assertEqual(len(matches), 2)
        self.assertEqual({item.episodes_total for item in matches}, {12, 24})

    def test_find_manual_title_matches_handles_empty_query(self):
        self.storage.add(AnimeEntry(title="Example Anime"))
        self.assertEqual(self.storage.find_manual_title_matches("   "), [])

    def test_remove(self):
        self.storage.add(AnimeEntry(title="Example Anime"))
        entry = self.storage.list_entries()[0]
        self.assertTrue(self.storage.remove(entry.storage_id))
        self.assertEqual(self.storage.list_entries(), [])

    def test_remove_requires_storage_id(self):
        with self.assertRaisesRegex(ValueError, "storage ID"):
            self.storage.remove("Example Anime")

    def test_restore_preserves_original_id_and_all_entry_fields(self):
        entry = AnimeEntry(
            title="Restorable Anime",
            episodes_total=24,
            episodes_watched=9,
            status=WatchStatus.PAUSED,
            provider="anilist",
            provider_id="456",
        )
        self.storage.add(entry)
        deleted = self.storage.list_entries()[0]
        self.assertTrue(self.storage.remove(deleted.storage_id))

        self.storage.restore(deleted)

        restored = self.storage.list_entries()[0]
        self.assertEqual(restored.storage_id, deleted.storage_id)
        self.assertEqual(restored.title, deleted.title)
        self.assertEqual(restored.episodes_total, deleted.episodes_total)
        self.assertEqual(restored.episodes_watched, deleted.episodes_watched)
        self.assertEqual(restored.status, deleted.status)
        self.assertEqual(restored.provider, deleted.provider)
        self.assertEqual(restored.provider_id, deleted.provider_id)
        self.assertEqual(restored.cover_image, deleted.cover_image)

    def test_restore_rejects_entry_without_valid_storage_id(self):
        with self.assertRaisesRegex(ValueError, "storage ID"):
            self.storage.restore(AnimeEntry(title="No ID"))

    def test_restore_does_not_overwrite_an_existing_entry(self):
        self.storage.add(AnimeEntry(title="Original"))
        deleted = AnimeEntry(title="Deleted", storage_id=1)

        with self.assertRaisesRegex(ValueError, "already in use"):
            self.storage.restore(deleted)

        self.assertEqual([item.title for item in self.storage.list_entries()], ["Original"])

    def test_duplicate_titles_are_mutated_by_storage_id_only(self):
        self.storage.add(AnimeEntry(title="Duplicate", episodes_total=12))
        self.storage.add(AnimeEntry(title="Duplicate", episodes_total=24))
        first, second = self.storage.list_entries()

        self.assertTrue(self.storage.update_progress(second.storage_id, 3))
        updated = {entry.storage_id: entry for entry in self.storage.list_entries()}
        self.assertEqual(updated[first.storage_id].episodes_watched, 0)
        self.assertEqual(updated[second.storage_id].episodes_watched, 3)

        self.assertTrue(self.storage.remove(second.storage_id))
        remaining = self.storage.list_entries()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].storage_id, first.storage_id)

    def test_progress_preserves_paused_and_dropped_statuses(self):
        for status in (WatchStatus.PAUSED, WatchStatus.DROPPED):
            with self.subTest(status=status):
                self.storage.add(AnimeEntry(title=status.value, episodes_total=12, status=status))
                entry = next(item for item in self.storage.list_entries() if item.title == status.value)
                self.assertTrue(self.storage.update_progress(entry.storage_id, 1))
                updated = next(item for item in self.storage.list_entries() if item.storage_id == entry.storage_id)
                self.assertEqual(updated.status, status)

    def test_progress_preserves_completed_status_when_total_is_unknown(self):
        self.storage.add(AnimeEntry(title="Completed unknown", status=WatchStatus.COMPLETED))
        entry = self.storage.list_entries()[0]
        self.assertTrue(self.storage.update_progress(entry.storage_id, 1))
        self.assertEqual(self.storage.list_entries()[0].status, WatchStatus.COMPLETED)

    def test_progress_moves_planning_to_watching_and_completes_at_total(self):
        self.storage.add(AnimeEntry(title="Planning", episodes_total=2))
        entry = self.storage.list_entries()[0]
        self.assertTrue(self.storage.update_progress(entry.storage_id, 1))
        self.assertEqual(self.storage.list_entries()[0].status, WatchStatus.WATCHING)
        self.assertTrue(self.storage.update_progress(entry.storage_id, 2))
        self.assertEqual(self.storage.list_entries()[0].status, WatchStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
