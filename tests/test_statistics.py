"""Tests for local-library statistics."""

import unittest

from aniyori.models import AnimeEntry, WatchStatus
from aniyori.statistics import calculate_library_statistics


class LibraryStatisticsTests(unittest.TestCase):
    def test_empty_library_has_zeroed_statistics(self):
        result = calculate_library_statistics([])

        self.assertEqual(result["anime_count"], 0)
        self.assertEqual(result["episodes_watched"], 0)
        self.assertEqual(result["completion_rate"], 0.0)
        self.assertEqual(result["estimated_minutes"], 0)
        self.assertEqual(
            result["status_counts"],
            {status.value: 0 for status in WatchStatus},
        )

    def test_calculates_progress_statuses_and_estimated_time(self):
        entries = [
            AnimeEntry(
                title="Watching",
                episodes_total=12,
                episodes_watched=4,
                status=WatchStatus.WATCHING,
            ),
            AnimeEntry(
                title="Completed",
                episodes_total=24,
                episodes_watched=24,
                status=WatchStatus.COMPLETED,
            ),
            AnimeEntry(title="Planning", status=WatchStatus.PLANNING),
        ]

        result = calculate_library_statistics(entries)

        self.assertEqual(result["anime_count"], 3)
        self.assertEqual(result["episodes_watched"], 28)
        self.assertEqual(result["known_episodes_total"], 36)
        self.assertEqual(result["completion_rate"], 33.3)
        self.assertEqual(result["estimated_minutes"], 28 * 24)
        self.assertEqual(result["status_counts"]["watching"], 1)
        self.assertEqual(result["status_counts"]["completed"], 1)
        self.assertEqual(result["status_counts"]["planning"], 1)

    def test_unknown_episode_totals_are_not_counted_as_zero_progress(self):
        entry = AnimeEntry(
            title="Unknown total",
            episodes_watched=7,
            status=WatchStatus.WATCHING,
        )

        result = calculate_library_statistics([entry])

        self.assertEqual(result["episodes_watched"], 7)
        self.assertEqual(result["known_episodes_total"], 0)

    def test_episode_duration_must_be_a_nonnegative_integer(self):
        with self.assertRaises(ValueError):
            calculate_library_statistics([], minutes_per_episode=-1)
        with self.assertRaises(ValueError):
            calculate_library_statistics([], minutes_per_episode=1.5)
        with self.assertRaises(ValueError):
            calculate_library_statistics([], minutes_per_episode=True)


if __name__ == "__main__":
    unittest.main()
