"""Tests for deterministic anime title matching."""
import unittest
from aniyori.services.matching import (
    match_anime_title,
    match_release_filename,
    normalize_anime_title,
)

CATALOGUE = [
    {"id": 10, "title": "Sousou no Frieren",
     "title_english": "Frieren: Beyond Journey's End",
     "title_native": "葬送のフリーレン"},
    {"id": 20, "title": "Spy x Family", "title_english": "SPY×FAMILY"},
]

class AnimeTitleMatchingTests(unittest.TestCase):
    def test_normalizes_unicode_punctuation_and_whitespace(self):
        self.assertEqual(normalize_anime_title("  SPY×FAMILY — PART  2 "),
                         "spy family part 2")
        self.assertEqual(normalize_anime_title("葬送のフリーレン"),
                         "葬送のフリーレン")

    def test_matches_any_catalogue_title_variant_exactly(self):
        result = match_anime_title("Frieren: Beyond Journey's End", CATALOGUE)
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best_match.media_id, 10)
        self.assertEqual(result.best_match.score, 1.0)

    def test_matches_extra_user_alias(self):
        result = match_anime_title("Frieren", CATALOGUE,
                                   aliases={10: ["Frieren", "Sousou no Frieren (2023)"]})
        self.assertEqual(result.best_match.media_id, 10)

    def test_manual_override_takes_precedence(self):
        result = match_anime_title("Spy Family", CATALOGUE,
                                   overrides={"spy family": 10})
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.best_match.media_id, 10)
        self.assertTrue(result.overridden)

    def test_override_to_missing_candidate_does_not_guess(self):
        result = match_anime_title("Spy Family", CATALOGUE,
                                   overrides={"spy family": 999})
        self.assertEqual(result.status, "no_match")
        self.assertIsNone(result.best_match)

    def test_close_candidates_are_ambiguous(self):
        candidates = [{"id": 1, "title": "Kimi no Na wa"},
                      {"id": 2, "title": "Kimi no Nawa"}]
        result = match_anime_title("Kimi no Nawa", candidates)
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.best_match)
        self.assertEqual({item.media_id for item in result.matches}, {1, 2})

    def test_unrelated_and_empty_titles_do_not_match(self):
        for title in ("", "   ", "Completely Different Show"):
            with self.subTest(title=title):
                result = match_anime_title(title, CATALOGUE)
                self.assertEqual(result.status, "no_match")

    def test_result_order_is_stable_when_candidate_order_changes(self):
        first = match_anime_title("Frieren", CATALOGUE, aliases={10: ["Frieren"]})
        second = match_anime_title("Frieren", list(reversed(CATALOGUE)),
                                   aliases={10: ["Frieren"]})
        self.assertEqual(first, second)

    def test_ignores_malformed_and_duplicate_candidates(self):
        candidates = [None, {"id": True, "title": "Example"},
                      {"id": 1, "title": ""}, {"id": 2, "title": "Example"},
                      {"id": 2, "title": "Different duplicate"}]
        result = match_anime_title("Example", candidates)
        self.assertEqual(result.status, "matched")
        self.assertEqual([item.media_id for item in result.matches], [2])

    def test_invalid_thresholds_are_rejected(self):
        with self.assertRaises(ValueError):
            match_anime_title("Example", [], minimum_score=1.1)
        with self.assertRaises(ValueError):
            match_anime_title("Example", [], ambiguity_margin=-0.1)

    def test_release_filename_parser_feeds_title_matching(self):
        result = match_release_filename(
            "[SubsPlease] Frieren: Beyond Journey's End - 05 [1080p].mkv",
            CATALOGUE,
        )
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.parsed.episode, 5)
        self.assertEqual(result.parsed.resolution, "1080p")
        self.assertEqual(result.decision.best_match.media_id, 10)

    def test_unparseable_filename_is_not_sent_to_catalogue_matcher(self):
        result = match_release_filename("random-video-file.mkv", CATALOGUE)
        self.assertEqual(result.status, "unparsed")
        self.assertIsNone(result.parsed)
        self.assertIsNone(result.decision.best_match)

    def test_ambiguous_release_filename_remains_unresolved(self):
        candidates = [
            {"id": 1, "title": "Kimi no Na wa"},
            {"id": 2, "title": "Kimi no Nawa"},
        ]
        result = match_release_filename(
            "[Group] Kimi no Nawa - 01 [1080p].mkv", candidates
        )
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.decision.best_match)

if __name__ == "__main__":
    unittest.main()
