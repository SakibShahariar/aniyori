"""Tests for ordered, persistent release classification rules."""

import tempfile
import unittest
from pathlib import Path

from aniyori.services.release_rules import (
    ReleaseRule, ReleaseRuleError, ReleaseRuleStore,
    evaluate_release_rules, normalize_release_rules,
)


class ReleaseRuleTests(unittest.TestCase):
    def test_first_matching_rule_determines_classification_and_reason(self):
        rules = (
            ReleaseRule("prefer", "Prefer GroupA", "release_group", "GroupA", "prefer", 0),
            ReleaseRule("exclude", "Discard low resolution", "resolution", "480p", "exclude", 1),
            ReleaseRule("include", "Include Frieren", "title", "Frieren", "include", 2),
        )
        preferred = evaluate_release_rules(
            {"title": "Frieren - 01", "release_group": "GroupA", "resolution": "480p"}, rules
        )
        self.assertEqual(preferred.status, "preferred")
        self.assertEqual(preferred.rule_id, "prefer")
        self.assertIn("Prefer GroupA", preferred.reason)
        discarded = evaluate_release_rules(
            {"title": "Frieren - 01", "release_group": "Other", "resolution": "480p"}, rules
        )
        self.assertEqual(discarded.status, "discarded")
        self.assertEqual(evaluate_release_rules({"title": "Frieren"}, rules[2:]).status, "wanted")
        self.assertEqual(evaluate_release_rules({"title": "Other"}, rules).status, "unmatched")

    def test_episode_keywords_and_disabled_rules(self):
        rules = (
            ReleaseRule("disabled", "Disabled", "keywords", "Frieren", "exclude", 0, False),
            ReleaseRule("episode", "Episode two", "episode", "2", "include", 1),
        )
        decision = evaluate_release_rules(
            {"title": "Example release", "episode": 2, "summary": "Frieren"}, rules
        )
        self.assertEqual(decision.status, "wanted")

    def test_store_adds_edits_reorders_removes_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ReleaseRuleStore(Path(directory) / "rules.json")
            added = store.add("Prefer group", "release_group", "GroupA", "prefer")
            first_id = added[0].rule_id
            store.add("Exclude 480p", "resolution", "480p", "exclude")
            store.update(first_id, name="Prefer trusted group", enabled=False)
            reordered = store.reorder([added[1].rule_id, first_id])
            self.assertEqual(reordered[0].name, "Exclude 480p")
            self.assertEqual(reordered[1].name, "Prefer trusted group")
            self.assertFalse(reordered[1].enabled)
            self.assertEqual(ReleaseRuleStore(store.path).load(), reordered)
            self.assertEqual(len(store.remove(first_id)), 1)

    def test_invalid_rules_and_duplicate_ids_are_rejected(self):
        invalid = (
            ReleaseRule("x", "Bad episode", "episode", "0", "include"),
            ReleaseRule("x", "Bad action", "title", "Frieren", "download"),
            ReleaseRule("x", "Bad field", "uploader", "GroupA", "prefer"),
        )
        for rule in invalid:
            with self.subTest(rule=rule), self.assertRaises(ReleaseRuleError):
                normalize_release_rules([rule])
        with self.assertRaisesRegex(ReleaseRuleError, "unique"):
            normalize_release_rules([
                ReleaseRule("same", "One", "title", "A", "include"),
                ReleaseRule("same", "Two", "title", "B", "exclude"),
            ])
        with tempfile.TemporaryDirectory() as directory:
            store = ReleaseRuleStore(Path(directory) / "rules.json")
            store.add("Rule", "title", "Frieren", "include")
            with self.assertRaisesRegex(ReleaseRuleError, "every configured rule"):
                store.reorder([])

    def test_malformed_saved_json_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseRuleError, "invalid JSON"):
                ReleaseRuleStore(path).load()
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
    unittest.main()
