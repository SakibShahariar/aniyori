"""Tests for validated external-link templates and persistence."""

import tempfile
import unittest
from pathlib import Path

from aniyori.models import AnimeEntry
from aniyori.services.external_links import (
    ExternalLinkError, ExternalLinkStore, links_for_entry,
    render_link_template, validate_link_template,
)


class ExternalLinkTests(unittest.TestCase):
    def test_default_links_use_only_valid_identifiers(self):
        links = links_for_entry(AnimeEntry(
            title="Frieren: Beyond Journey's End",
            provider="anilist", provider_id="52991",
        ))
        self.assertEqual(links[0], ("AniList", "https://anilist.co/anime/52991"))
        self.assertIn("q=Frieren%3A+Beyond+Journey%27s+End", links[1][1])
        self.assertIn("filter[text]=Frieren%3A+Beyond+Journey%27s+End", links[2][1])

    def test_anilist_link_is_hidden_for_invalid_or_other_provider_ids(self):
        for entry in (
            AnimeEntry(title="Manual"),
            AnimeEntry(title="Other", provider="mal", provider_id="123"),
            AnimeEntry(title="Bad ID", provider="anilist", provider_id="abc"),
        ):
            with self.subTest(entry=entry):
                self.assertNotIn("AniList", [name for name, _url in links_for_entry(entry)])

    def test_custom_link_is_hidden_when_required_identifier_is_missing(self):
        links = links_for_entry(
            AnimeEntry(title="Manual anime"),
            [{"name": "Provider page", "url": "https://example.com/{provider_id}"}],
        )
        self.assertNotIn("Provider page", [name for name, _url in links])

    def test_custom_template_url_encodes_user_data(self):
        url = render_link_template(
            "https://example.com/anime/{provider_id}?q={title}",
            {"title": "A & B", "provider": "anilist", "provider_id": "42"},
        )
        self.assertEqual(url, "https://example.com/anime/42?q=A+%26+B")

    def test_rejects_unsafe_urls_and_template_fields(self):
        for label, template in (
            ("Bad", "javascript:alert(1)"),
            ("Credentials", "https://user:pass@example.com/{title}"),
            ("Bad field", "https://example.com/{title.__class__}"),
            ("Bad scheme", "file:///etc/passwd"),
        ):
            with self.subTest(template=template), self.assertRaises(ExternalLinkError):
                validate_link_template(label, template)

    def test_store_round_trip_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExternalLinkStore(Path(directory) / "links.json")
            store.save_templates([{"name": "Official", "url": "https://example.com/{provider_id}"}])
            self.assertEqual(
                store.list_templates(),
                ({"name": "Official", "url": "https://example.com/{provider_id}"},),
            )
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_store_rejects_duplicate_names_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExternalLinkStore(Path(directory) / "links.json")
            store.save_templates([{"name": "Official", "url": "https://example.com"}])
            original = store.path.read_text(encoding="utf-8")
            with self.assertRaisesRegex(ExternalLinkError, "unique"):
                store.save_templates([
                    {"name": "Official", "url": "https://example.com"},
                    {"name": "official", "url": "https://other.example.com"},
                ])
            self.assertEqual(store.path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
