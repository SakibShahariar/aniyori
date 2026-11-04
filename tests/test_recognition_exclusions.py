"""Tests for persisted recognition exclusions and matching behavior."""

import tempfile
import unittest
from pathlib import Path

from aniyori.services.recognition_exclusions import (
    RecognitionExclusionError, RecognitionExclusionStore, exclusion_reason,
)
from aniyori.services.matching import match_release_filename


class RecognitionExclusionTests(unittest.TestCase):
    def test_store_round_trip_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecognitionExclusionStore(Path(directory) / "exclusions.json")
            store.save_rules([
                {"kind": "folder", "pattern": str(Path(directory) / "Archive")},
                {"kind": "filename", "pattern": "*sample*.mkv"},
                {"kind": "title", "pattern": "*bad anime*"},
                {"kind": "release_group", "pattern": "BadGroup"},
            ])
            self.assertEqual(len(store.list_rules()), 4)
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_rejects_relative_folder_paths_and_path_based_filename_patterns(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecognitionExclusionStore(Path(directory) / "exclusions.json")
            for rule in (
                {"kind": "folder", "pattern": "relative/folder"},
                {"kind": "filename", "pattern": "folder/*.mkv"},
            ):
                with self.subTest(rule=rule), self.assertRaises(RecognitionExclusionError):
                    store.save_rules([rule])

    def test_rejects_duplicate_rules_without_overwriting_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecognitionExclusionStore(Path(directory) / "exclusions.json")
            store.save_rules([{"kind": "filename", "pattern": "*.mkv"}])
            original = store.path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(RecognitionExclusionError, "Duplicate"):
                store.save_rules([
                    {"kind": "filename", "pattern": "*.mkv"},
                    {"kind": "filename", "pattern": "*.MKV"},
                ])
            self.assertEqual(store.path.read_text(encoding="utf-8"), original)

    def test_matches_folder_and_filename_before_title_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "Archive"
            archive.mkdir()
            path = archive / "[BadGroup] Frieren - 01.mkv"
            rules = [
                {"kind": "folder", "pattern": str(archive)},
                {"kind": "filename", "pattern": "*.mkv"},
            ]
            self.assertIn("Excluded folder", exclusion_reason(path, None, None, rules))
            self.assertIn(
                "Excluded filename",
                exclusion_reason(root / "Other.mkv", None, None, rules[1:]),
            )

    def test_matches_parsed_anime_title_and_release_group(self):
        path = Path("[BadGroup] Frieren - 01.mkv")
        result = match_release_filename(path.name, [{"id": 1, "title": "Frieren"}])
        parsed = result.parsed
        best = result.decision.best_match
        self.assertIn(
            "Excluded anime title",
            exclusion_reason(path, parsed, best, [{"kind": "title", "pattern": "*frieren*"}]),
        )
        self.assertIn(
            "Excluded release group",
            exclusion_reason(path, parsed, best, [{"kind": "release_group", "pattern": "badgroup"}]),
        )

    def test_non_matching_rules_do_not_exclude(self):
        path = Path("[GoodGroup] Frieren - 01.mkv")
        result = match_release_filename(path.name, [{"id": 1, "title": "Frieren"}])
        self.assertIsNone(exclusion_reason(
            path, result.parsed, result.decision.best_match,
            [{"kind": "release_group", "pattern": "OtherGroup"}],
        ))


if __name__ == "__main__":
    unittest.main()
