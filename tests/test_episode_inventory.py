"""Tests for local episode availability summaries."""

import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry
from aniyori.services.matching import match_release_filename
from aniyori.services.recognition import LocalVideoMatch
from aniyori.services.episode_inventory import summarize_episode_inventory


class EpisodeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.entry = AnimeEntry(
            title="Frieren", provider="anilist", provider_id="10",
            episodes_total=5,
        )
        self.candidates = [{"id": 10, "title": "Frieren"}]

    def tearDown(self):
        self.temp_dir.cleanup()

    def match(self, filename, candidates=None):
        path = self.root / filename
        path.touch()
        return LocalVideoMatch(
            path=path,
            result=match_release_filename(
                filename, self.candidates if candidates is None else candidates
            ),
        )

    def test_reports_available_missing_and_next_episode(self):
        matches = [
            self.match("[Group] Frieren - 01.mkv"),
            self.match("[Group] Frieren - 02.mkv"),
            self.match("[Group] Frieren - 04.mkv"),
        ]

        inventory, = summarize_episode_inventory(matches, [self.entry])

        self.assertEqual(inventory.available_episodes, (1, 2, 4))
        self.assertEqual(inventory.missing_episodes, (3, 5))
        self.assertEqual(inventory.next_episode, 3)

    def test_duplicate_releases_count_once(self):
        matches = [
            self.match("[Group A] Frieren - 01.mkv"),
            self.match("[Group B] Frieren - 01 [1080p].mkv"),
        ]

        inventory, = summarize_episode_inventory(matches, [self.entry])

        self.assertEqual(inventory.available_episodes, (1,))
        self.assertEqual(inventory.missing_episodes, (2, 3, 4, 5))

    def test_ambiguous_unparsed_and_unmatched_files_are_ignored(self):
        matches = [
            self.match("[Group] Frieren - 01.mkv"),
            self.match("[Group] random clip.mkv"),
            self.match(
                "[Group] Kimi no Nawa - 02.mkv",
                [{"id": 20, "title": "Kimi no Na wa"},
                 {"id": 21, "title": "Kimi no Nawa"}],
            ),
        ]

        inventory, = summarize_episode_inventory(matches, [self.entry])

        self.assertEqual(inventory.available_episodes, (1,))
        self.assertEqual(inventory.missing_episodes, (2, 3, 4, 5))

    def test_season_local_numbers_are_not_compared_to_overall_total(self):
        matches = [self.match("[Group] Frieren S02E01.mkv")]

        inventory, = summarize_episode_inventory(matches, [self.entry])

        self.assertEqual(inventory.available_episodes, ())
        self.assertEqual(inventory.missing_episodes, ())
        self.assertIsNone(inventory.next_episode)
        self.assertEqual(inventory.seasoned_episodes, ((2, (1,)),))

    def test_mixed_seasoned_and_unseasoned_numbering_is_conservative(self):
        matches = [
            self.match("[Group] Frieren - 01.mkv"),
            self.match("[Group] Frieren S02E01.mkv"),
        ]

        inventory, = summarize_episode_inventory(matches, [self.entry])

        self.assertEqual(inventory.available_episodes, (1,))
        self.assertEqual(inventory.missing_episodes, ())
        self.assertIsNone(inventory.next_episode)

    def test_unknown_total_uses_highest_available_as_next_episode(self):
        entry = AnimeEntry(title="Frieren", provider="anilist", provider_id="10")
        matches = [self.match("[Group] Frieren - 01.mkv"),
                   self.match("[Group] Frieren - 03.mkv")]

        inventory, = summarize_episode_inventory(matches, [entry])

        self.assertEqual(inventory.missing_episodes, ())
        self.assertEqual(inventory.next_episode, 4)

    def test_library_entries_without_files_are_reported_as_missing(self):
        inventory, = summarize_episode_inventory([], [self.entry])

        self.assertEqual(inventory.available_episodes, ())
        self.assertEqual(inventory.missing_episodes, (1, 2, 3, 4, 5))
        self.assertEqual(inventory.next_episode, 1)

    def test_only_anilist_entries_are_included(self):
        manual = AnimeEntry(title="Manual")
        inventory = summarize_episode_inventory([], [manual])

        self.assertEqual(inventory, ())


if __name__ == "__main__":
    unittest.main()
