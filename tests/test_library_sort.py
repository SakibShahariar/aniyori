"""Tests for library sort modes used by both list and grid layouts."""

import unittest

from aniyori.models import AnimeEntry
from aniyori.services.library_sort import sort_library_entries


class LibrarySortTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            AnimeEntry(title="Zulu", episodes_watched=4, episodes_total=12, storage_id=1),
            AnimeEntry(title="Alpha", episodes_watched=5, episodes_total=5, storage_id=2),
            AnimeEntry(title="Beta", episodes_watched=3, episodes_total=None, storage_id=3),
        ]

    def test_title_sort_is_case_insensitive_and_stable(self):
        self.assertEqual(
            [item.title for item in sort_library_entries(self.entries)],
            ["Alpha", "Beta", "Zulu"],
        )

    def test_progress_sort_uses_completion_fraction_then_title(self):
        self.assertEqual(
            [item.title for item in sort_library_entries(self.entries, sort_by="progress")],
            ["Alpha", "Zulu", "Beta"],
        )

    def test_recently_updated_sort_places_latest_first_and_missing_last(self):
        updated = {1: "2026-01-01 00:00:00", 2: "2026-03-01 00:00:00"}
        self.assertEqual(
            [item.title for item in sort_library_entries(
                self.entries, sort_by="recently_updated", updated_at_by_id=updated
            )],
            ["Alpha", "Zulu", "Beta"],
        )

    def test_next_airing_sort_places_soonest_known_episode_first(self):
        airing = {1: (5, 300), 2: (6, 100)}
        self.assertEqual(
            [item.title for item in sort_library_entries(
                self.entries, sort_by="next_airing", airing_by_id=airing
            )],
            ["Alpha", "Zulu", "Beta"],
        )

    def test_rejects_unknown_sort_mode(self):
        with self.assertRaisesRegex(ValueError, "sort mode"):
            sort_library_entries(self.entries, sort_by="random")


if __name__ == "__main__":
    unittest.main()
