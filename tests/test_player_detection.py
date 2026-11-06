"""Tests for opt-in MPRIS playback detection helpers."""

import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry
from aniyori.services.player_detection import (
    PlayerDetectionSettings,
    PlayerDetectionSettingsStore,
    local_media_path,
    match_playback_file,
    playback_finished,
    supported_player_names,
)


class PlayerDetectionTests(unittest.TestCase):
    def test_player_names_include_only_mpv_and_vlc(self):
        names = [
            "org.mpris.MediaPlayer2.mpv",
            "org.mpris.MediaPlayer2.mpv.instance123",
            "org.mpris.MediaPlayer2.vlc",
            "org.mpris.MediaPlayer2.vlc.instance",
            "org.mpris.MediaPlayer2.firefox",
            "org.mpris.MediaPlayer2.mpvacious",
            None,
        ]
        self.assertEqual(
            supported_player_names(names),
            (
                "org.mpris.MediaPlayer2.mpv",
                "org.mpris.MediaPlayer2.mpv.instance123",
                "org.mpris.MediaPlayer2.vlc",
                "org.mpris.MediaPlayer2.vlc.instance",
            ),
        )

    def test_local_media_path_rejects_remote_and_non_file_uris(self):
        self.assertIsNone(local_media_path("https:" + "//example.com/video.mkv"))
        self.assertIsNone(local_media_path("file://server/share/video.mkv"))
        self.assertIsNone(local_media_path("file:///tmp/video.mkv?token=secret"))
        self.assertIsNone(local_media_path("not a URI"))

    def test_matches_only_confident_local_episode_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "[SubsPlease] Frieren - 05 [1080p].mkv"
            path.touch()
            entries = [AnimeEntry(title="Frieren", storage_id=12)]
            self.assertEqual(match_playback_file(path.as_uri(), entries), (12, 5))
            self.assertIsNone(
                match_playback_file("https:" + "//example.com/Frieren-05.mkv", entries)
            )

    def test_unrecognized_and_ambiguous_files_do_not_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "[Group] Kimi no Nawa - 01 [1080p].mkv"
            path.touch()
            entries = [
                AnimeEntry(title="Kimi no Na wa", storage_id=1),
                AnimeEntry(title="Kimi no Nawa", storage_id=2),
            ]
            self.assertIsNone(match_playback_file(path.as_uri(), entries))

    def test_progress_requires_near_complete_known_duration(self):
        self.assertTrue(playback_finished(900, 1000))
        self.assertFalse(playback_finished(899, 1000))
        self.assertFalse(playback_finished(0, 0))
        self.assertFalse(playback_finished(True, 1000))
        self.assertFalse(playback_finished(1000, 1000, threshold=0))

    def test_settings_are_disabled_by_default_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "player-detection.json"
            store = PlayerDetectionSettingsStore(path)
            self.assertEqual(store.load(), PlayerDetectionSettings())
            store.save(PlayerDetectionSettings(True))
            self.assertEqual(store.load(), PlayerDetectionSettings(True))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_invalid_settings_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "player-detection.json"
            path.write_text(
                '{"format":"aniyori-player-detection","version":1,"enabled":"yes"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid"):
                PlayerDetectionSettingsStore(path).load()


if __name__ == "__main__":
    unittest.main()
