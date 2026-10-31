"""Tests for persistent release preferences and decision explanations."""

import json
import tempfile
import unittest
from pathlib import Path

from aniyori.services.release_preferences import (
    ReleasePreferenceError, ReleasePreferenceStore,
    evaluate_release_preferences, normalize_release_preferences,
)


class ReleasePreferenceTests(unittest.TestCase):
    def test_preferred_and_rejected_values_produce_explanations(self):
        preferences = {
            "resolution": {"preferred": ["1080p"], "rejected": ["480p"], "priority": 0},
            "source": {"preferred": ["BluRay"], "rejected": ["CAM"], "priority": 1},
        }
        decision = evaluate_release_preferences(
            {"resolution": "1080p", "source": "CAM"}, preferences
        )
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.matched_preferred, ("resolution",))
        self.assertEqual(decision.matched_rejected, ("source",))
        self.assertEqual(len(decision.explanations), 2)

    def test_missing_attributes_do_not_trigger_preferences(self):
        decision = evaluate_release_preferences(
            {"resolution": None}, {"resolution": {"preferred": ["1080p"], "rejected": ["480p"]}}
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.explanations, ())

    def test_preference_values_are_case_and_whitespace_insensitive(self):
        decision = evaluate_release_preferences(
            {"release_group": "  Good GROUP "},
            {"release_group": {"preferred": ["good group"]}},
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.matched_preferred, ("release_group",))

    def test_priorities_control_explanation_order(self):
        preferences = {
            "source": {"preferred": ["BluRay"], "priority": 9},
            "resolution": {"preferred": ["1080p"], "priority": 1},
        }
        decision = evaluate_release_preferences(
            {"source": "BluRay", "resolution": "1080p"}, preferences
        )
        self.assertEqual(decision.matched_preferred, ("resolution", "source"))

    def test_rejects_conflicting_or_malformed_preferences(self):
        invalid = (
            {"resolution": {"preferred": ["1080p"], "rejected": ["1080P"]}},
            {"resolution": {"preferred": [""]}},
            {"resolution": {"preferred": "1080p"}},
            {"resolution": {"priority": -1}},
            {"unknown": {"preferred": ["value"]}},
        )
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ReleasePreferenceError):
                normalize_release_preferences(payload)

    def test_store_defaults_and_round_trips_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReleasePreferenceStore(Path(directory) / "prefs.json")
            self.assertEqual(len(store.load()), 5)
            values = {
                "resolution": {"preferred": ["1080p", "2160p"], "rejected": ["480p"], "priority": 0},
                "audio": {"preferred": ["FLAC"], "rejected": [], "priority": 1},
            }
            store.save(values)
            loaded = ReleasePreferenceStore(store.path).load()
            by_name = {item.attribute: item for item in loaded}
            self.assertEqual(by_name["resolution"].preferred, ("1080p", "2160p"))
            self.assertEqual(by_name["audio"].preferred, ("flac",))

    def test_malformed_saved_preferences_are_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prefs.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ReleasePreferenceError, "invalid JSON"):
                ReleasePreferenceStore(path).load()
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
    unittest.main()
