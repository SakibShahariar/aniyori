"""Tests for the UI-independent library model."""

import unittest

from aniyori.models import AnimeEntry, WatchStatus


class AnimeEntryTests(unittest.TestCase):
    def test_progress_fraction(self):
        entry = AnimeEntry(
            title="Example Series",
            episodes_total=12,
            episodes_watched=3,
            status=WatchStatus.WATCHING,
        )
        self.assertEqual(entry.progress_fraction, 0.25)
        self.assertEqual(entry.progress_label, "3 / 12 episodes")

    def test_unknown_total_has_no_fraction(self):
        entry = AnimeEntry(title="Airing Series", episodes_watched=2)
        self.assertIsNone(entry.progress_fraction)
        self.assertEqual(entry.progress_label, "2 watched")

    def test_empty_title_is_rejected(self):
        with self.assertRaises(ValueError):
            AnimeEntry(title="  ")

    def test_watched_count_cannot_exceed_total(self):
        with self.assertRaises(ValueError):
            AnimeEntry(title="Example", episodes_total=4, episodes_watched=5)

    def test_negative_episode_count_is_rejected(self):
        with self.assertRaises(ValueError):
            AnimeEntry(title="Example", episodes_watched=-1)


if __name__ == "__main__":
    unittest.main()
