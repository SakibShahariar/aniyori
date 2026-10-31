"""Tests for deterministic release-quality scoring."""

import unittest

from aniyori.services.release_scoring import (
    DEFAULT_WEIGHTS, rank_releases, score_release,
)


class ReleaseScoringTests(unittest.TestCase):
    def test_complete_release_gets_explainable_score(self):
        result = score_release({
            "resolution": "1080p", "source": "BluRay", "audio": "FLAC",
            "subtitles": "Multi", "release_group": "GoodGroup",
            "file_size_mb": 1500, "seeders": 80,
        }, preferred_groups={"goodgroup"})

        self.assertGreater(result.score, 80)
        self.assertEqual(len(result.factors), 7)
        self.assertIn("Resolution 1080p", result.explanation)
        self.assertIn("Release group GoodGroup is preferred", result.explanation)

    def test_missing_metadata_is_omitted_not_penalized(self):
        partial = score_release({"resolution": "1080p"})
        full = score_release({
            "resolution": "1080p", "source": None, "audio": None,
            "subtitles": None, "release_group": None,
            "file_size_mb": None, "seeders": None,
        })
        self.assertEqual(partial.score, full.score)
        self.assertEqual([factor.name for factor in partial.factors], ["resolution"])

    def test_rejected_group_scores_below_preferred_group(self):
        release = {"resolution": "1080p", "release_group": "GroupA"}
        preferred = score_release(release, preferred_groups={"groupa"})
        rejected = score_release(release, rejected_groups={"groupa"})
        self.assertGreater(preferred.score, rejected.score)
        self.assertIn("rejected", rejected.explanation)

    def test_custom_weights_change_factor_influence(self):
        release = {"resolution": "720p", "source": "BluRay"}
        default = score_release(release)
        source_heavy = score_release(release, weights={"resolution": 0.01, "source": 0.99})
        self.assertGreater(source_heavy.score, default.score)

    def test_rank_is_descending_and_stable_for_ties(self):
        first = {"resolution": "1080p", "source": "BluRay"}
        second = {"resolution": "720p", "source": "HDTV"}
        tie_a = {"resolution": "1080p"}
        tie_b = {"resolution": "1080p"}
        ranked = rank_releases([second, tie_a, tie_b, first])
        self.assertEqual(ranked[0][0], first)
        self.assertEqual(ranked[1][0], tie_a)
        self.assertEqual(ranked[2][0], tie_b)

    def test_missing_all_metadata_returns_zero_without_factors(self):
        result = score_release({})
        self.assertEqual(result.score, 0)
        self.assertEqual(result.factors, ())
        self.assertIn("No supported", result.explanation)

    def test_invalid_weight_names_and_values_are_rejected(self):
        for weights in (
            {"unknown": 1}, {"resolution": -1}, {"audio": float("nan")},
            {"seeders": True}, {key: 0 for key in DEFAULT_WEIGHTS},
        ):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                score_release({}, weights=weights)

    def test_preferences_push_rejected_releases_below_accepted_releases(self):
        accepted = {"resolution": "1080p", "source": "BluRay"}
        rejected = {"resolution": "1080p", "source": "CAM"}
        ranked = rank_releases(
            [rejected, accepted],
            preferences={"source": {"rejected": ["CAM"]}},
        )
        self.assertEqual(ranked[0][0], accepted)
        self.assertFalse(ranked[1][1].accepted)
        self.assertIn("Rejected: source is CAM", ranked[1][1].explanation)

    def test_invalid_numeric_metadata_is_ignored(self):
        result = score_release({
            "resolution": True, "file_size_mb": float("inf"), "seeders": -2,
        })
        self.assertEqual(result.score, 0)
        self.assertEqual(result.factors, ())


if __name__ == "__main__":
    unittest.main()
