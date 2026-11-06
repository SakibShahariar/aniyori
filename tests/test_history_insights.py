"""Tests for yearly watch-history insights."""

import unittest
from datetime import timedelta, timezone

from aniyori.statistics import calculate_history_insights


class HistoryInsightsTests(unittest.TestCase):
    def test_monthly_totals_separate_first_watches_rewatches_and_corrections(self):
        events = [
            {
                "id": 1, "anime_id": 10, "anime_title": "Frieren",
                "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-01-05T12:00:00Z",
            },
            {
                "id": 2, "anime_id": 10, "anime_title": "Frieren",
                "action": "episode", "details": "Rewatched episode",
                "created_at": "2026-01-06T12:00:00Z",
            },
            {
                "id": 3, "anime_id": 10, "anime_title": "Frieren",
                "action": "episode", "details": "2 → 3",
                "created_at": "2026-02-01T00:00:00",
            },
            {
                "id": 4, "anime_id": 10, "anime_title": "Frieren",
                "action": "progress", "details": "3 → 1",
                "created_at": "2026-02-02T00:00:00Z",
            },
            {
                "id": 5, "anime_id": 10, "anime_title": "Frieren",
                "action": "status", "details": "watching → completed",
                "created_at": "2026-02-03T00:00:00Z",
            },
        ]

        result = calculate_history_insights(
            events, 2026, local_timezone=timezone.utc
        )

        self.assertEqual(result["event_count"], 5)
        self.assertEqual(result["episode_events"], 3)
        self.assertEqual(result["first_watch_events"], 2)
        self.assertEqual(result["rewatch_events"], 1)
        self.assertEqual(result["progress_changes"], 1)
        self.assertEqual(result["status_changes"], 1)
        self.assertEqual(result["unclassified_episode_events"], 0)
        self.assertEqual(result["active_days"], 5)
        self.assertEqual(result["completed_anime_count"], 1)
        self.assertEqual(result["completed_anime"][0]["title"], "Frieren")
        self.assertEqual(result["estimated_minutes"], 3 * 24)
        self.assertEqual(result["months"][0]["episode_events"], 2)
        self.assertEqual(result["months"][1]["first_watch_events"], 1)
        self.assertEqual(result["months"][1]["progress_changes"], 1)

    def test_timezone_conversion_assigns_events_to_local_calendar_year(self):
        events = [
            {
                "id": 1, "anime_title": "Before local new year",
                "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-01-01T02:00:00Z",
            },
            {
                "id": 2, "anime_title": "After local new year",
                "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-01-01T05:30:00Z",
            },
        ]
        local_zone = timezone(timedelta(hours=-5))

        previous_year = calculate_history_insights(
            events, 2025, local_timezone=local_zone
        )
        current_year = calculate_history_insights(
            events, 2026, local_timezone=local_zone
        )

        self.assertEqual(previous_year["episode_events"], 1)
        self.assertEqual(previous_year["months"][11]["episode_events"], 1)
        self.assertEqual(current_year["episode_events"], 1)
        self.assertEqual(current_year["months"][0]["episode_events"], 1)

    def test_malformed_undated_and_duplicate_records_are_not_counted(self):
        events = [
            {"id": 1, "action": "episode", "created_at": "not-a-date"},
            {
                "id": 1, "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-03-01T12:00:00Z",
            },
            {
                "id": 1, "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-03-02T12:00:00Z",
            },
            {"id": 2, "action": "episode", "created_at": "not-a-date"},
            {"id": 3, "action": "episode"},
            {"id": 4, "action": [], "created_at": "2026-03-03T00:00:00Z"},
        ]

        result = calculate_history_insights(
            events, 2026, local_timezone=timezone.utc
        )

        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["episode_events"], 1)
        self.assertEqual(result["active_days"], 1)

    def test_empty_year_returns_twelve_zeroed_months(self):
        result = calculate_history_insights(
            [], 2024, local_timezone=timezone.utc
        )

        self.assertEqual(len(result["months"]), 12)
        self.assertEqual(result["event_count"], 0)
        self.assertEqual(result["completed_anime"], [])
        self.assertEqual(result["active_days"], 0)
        self.assertEqual(result["estimated_minutes"], 0)
        self.assertTrue(all(month["event_count"] == 0 for month in result["months"]))

    def test_completed_anime_are_deduplicated_by_library_id(self):
        events = [
            {
                "id": 1, "anime_id": 7, "anime_title": "Title before edit",
                "action": "status", "details": "watching → completed",
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 2, "anime_id": 7, "anime_title": "Title after edit",
                "action": "status", "details": "paused → completed",
                "created_at": "2026-02-01T00:00:00Z",
            },
        ]

        result = calculate_history_insights(
            events, 2026, local_timezone=timezone.utc
        )

        self.assertEqual(result["completed_anime_count"], 1)

    def test_invalid_year_timezone_and_duration_are_rejected(self):
        for year in (True, 0, 10000, "2026"):
            with self.subTest(year=year), self.assertRaises(ValueError):
                calculate_history_insights([], year)
        with self.assertRaises(ValueError):
            calculate_history_insights([], 2026, local_timezone="UTC")
        with self.assertRaises(ValueError):
            calculate_history_insights([], 2026, minutes_per_episode=-1)
        with self.assertRaises(ValueError):
            calculate_history_insights([], 2026, minutes_per_episode=True)
        with self.assertRaises(ValueError):
            calculate_history_insights([], 2026, minutes_per_episode=24.5)


if __name__ == "__main__":
    unittest.main()
