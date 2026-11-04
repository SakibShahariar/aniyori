"""Tests for notification preferences, deduplication, and persistent history."""

import json
import tempfile
import unittest
from pathlib import Path

from aniyori.services.notifications import (
    EVENT_TYPES, NotificationError, NotificationPreferences, NotificationStore,
)


class NotificationStoreTests(unittest.TestCase):
    def test_add_list_dismiss_and_clear_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "notifications.json")
            first = store.add("release_match", "info", "New release", "Frieren episode 4")
            second = store.add("backup", "info", "Backup complete", "Saved archive")
            self.assertEqual([item.notification_id for item in store.list()], [
                second.notification_id, first.notification_id,
            ])
            self.assertEqual(store.dismiss([first.notification_id]), 1)
            self.assertEqual([item.title for item in store.list(include_dismissed=False)], [
                "Backup complete",
            ])
            self.assertEqual(store.clear_dismissed(), 1)
            self.assertEqual(len(store.list()), 1)

    def test_deduplicates_repeated_events_and_caps_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "notifications.json")
            first = store.add("webhook_error", "warning", "Delivery failed", "offline", dedupe_key="hook:1")
            self.assertIsNotNone(first)
            self.assertIsNone(store.add("webhook_error", "warning", "Delivery failed", "offline", dedupe_key="hook:1"))

    def test_preferences_filter_event_types_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "notifications.json")
            prefs = NotificationPreferences(("backup", "webhook_error"), True, "warning")
            store.save_preferences(prefs)
            self.assertEqual(store.preferences(), prefs)
            self.assertIsNone(store.add("release_match", "info", "New", "release"))
            self.assertIsNotNone(store.add("backup", "info", "Done", "saved"))

    def test_minimum_severity_filters_lower_priority_events(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "notifications.json")
            store.save_preferences(NotificationPreferences(EVENT_TYPES, False, "warning"))
            self.assertIsNone(store.add("release_match", "info", "New", "release"))
            self.assertIsNone(store.add("webhook_error", "info", "Failure", "ignored"))
            self.assertIsNotNone(store.add("webhook_error", "warning", "Failure", "saved"))
            self.assertIsNotNone(store.add("download_failure", "error", "Failure", "saved"))

    def test_persists_private_file_and_rejects_corrupt_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notifications.json"
            store = NotificationStore(path)
            store.add("backup", "info", "Done", "saved")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(NotificationError, "invalid JSON"):
                store.list()

    def test_rejects_invalid_preferences_and_notifications(self):
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory) / "notifications.json")
            with self.assertRaises(NotificationError):
                store.save_preferences(NotificationPreferences(("unknown",), False))
            with self.assertRaises(NotificationError):
                store.add("other", "info", "bad", "message")
            with self.assertRaises(NotificationError):
                store.add("backup", "critical", "bad", "message")


if __name__ == "__main__":
    unittest.main()
