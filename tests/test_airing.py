"""Tests for airing schedule presentation helpers."""

import unittest
from datetime import datetime, timezone

from aniyori.services.airing import format_airing_countdown


class AiringCountdownTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        self.timestamp = int(self.now.timestamp())

    def test_formats_minutes_hours_and_days(self):
        self.assertEqual(format_airing_countdown(13, self.timestamp + 300, now=self.now), "Episode 13 · in 5m")
        self.assertEqual(format_airing_countdown(14, self.timestamp + 7500, now=self.now), "Episode 14 · in 2h 5m")
        self.assertEqual(format_airing_countdown(15, self.timestamp + 176400, now=self.now), "Episode 15 · in 2d 1h")

    def test_expired_schedule_is_reported_as_airing_now(self):
        self.assertEqual(format_airing_countdown(16, self.timestamp - 1, now=self.now), "Episode 16 · airing now")

    def test_missing_or_invalid_schedule_has_no_label(self):
        for episode, airing_at in ((None, self.timestamp), (0, self.timestamp), (True, self.timestamp), (13, None), (13, 0), (13, True), ("13", self.timestamp)):
            with self.subTest(episode=episode, airing_at=airing_at):
                self.assertIsNone(format_airing_countdown(episode, airing_at, now=self.now))

    def test_naive_now_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            format_airing_countdown(13, self.timestamp, now=datetime(2026, 10, 31))


if __name__ == "__main__":
    unittest.main()
