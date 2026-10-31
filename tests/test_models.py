"""Tests for the UI-independent library model."""

import unittest

from aniyori.models import (
    MAX_EPISODE_COUNT,
    AnimeEntry,
    WatchStatus,
    parse_episode_count,
)


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
        self.assertEqual(entry.progress_label, "2 / ? episodes")

    def test_empty_title_is_rejected(self):
        with self.assertRaises(ValueError):
            AnimeEntry(title="  ")

    def test_watched_count_cannot_exceed_total(self):
        with self.assertRaises(ValueError):
            AnimeEntry(title="Example", episodes_total=4, episodes_watched=5)

    def test_negative_episode_count_is_rejected(self):
        with self.assertRaises(ValueError):
            AnimeEntry(title="Example", episodes_watched=-1)

    def test_episode_count_parser_handles_optional_and_malformed_values(self):
        self.assertIsNone(parse_episode_count("  ", optional=True))
        self.assertEqual(parse_episode_count(" 12 "), 12)
        with self.assertRaisesRegex(ValueError, "whole number"):
            parse_episode_count("12.5")
        with self.assertRaisesRegex(ValueError, "required"):
            parse_episode_count("")

    def test_episode_count_parser_rejects_negative_and_implausible_values(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            parse_episode_count("-1")
        with self.assertRaisesRegex(ValueError, "10,000"):
            parse_episode_count(str(MAX_EPISODE_COUNT + 1))

    def test_model_rejects_implausibly_large_episode_counts(self):
        with self.assertRaisesRegex(ValueError, "10,000"):
            AnimeEntry(title="Too many", episodes_total=MAX_EPISODE_COUNT + 1)
        with self.assertRaisesRegex(ValueError, "10,000"):
            AnimeEntry(title="Too many watched", episodes_watched=MAX_EPISODE_COUNT + 1)

    def test_model_rejects_boolean_and_non_integer_episode_counts(self):
        invalid_values = (True, False, 1.5, "3")
        for value in invalid_values:
            with self.subTest(field="episodes_total", value=value):
                with self.assertRaisesRegex(ValueError, "whole number"):
                    AnimeEntry(title="Example", episodes_total=value)
            with self.subTest(field="episodes_watched", value=value):
                with self.assertRaisesRegex(ValueError, "whole number"):
                    AnimeEntry(title="Example", episodes_watched=value)

    def test_model_rejects_invalid_status_and_optional_text_fields(self):
        with self.assertRaisesRegex(ValueError, "WatchStatus"):
            AnimeEntry(title="Example", status="watching")
        for field_name in ("provider", "provider_id", "cover_image"):
            with self.subTest(field=field_name):
                with self.assertRaisesRegex(ValueError, "must be text"):
                    AnimeEntry(title="Example", **{field_name: 42})
        with self.assertRaisesRegex(ValueError, "title must be text"):
            AnimeEntry(title=None)

    def test_model_rejects_invalid_storage_ids(self):
        for value in (0, -1, True, 1.5, "1"):
            with self.subTest(storage_id=value):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    AnimeEntry(title="Example", storage_id=value)


if __name__ == "__main__":
    unittest.main()
