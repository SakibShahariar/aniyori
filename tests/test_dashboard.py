"""Tests for Home dashboard data selection."""

import unittest

from aniyori.dashboard import (
    continue_watching_entries,
    count_library_statuses,
    recently_added_entries,
    upcoming_airing_entries,
)
from aniyori.models import AnimeEntry, WatchStatus


class DashboardSelectionTests(unittest.TestCase):
    def test_status_counts_include_empty_statuses(self):
        entries = [
            AnimeEntry(title="Watching", status=WatchStatus.WATCHING),
            AnimeEntry(title="Completed", status=WatchStatus.COMPLETED),
            AnimeEntry(title="Another watching", status=WatchStatus.WATCHING),
        ]

        counts = count_library_statuses(entries)

        self.assertEqual(counts[WatchStatus.WATCHING], 2)
        self.assertEqual(counts[WatchStatus.COMPLETED], 1)
        self.assertEqual(counts[WatchStatus.PLANNING], 0)
        self.assertEqual(counts[WatchStatus.PAUSED], 0)
        self.assertEqual(counts[WatchStatus.DROPPED], 0)

    def test_continue_watching_excludes_completed_and_non_watching(self):
        entries = [
            AnimeEntry(title="Active", status=WatchStatus.WATCHING, episodes_total=12, episodes_watched=4),
            AnimeEntry(title="Finished", status=WatchStatus.WATCHING, episodes_total=12, episodes_watched=12),
            AnimeEntry(title="Planning", status=WatchStatus.PLANNING, episodes_total=12),
            AnimeEntry(title="Unknown total", status=WatchStatus.WATCHING),
        ]

        selected = continue_watching_entries(entries)

        self.assertEqual([entry.title for entry in selected], ["Active", "Unknown total"])

    def test_continue_watching_prioritizes_recently_updated_entries(self):
        older = AnimeEntry(title="Older", status=WatchStatus.WATCHING, storage_id=1)
        newer = AnimeEntry(title="Newer", status=WatchStatus.WATCHING, storage_id=2)
        selected = continue_watching_entries(
            [older, newer],
            {1: "2026-01-01 10:00:00", 2: "2026-02-01 10:00:00"},
        )
        self.assertEqual([entry.title for entry in selected], ["Newer", "Older"])

    def test_continue_watching_respects_limit(self):
        entries = [
            AnimeEntry(title=f"Anime {index}", status=WatchStatus.WATCHING)
            for index in range(4)
        ]

        self.assertEqual(len(continue_watching_entries(entries, limit=2)), 2)
        self.assertEqual(continue_watching_entries(entries, limit=0), [])

    def test_recently_added_uses_creation_timestamps_newest_first(self):
        older = AnimeEntry(title="Older", storage_id=1)
        newer = AnimeEntry(title="Newer", storage_id=2)
        selected = recently_added_entries(
            [older, newer],
            {1: "2026-01-01 10:00:00", 2: "2026-02-01 10:00:00"},
        )
        self.assertEqual([entry.title for entry in selected], ["Newer", "Older"])

    def test_recently_added_excludes_entries_without_creation_timestamps(self):
        saved = AnimeEntry(title="Saved", storage_id=1)
        missing = AnimeEntry(title="Missing timestamp", storage_id=2)
        unsaved = AnimeEntry(title="Unsaved")
        selected = recently_added_entries(
            [saved, missing, unsaved],
            {1: "2026-01-01 10:00:00"},
        )
        self.assertEqual([entry.title for entry in selected], ["Saved"])

    def test_upcoming_airing_sorts_future_entries_soonest_first(self):
        soon = AnimeEntry(title="Soon", storage_id=1)
        later = AnimeEntry(title="Later", storage_id=2)
        selected = upcoming_airing_entries(
            [later, soon],
            {1: (13, 200), 2: (14, 100)},
            now=0,
        )
        self.assertEqual([entry.title for entry in selected], ["Later", "Soon"])

    def test_upcoming_airing_skips_past_and_malformed_data(self):
        valid = AnimeEntry(title="Valid", storage_id=1)
        past = AnimeEntry(title="Past", storage_id=2)
        malformed = AnimeEntry(title="Malformed", storage_id=3)
        unsaved = AnimeEntry(title="Unsaved")
        selected = upcoming_airing_entries(
            [past, valid, malformed, unsaved],
            {1: (13, 200), 2: (12, -5), 3: (13, "later")},
            now=100,
        )
        self.assertEqual([entry.title for entry in selected], ["Valid"])

    def test_upcoming_airing_respects_limit(self):
        entries = [
            AnimeEntry(title=f"Anime {index}", storage_id=index)
            for index in range(1, 4)
        ]
        airing = {index: (index, index * 10) for index in range(1, 4)}
        self.assertEqual(len(upcoming_airing_entries(entries, airing, now=0, limit=2)), 2)
        self.assertEqual(upcoming_airing_entries(entries, airing, now=0, limit=0), [])



if __name__ == "__main__":
    unittest.main()
