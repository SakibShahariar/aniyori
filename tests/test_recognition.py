"""Tests for headless local video recognition orchestration."""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from aniyori.services.recognition import recognize_local_videos


class LocalVideoRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_classifies_matched_ambiguous_and_unparsed_files(self):
        files = [
            self.root / "[Group] Frieren - 05 [1080p].mkv",
            self.root / "[Group] Kimi no Nawa - 01 [1080p].mkv",
            self.root / "random clip.mkv",
        ]
        for path in files:
            path.touch()
        candidates = [
            {"id": 10, "title": "Frieren"},
            {"id": 20, "title": "Kimi no Na wa"},
            {"id": 21, "title": "Kimi no Nawa"},
        ]

        results = recognize_local_videos([self.root], candidates)
        by_name = {item.path.name: item.result.status for item in results}

        self.assertEqual(by_name[files[0].name], "matched")
        self.assertEqual(by_name[files[1].name], "ambiguous")
        self.assertEqual(by_name[files[2].name], "unparsed")

    def test_catalogue_generator_is_reused_for_every_file(self):
        first = self.root / "[Group] Frieren - 01.mkv"
        second = self.root / "[Group] Frieren - 02.mkv"
        first.touch()
        second.touch()
        candidates = (item for item in [{"id": 10, "title": "Frieren"}])

        results = recognize_local_videos([self.root], candidates)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(item.result.status == "matched" for item in results))

    def test_manual_override_is_applied_to_local_releases(self):
        path = self.root / "[Group] Spy Family - 01.mkv"
        path.touch()
        candidates = [
            {"id": 10, "title": "Spy x Family"},
            {"id": 20, "title": "Family Spy"},
        ]

        results = recognize_local_videos(
            [self.root], candidates, overrides={"spy family": 20}
        )

        self.assertEqual(results[0].result.decision.best_match.media_id, 20)
        self.assertTrue(results[0].result.decision.overridden)

    def test_filename_exclusion_skips_catalogue_recognition(self):
        path = self.root / "sample.mkv"
        path.touch()
        with patch("aniyori.services.recognition.match_release_filename") as matcher:
            results = recognize_local_videos(
                [self.root],
                [{"id": 10, "title": "Frieren"}],
                exclusions=[{"kind": "filename", "pattern": "*.mkv"}],
            )
        matcher.assert_not_called()
        self.assertIn("Excluded filename", results[0].excluded_reason)

    def test_recognition_exclusions_mark_files(self):
        path = self.root / "[BadGroup] Frieren - 01.mkv"
        path.touch()
        results = recognize_local_videos(
            [self.root],
            [{"id": 10, "title": "Frieren"}],
            exclusions=[{"kind": "release_group", "pattern": "BadGroup"}],
        )
        self.assertEqual(len(results), 1)
        self.assertIn("Excluded release group", results[0].excluded_reason)

    def test_excluded_directories_are_respected(self):
        excluded = self.root / "Archive"
        excluded.mkdir()
        (excluded / "[Group] Frieren - 01.mkv").touch()

        results = recognize_local_videos(
            [self.root],
            [{"id": 10, "title": "Frieren"}],
            excluded_directories={"Archive"},
        )

        self.assertEqual(results, [])

    def test_cancellation_returns_no_later_recognition_results(self):
        (self.root / "[Group] Frieren - 01.mkv").touch()

        results = recognize_local_videos(
            [self.root],
            [{"id": 10, "title": "Frieren"}],
            is_cancelled=lambda: True,
        )

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
