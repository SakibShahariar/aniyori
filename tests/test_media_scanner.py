"""Tests for deterministic local media file discovery."""

import tempfile
import unittest
from pathlib import Path

from aniyori.services.media_scanner import scan_video_files


class MediaScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_finds_video_extensions_recursively_case_insensitively(self):
        first = self.root / "Series" / "Season 1" / "Episode 01.MKV"
        second = self.root / "Series" / "Episode 02.mp4"
        ignored = self.root / "Series" / "notes.txt"
        first.parent.mkdir(parents=True)
        first.touch()
        second.touch()
        ignored.touch()

        expected = sorted(
            [first.absolute(), second.absolute()], key=lambda path: str(path).casefold()
        )
        self.assertEqual(scan_video_files([self.root]), expected)

    def test_ignores_common_cache_and_system_directories(self):
        media = self.root / "Anime" / "episode.mkv"
        cached = self.root / ".cache" / "episode.mkv"
        git_file = self.root / ".git" / "objects" / "episode.mkv"
        media.parent.mkdir(parents=True)
        cached.parent.mkdir(parents=True)
        git_file.parent.mkdir(parents=True)
        media.touch()
        cached.touch()
        git_file.touch()

        self.assertEqual(scan_video_files([self.root]), [media.absolute()])

    def test_skips_missing_roots_and_deduplicates_overlapping_roots(self):
        media = self.root / "Anime" / "episode.mkv"
        media.parent.mkdir()
        media.touch()

        results = scan_video_files(
            [self.root / "missing", self.root, media.parent]
        )

        self.assertEqual(results, [media.absolute()])

    def test_skips_symlinked_files_and_directories(self):
        real_dir = self.root / "real"
        real_dir.mkdir()
        real_file = real_dir / "episode.mkv"
        real_file.touch()
        linked_file = self.root / "linked.mkv"
        linked_dir = self.root / "linked-dir"
        try:
            linked_file.symlink_to(real_file)
            linked_dir.symlink_to(real_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links are unavailable on this platform")

        self.assertEqual(scan_video_files([self.root]), [real_file.absolute()])

    def test_honours_custom_excluded_directory_names(self):
        excluded = self.root / "Archive"
        excluded.mkdir()
        (excluded / "old.mkv").touch()

        self.assertEqual(
            scan_video_files([self.root], excluded_directories={"Archive"}), []
        )

    def test_cancellation_stops_discovery(self):
        (self.root / "episode.mkv").touch()

        self.assertEqual(
            scan_video_files([self.root], is_cancelled=lambda: True), []
        )

    def test_nonexistent_and_file_roots_are_ignored(self):
        file_root = self.root / "not-a-folder.mkv"
        file_root.touch()

        self.assertEqual(
            scan_video_files([file_root, self.root / "missing"]), []
        )


if __name__ == "__main__":
    unittest.main()
