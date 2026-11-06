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

    def match(self, filename, candidates=None, size_bytes=None):
        path = self.root / filename
        path.touch()
        return LocalVideoMatch(
            path=path,
            result=match_release_filename(
                filename, self.candidates if candidates is None else candidates
            ),
            size_bytes=size_bytes,
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

    def test_reports_next_available_unwatched_episode_and_file_size(self):
        matches = [
            self.match("[Group] Frieren - 01.mkv", size_bytes=1024),
            self.match("[Group] Frieren - 02.mkv", size_bytes=2048),
            self.match("[Group] Frieren - 03.mkv", size_bytes=4096),
        ]

        inventory, = summarize_episode_inventory(
            matches,
            [self.entry],
            watched_episodes={"10": {1, 3}},
        )

        self.assertEqual(inventory.next_unwatched_episode, 2)
        self.assertEqual(inventory.size_bytes, 7168)
        self.assertTrue(inventory.size_complete)
        self.assertEqual(len(inventory.source_paths), 3)

    def test_uses_legacy_aggregate_progress_when_explicit_state_is_absent(self):
        entry = AnimeEntry(
            title="Frieren", provider="anilist", provider_id="10",
            episodes_total=5, episodes_watched=2,
        )
        matches = [
            self.match("[Group] Frieren - 01.mkv", size_bytes=10),
            self.match("[Group] Frieren - 02.mkv", size_bytes=10),
            self.match("[Group] Frieren - 03.mkv", size_bytes=10),
        ]

        inventory, = summarize_episode_inventory(matches, [entry])

        self.assertEqual(inventory.next_unwatched_episode, 3)

    def test_incomplete_scan_does_not_claim_missing_or_next_episode(self):
        matches = [self.match("[Group] Frieren - 01.mkv", size_bytes=1024)]

        inventory, = summarize_episode_inventory(
            matches, [self.entry], scan_complete=False, size_complete=False
        )

        self.assertEqual(inventory.missing_episodes, ())
        self.assertFalse(inventory.missing_complete)
        self.assertIsNone(inventory.next_unwatched_episode)
        self.assertFalse(inventory.size_complete)

    def test_unknown_file_size_is_not_reported_as_a_complete_total(self):
        matches = [self.match("[Group] Frieren - 01.mkv")]

        inventory, = summarize_episode_inventory(matches, [self.entry])

        self.assertEqual(inventory.size_bytes, 0)
        self.assertFalse(inventory.size_complete)

    def test_only_anilist_entries_are_included(self):
        manual = AnimeEntry(title="Manual")
        inventory = summarize_episode_inventory([], [manual])

        self.assertEqual(inventory, ())


if __name__ == "__main__":
    unittest.main()
