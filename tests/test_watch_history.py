"""Tests for durable watch-history recording, filtering, and pruning."""

import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry, WatchStatus
from aniyori.storage import LibraryStorage


class WatchHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = LibraryStorage(Path(self.temp.name) / "library.sqlite3")
        self.storage.add(AnimeEntry(title="Frieren", episodes_total=12))
        self.entry = self.storage.list_entries()[0]

    def tearDown(self):
        self.temp.cleanup()

    def test_manual_progress_and_status_transitions_are_recorded(self):
        self.storage.update_progress(self.entry.storage_id, 1)
        history = self.storage.list_watch_history()
        self.assertEqual([item["action"] for item in history], ["status", "episode"])
        self.assertEqual(history[0]["details"], "planning → watching")
        self.assertEqual(history[1]["episode"], 1)
        self.assertEqual(history[1]["source"], "manual")

    def test_progress_source_can_identify_automatic_player_updates(self):
        self.storage.update_progress(self.entry.storage_id, 1, source="player")
        event = self.storage.list_watch_history(action="episode")[0]
        self.assertEqual(event["source"], "player")

    def test_bulk_progress_and_status_changes_are_recorded(self):
        self.storage.update_progress_many({self.entry.storage_id: 2}, source="bulk")
        updated = AnimeEntry(
            title=self.entry.title, episodes_total=12, episodes_watched=2,
            status=WatchStatus.PAUSED, storage_id=self.entry.storage_id,
        )
        self.storage.update_entry(updated)
        history = self.storage.list_watch_history()
        self.assertEqual({item["action"] for item in history}, {"progress", "status"})
        self.assertTrue(any(item["source"] == "bulk" for item in history))

    def test_explicit_episode_event_is_recorded_and_survives_restart(self):
        event_id = self.storage.record_watch_event(
            self.entry.storage_id, episode=3, action="episode",
            source="player", details="Playback reached the end.",
        )
        restarted = LibraryStorage(self.storage.path)
        event = restarted.list_watch_history()[0]
        self.assertEqual(event["id"], event_id)
        self.assertEqual(event["episode"], 3)
        self.assertEqual(event["source"], "player")
        self.assertEqual(event["details"], "Playback reached the end.")


    def test_episode_state_migrates_legacy_count_and_derives_progress(self):
        self.storage.update_progress(self.entry.storage_id, 2)
        progress = self.storage.set_episode_watched(self.entry.storage_id, 4)
        self.assertEqual(progress, 3)
        self.assertEqual(
            self.storage.list_episode_progress(self.entry.storage_id),
            {1: True, 2: True, 4: True},
        )
        self.assertEqual(self.storage.list_entries()[0].episodes_watched, 3)

    def test_episode_can_be_unwatched_and_rewatched_without_losing_history(self):
        self.storage.set_episode_watched(self.entry.storage_id, 1)
        self.storage.set_episode_watched(self.entry.storage_id, 1, False)
        self.storage.set_episode_watched(self.entry.storage_id, 1, True)
        self.assertEqual(self.storage.list_entries()[0].episodes_watched, 1)
        events = self.storage.list_watch_history(action="episode")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["details"], "Rewatched episode")

    def test_episode_tracking_rejects_invalid_or_out_of_range_values(self):
        for episode in (0, -1, 13, True):
            with self.subTest(episode=episode), self.assertRaises(ValueError):
                self.storage.set_episode_watched(self.entry.storage_id, episode)
        with self.assertRaises(ValueError):
            self.storage.set_episode_watched(self.entry.storage_id, 1, "yes")
        with self.assertRaises(ValueError):
            self.storage.list_episode_progress(999)

    def test_history_can_be_filtered_by_anime_action_and_date(self):
        self.storage.update_progress(self.entry.storage_id, 1)
        all_events = self.storage.list_watch_history()
        day = str(all_events[0]["created_at"])[:10]
        filtered = self.storage.list_watch_history(
            anime="fri", date_filter=day, action="episode"
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["action"], "episode")
        self.assertEqual(
            self.storage.list_watch_history(anime="does not exist"), []
        )

    def test_selected_removal_pruning_and_clear(self):
        first = self.storage.record_watch_event(
            self.entry.storage_id, episode=1, action="episode"
        )
        second = self.storage.record_watch_event(
            self.entry.storage_id, episode=2, action="episode"
        )
        self.assertEqual(self.storage.remove_watch_history([first, first]), 1)
        self.assertEqual(len(self.storage.list_watch_history()), 1)
        self.assertEqual(self.storage.prune_watch_history("9999-12-31"), 1)
        self.assertEqual(self.storage.clear_watch_history(), 0)

    def test_history_is_preserved_when_anime_is_removed(self):
        self.storage.record_watch_event(
            self.entry.storage_id, episode=1, action="episode"
        )
        self.storage.remove(self.entry.storage_id)
        self.assertEqual(len(self.storage.list_watch_history()), 1)
        self.assertEqual(self.storage.list_watch_history()[0]["anime_title"], "Frieren")

    def test_year_query_uses_local_calendar_boundaries(self):
        first = self.storage.record_watch_event(
            self.entry.storage_id, episode=1, action="episode"
        )
        second = self.storage.record_watch_event(
            self.entry.storage_id, episode=2, action="episode"
        )
        with self.storage._connect() as connection:
            connection.execute(
                "UPDATE watch_history SET created_at = ? WHERE id = ?",
                ("2025-12-31 23:00:00", first),
            )
            connection.execute(
                "UPDATE watch_history SET created_at = ? WHERE id = ?",
                ("2026-01-01 05:00:00", second),
            )

        from datetime import timedelta, timezone
        local_zone = timezone(timedelta(hours=-5))
        previous_year = self.storage.list_watch_history_for_year(
            2025, local_timezone=local_zone
        )
        current_year = self.storage.list_watch_history_for_year(
            2026, local_timezone=local_zone
        )

        self.assertEqual([item["id"] for item in previous_year], [first])
        self.assertEqual([item["id"] for item in current_year], [second])

    def test_year_query_rejects_invalid_year_and_timezone(self):
        for year in (True, 0, 10000, "2026"):
            with self.subTest(year=year), self.assertRaises(ValueError):
                self.storage.list_watch_history_for_year(year)
        with self.assertRaises(ValueError):
            self.storage.list_watch_history_for_year(2026, local_timezone="UTC")

    def test_rejects_invalid_history_filters_and_event_data(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            self.storage.list_watch_history(date_filter="yesterday")
        with self.assertRaisesRegex(ValueError, "positive"):
            self.storage.record_watch_event(self.entry.storage_id, episode=0)
        with self.assertRaisesRegex(ValueError, "action"):
            self.storage.list_watch_history(action="unknown")


if __name__ == "__main__":
    unittest.main()
