"""Tests for safe share-template rendering and persistence."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aniyori.models import AnimeEntry, WatchStatus
from aniyori.services.share_templates import (
    DEFAULT_SHARE_TEMPLATE, ShareTemplateError, ShareTemplateStore,
    render_share_template, share_context_for_entry, validate_share_template,
)


class ShareTemplateTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            "title": "Frieren: Beyond Journey's End", "episode": 5,
            "total_episodes": 28, "progress": "18", "status": "watching",
            "timestamp": "2026-10-31T12:00+00:00",
        }

    def test_default_template_renders_supported_variables(self):
        self.assertEqual(
            render_share_template(DEFAULT_SHARE_TEMPLATE, self.values),
            "Frieren: Beyond Journey's End — Episode 5/28 (18%) · watching",
        )

    def test_conditional_sections_are_included_only_when_value_exists(self):
        template = "{title}[[if total_episodes]] ({episode}/{total_episodes})[[/if]]"
        self.assertEqual(render_share_template(template, self.values), "Frieren: Beyond Journey's End (5/28)")
        self.assertEqual(
            render_share_template(template, {**self.values, "total_episodes": ""}),
            "Frieren: Beyond Journey's End",
        )

    def test_basic_formatting_functions(self):
        template = "[[upper:title]] / [[lower:status]] / [[title:status]] / [[default:total_episodes:TBA]]"
        self.assertEqual(
            render_share_template(template, self.values),
            "FRIEREN: BEYOND JOURNEY'S END / watching / Watching / 28",
        )
        self.assertTrue(
            render_share_template(
                template, {**self.values, "total_episodes": ""}
            ).endswith("TBA")
        )

    def test_rejects_unknown_fields_and_malformed_templates(self):
        for template in ("{unknown}", "{title", "[[if unknown]]x[[/if]]", "[[if title]]x", "[[bogus:title]]"):
            with self.subTest(template=template), self.assertRaises(ShareTemplateError):
                validate_share_template(template)

    def test_validates_fields_inside_conditional_sections(self):
        with self.assertRaisesRegex(ShareTemplateError, "Unknown template field"):
            validate_share_template("[[if title]]{not_a_field}[[/if]]")

    def test_validates_fields_inside_formatting_functions(self):
        with self.assertRaisesRegex(ShareTemplateError, "Unknown template field"):
            validate_share_template("[[upper:not_a_field]]")

    def test_rejects_attribute_and_index_access(self):
        for template in ("{title.__class__}", "{title[0]}"):
            with self.subTest(template=template), self.assertRaises(ShareTemplateError):
                validate_share_template(template)

    def test_nested_conditionals_are_rejected_clearly(self):
        with self.assertRaisesRegex(ShareTemplateError, "Nested"):
            validate_share_template("[[if title]]a [[if status]]b[[/if]][[/if]]")

    def test_share_context_uses_entry_progress_and_timestamp(self):
        entry = AnimeEntry(
            title="Frieren", episodes_total=20, episodes_watched=5,
            status=WatchStatus.WATCHING,
        )
        timestamp = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        context = share_context_for_entry(entry, now=timestamp)
        self.assertEqual(context["progress"], "25")
        self.assertEqual(context["timestamp"], "2026-10-31T12:00+00:00")
        self.assertEqual(context["episode"], 5)

    def test_unknown_episode_total_has_empty_context_value(self):
        self.assertEqual(share_context_for_entry(AnimeEntry(title="Unknown"))["total_episodes"], "")

    def test_store_loads_default_and_persists_valid_template(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ShareTemplateStore(Path(directory) / "share.json")
            self.assertEqual(store.load(), DEFAULT_SHARE_TEMPLATE)
            store.save("{title} — {episode}")
            self.assertEqual(ShareTemplateStore(store.path).load(), "{title} — {episode}")

    def test_store_rejects_invalid_template_without_overwriting_saved_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ShareTemplateStore(Path(directory) / "share.json")
            store.save("{title}")
            original = store.path.read_text(encoding="utf-8")
            with self.assertRaises(ShareTemplateError):
                store.save("{unknown}")
            self.assertEqual(store.path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
