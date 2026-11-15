"""Tests for local-library statistics."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from aniyori.models import AnimeEntry, WatchStatus
from aniyori.statistics import calculate_history_insights, calculate_library_statistics
from aniyori.timezones import get_local_timezone


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


class WatchHistoryInsightsTests(unittest.TestCase):
    def test_monthly_activity_counts_episode_rewatch_progress_and_status_events(self):
        events = [
            {
                "id": 1, "anime_id": 10, "anime_title": "First Watch",
                "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-02-03 12:00:00",
            },
            {
                "id": 2, "anime_id": 10, "anime_title": "First Watch",
                "action": "episode", "details": "Rewatched episode",
                "created_at": "2026-02-03 13:00:00",
            },
            {
                "id": 3, "anime_id": 10, "anime_title": "First Watch",
                "action": "progress", "details": "Marked episode unwatched",
                "created_at": "2026-02-04 13:00:00",
            },
            {
                "id": 4, "anime_id": 10, "anime_title": "First Watch",
                "action": "status", "details": "watching → completed",
                "created_at": "2026-02-05 13:00:00",
            },
        ]

        result = calculate_history_insights(
            events, 2026, local_timezone=timezone.utc, minutes_per_episode=30
        )

        february = result["months"][1]
        self.assertEqual(february["event_count"], 4)
        self.assertEqual(february["episode_events"], 2)
        self.assertEqual(february["first_watch_events"], 1)
        self.assertEqual(february["rewatch_events"], 1)
        self.assertEqual(february["progress_changes"], 1)
        self.assertEqual(february["status_changes"], 1)
        self.assertEqual(result["active_days"], 3)
        self.assertEqual(result["completed_anime"], [{"id": 10, "title": "First Watch"}])
        self.assertEqual(result["estimated_minutes"], 60)

    def test_local_calendar_year_boundary_uses_the_requested_timezone(self):
        events = [
            {
                "id": 1, "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-01-01T00:30:00+00:00",
            },
            {
                "id": 2, "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-01-01T01:30:00+00:00",
            },
        ]
        local_timezone = timezone(timedelta(hours=-1))

        previous_year = calculate_history_insights(
            events, 2025, local_timezone=local_timezone
        )
        new_year = calculate_history_insights(
            events, 2026, local_timezone=local_timezone
        )

        self.assertEqual(previous_year["event_count"], 1)
        self.assertEqual(previous_year["months"][11]["episode_events"], 1)
        self.assertEqual(new_year["event_count"], 1)
        self.assertEqual(new_year["months"][0]["episode_events"], 1)

    def test_daylight_saving_transition_keeps_events_on_their_local_day(self):
        local_timezone = ZoneInfo("America/New_York")
        events = [
            {
                "id": 1, "action": "episode", "details": "Marked episode watched",
                "created_at": "2026-03-08T06:30:00+00:00",
            },
            {
                "id": 2, "action": "episode", "details": "Rewatched episode",
                "created_at": "2026-03-08T07:30:00+00:00",
            },
        ]

        result = calculate_history_insights(
            events, 2026, local_timezone=local_timezone
        )

        self.assertEqual(result["event_count"], 2)
        self.assertEqual(result["active_days"], 1)
        self.assertEqual(result["months"][2]["episode_events"], 2)

    def test_invalid_missing_and_duplicate_history_rows_are_ignored(self):
        valid = {
            "id": 7, "action": "episode", "details": "Marked episode watched",
            "created_at": "2026-05-01T12:00:00+00:00",
        }
        events = [
            valid,
            dict(valid),
            {"id": 8, "action": "episode", "details": "Marked episode watched", "created_at": ""},
            {"id": 9, "action": "episode", "details": "Marked episode watched", "created_at": "not-a-date"},
            {"id": 10, "action": "unknown", "details": None, "created_at": "2026-05-01T12:00:00+00:00"},
            None,
        ]

        result = calculate_history_insights(
            events, 2026, local_timezone=timezone.utc
        )

        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["episode_events"], 1)
        self.assertEqual(result["active_days"], 1)

    def test_repeated_completion_events_do_not_duplicate_anime(self):
        events = [
            {
                "id": 1, "anime_id": 12, "anime_title": "Completed Anime",
                "action": "status", "details": "watching → completed",
                "created_at": "2026-07-01T10:00:00+00:00",
            },
            {
                "id": 2, "anime_id": 12, "anime_title": "Completed Anime",
                "action": "status", "details": "paused → completed",
                "created_at": "2026-07-02T10:00:00+00:00",
            },
            {
                "id": 3, "anime_id": 13, "anime_title": " completed anime ",
                "action": "status", "details": "watching → completed",
                "created_at": "2026-07-03T10:00:00+00:00",
            },
        ]

        result = calculate_history_insights(
            events, 2026, local_timezone=timezone.utc
        )

        self.assertEqual(result["completed_anime_count"], 2)
        self.assertEqual(
            [item["title"] for item in result["completed_anime"]],
            ["Completed Anime", "completed anime"],
        )

    def test_empty_year_is_zeroed_and_keeps_estimate_assumption(self):
        result = calculate_history_insights(
            [], 2026, local_timezone=timezone.utc, minutes_per_episode=18
        )

        self.assertEqual(result["event_count"], 0)
        self.assertEqual(result["active_days"], 0)
        self.assertEqual(result["completed_anime"], [])
        self.assertEqual(result["estimated_minutes"], 0)
        self.assertEqual(result["minutes_per_episode"], 18)
        self.assertEqual(len(result["months"]), 12)
        self.assertTrue(all(month["event_count"] == 0 for month in result["months"]))

    def test_invalid_year_duration_timezone_and_event_iterable_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_history_insights([], True)
        with self.assertRaises(ValueError):
            calculate_history_insights([], 10000)
        with self.assertRaises(ValueError):
            calculate_history_insights([], 2026, minutes_per_episode=-1)
        with self.assertRaises(ValueError):
            calculate_history_insights([], 2026, local_timezone="UTC")
        with self.assertRaises(ValueError):
            calculate_history_insights(None, 2026)


class LocalTimezoneTests(unittest.TestCase):
    def test_configured_timezone_fallback_preserves_daylight_saving_rules(self):
        with patch("aniyori.timezones.Path.open", side_effect=OSError("unavailable")):
            with patch.dict("os.environ", {"TZ": "America/New_York"}):
                local_timezone = get_local_timezone()

        self.assertEqual(local_timezone.key, "America/New_York")
        winter = datetime(2026, 1, 1, tzinfo=local_timezone)
        summer = datetime(2026, 7, 1, tzinfo=local_timezone)
        self.assertNotEqual(winter.utcoffset(), summer.utcoffset())


if __name__ == "__main__":
    unittest.main()
