"""Tests for conservative anime release filename parsing."""

import unittest

from aniyori.filename_parser import parse_anime_filename


class AnimeFilenameParserTests(unittest.TestCase):
    def test_bracketed_fansub_release(self):
        parsed = parse_anime_filename(
            "[SubsPlease] One Piece - 1100 (1080p) [ABCDEF12].mkv"
        )
        self.assertEqual(parsed.title, "One Piece")
        self.assertEqual(parsed.episode, 1100)
        self.assertEqual(parsed.release_group, "SubsPlease")
        self.assertEqual(parsed.resolution, "1080p")

    def test_season_episode_notation(self):
        parsed = parse_anime_filename("Spy x Family.S02E03.1080p.WEB-DL-GROUP.mkv")
        self.assertEqual(parsed.title, "Spy x Family")
        self.assertEqual(parsed.season, 2)
        self.assertEqual(parsed.episode, 3)
        self.assertEqual(parsed.resolution, "1080p")
        self.assertEqual(parsed.source, "WEB-DL")
        self.assertIsNone(parsed.episode_title)

    def test_episode_title_and_version(self):
        parsed = parse_anime_filename(
            "[Group] Frieren - 05 - The Hero of the South v2 [720p].mkv"
        )
        self.assertEqual(parsed.title, "Frieren")
        self.assertEqual(parsed.episode, 5)
        self.assertEqual(parsed.episode_title, "The Hero of the South")
        self.assertEqual(parsed.version, 2)

    def test_episode_number_release_version_and_underscored_separators(self):
        parsed = parse_anime_filename(
            "[TaigaSubs]_Toradora!_(2008)_-_01v2_-_Tiger_and_Dragon_[1080p].mkv"
        )
        self.assertEqual(parsed.title, "Toradora! (2008)")
        self.assertEqual(parsed.episode, 1)
        self.assertEqual(parsed.version, 2)
        self.assertEqual(parsed.episode_title, "Tiger and Dragon")

    def test_accepts_paths_and_video_extensions(self):
        parsed = parse_anime_filename("/media/anime/Chainsaw Man - 12 [1080p].mp4")
        self.assertEqual(parsed.title, "Chainsaw Man")
        self.assertEqual(parsed.episode, 12)

    def test_windows_style_path_is_parsed_on_linux(self):
        parsed = parse_anime_filename(
            r"C:\Users\Example\Videos\Cowboy Bebop - 03 [1080p].mkv"
        )
        self.assertEqual(parsed.title, "Cowboy Bebop")
        self.assertEqual(parsed.episode, 3)

    def test_japanese_episode_marker(self):
        parsed = parse_anime_filename("Mob Psycho 100 第08話 [1080p].mkv")
        self.assertEqual(parsed.title, "Mob Psycho 100")
        self.assertEqual(parsed.episode, 8)

    def test_ambiguous_or_non_episode_names_are_not_guessed(self):
        for filename in (
            "", "not a release.mkv", "Movie Title (2024).mkv",
            "[Group] Some Anime 1080p.mkv", None,
        ):
            with self.subTest(filename=filename):
                self.assertIsNone(parse_anime_filename(filename))

    def test_invalid_input_type_is_safe(self):
        self.assertIsNone(parse_anime_filename(123))


if __name__ == "__main__":
    unittest.main()
