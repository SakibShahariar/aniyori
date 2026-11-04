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

    def test_history_can_be_filtered_by_anime_action_and_date(self):
        self.storage.update_progress(self.entry.storage_id, 1)
        self.storage.record_watch_event(
            self.entry.storage_id, episode=1, action="episode", source="player"
        )
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

    def test_rejects_invalid_history_filters_and_event_data(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            self.storage.list_watch_history(date_filter="yesterday")
        with self.assertRaisesRegex(ValueError, "positive"):
            self.storage.record_watch_event(self.entry.storage_id, episode=0)
        with self.assertRaisesRegex(ValueError, "action"):
            self.storage.list_watch_history(action="unknown")


if __name__ == "__main__":
    unittest.main()
