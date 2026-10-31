"""Tests for RSS parsing, feed persistence, and independent refresh results."""

import unittest
from datetime import timezone

from aniyori.services.rss import FeedParseError, RSSFeed, RSSFeedStore, parse_release_feed
from aniyori.services.release_monitor import (
    FeedFetchError, fetch_feed_content, refresh_release_feeds,
)


CATALOGUE = [
    {"id": 10, "title": "Sousou no Frieren",
     "title_english": "Frieren: Beyond Journey's End"},
    {"id": 20, "title": "Spy x Family", "title_english": "SPY×FAMILY"},
]


class ReleaseFeedParserTests(unittest.TestCase):
    def test_parses_rss_items_and_normalizes_dates_categories_and_links(self):
        feed = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Anime Releases</title>
          <item><title>Example - 01 [1080p]</title>
            <link>https://example.org/releases/1</link>
            <guid>release-1</guid>
            <pubDate>Sat, 31 Oct 2026 05:00:00 +0000</pubDate>
            <description><![CDATA[<p>Episode one</p>]]></description>
            <category>1080p</category><category>English</category>
          </item>
        </channel></rss>"""
        entries = parse_release_feed(feed)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.title, "Example - 01 [1080p]")
        self.assertEqual(entry.link, "https://example.org/releases/1")
        self.assertEqual(entry.identifier, "release-1")
        self.assertEqual(entry.published_at.tzinfo, timezone.utc)
        self.assertEqual(entry.categories, ("1080p", "English"))
        self.assertIn("<p>Episode one</p>", entry.summary)

    def test_parses_atom_namespaces_and_prefers_alternate_link(self):
        feed = """<feed xmlns="http://www.w3.org/2005/Atom">
          <title>Releases</title><entry><title>Example Episode 2</title>
            <id>tag:example.org,2026:2</id>
            <link rel="self" href="https://example.org/api/2"/>
            <link rel="alternate" href="https://example.org/releases/2"/>
            <updated>2026-10-31T05:30:00Z</updated>
            <category term="1080p"/><summary>Episode two</summary>
          </entry></feed>"""
        entry = parse_release_feed(feed)[0]
        self.assertEqual(entry.link, "https://example.org/releases/2")
        self.assertEqual(entry.identifier, "tag:example.org,2026:2")
        self.assertEqual(entry.categories, ("1080p",))
        self.assertEqual(entry.published_at.tzinfo, timezone.utc)

    def test_ignores_unsafe_or_malformed_entry_links(self):
        feed = """<rss><channel><item><title>One</title>
          <link>javascript:alert(1)</link><guid>one</guid></item>
          <item><title>Two</title><link>https://user:pass@example.org/x</link></item>
          <item><title>Three</title><link>https://example.org:bad/x</link></item>
        </channel></rss>"""
        self.assertTrue(all(item.link is None for item in parse_release_feed(feed)))

    def test_skips_entries_without_titles_and_respects_entry_limit(self):
        feed = """<rss><channel><item><description>missing title</description></item>
          <item><title>One</title></item><item><title>Two</title></item>
        </channel></rss>"""
        self.assertEqual([item.title for item in parse_release_feed(feed, max_entries=1)], ["One"])
        self.assertEqual(len(parse_release_feed(feed, max_entries=0)), 0)

    def test_rejects_oversized_dtd_and_malformed_feeds(self):
        with self.assertRaisesRegex(FeedParseError, "maximum allowed size"):
            parse_release_feed("<rss/>", max_bytes=3)
        with self.assertRaisesRegex(FeedParseError, "DTD and entity"):
            parse_release_feed("<!DOCTYPE rss [<!ENTITY x 'boom'>]><rss/>")
        with self.assertRaisesRegex(FeedParseError, "invalid XML"):
            parse_release_feed("<rss><channel>")
        with self.assertRaisesRegex(FeedParseError, "Unsupported feed"):
            parse_release_feed("<html/>")

    def test_feed_store_adds_removes_and_round_trips_sources(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            store = RSSFeedStore(Path(directory) / "feeds.json")
            self.assertEqual(store.load(), ())
            added = store.add("https://example.org/feed.xml", "Example Releases")
            self.assertEqual(added, (RSSFeed("Example Releases", "https://example.org/feed.xml"),))
            self.assertEqual(store.load(), added)
            self.assertEqual(store.remove("https://example.org/feed.xml"), ())
            self.assertEqual(store.load(), ())

    def test_feed_store_rejects_duplicate_and_unsafe_urls(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            store = RSSFeedStore(Path(directory) / "feeds.json")
            store.add("https://example.org/feed.xml")
            with self.assertRaisesRegex(FeedParseError, "already configured"):
                store.add("https://EXAMPLE.org/feed.xml")
            for url in ("file:///tmp/feed.xml", "https://user:pass@example.org/feed.xml"):
                with self.subTest(url=url), self.assertRaises(FeedParseError):
                    store.add(url)

    def test_feed_store_rejects_duplicate_sources_and_invalid_enabled_values(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            store = RSSFeedStore(Path(directory) / "feeds.json")
            with self.assertRaisesRegex(FeedParseError, "unique"):
                store.save([
                    RSSFeed("First", "https://example.org/feed.xml"),
                    RSSFeed("Second", "https://EXAMPLE.org/feed.xml"),
                ])
            with self.assertRaisesRegex(FeedParseError, "boolean"):
                store.save([RSSFeed("Broken", "https://example.org/feed.xml", 1)])

    def test_refresh_matches_releases_scores_quality_and_keeps_feed_failures_isolated(self):
        feeds = (
            RSSFeed("Working", "https://example.org/good.xml"),
            RSSFeed("Broken", "https://example.org/bad.xml"),
            RSSFeed("Disabled", "https://example.org/disabled.xml", False),
        )
        payload = b"""<rss><channel>
          <item><title>[SubsPlease] Frieren Beyond Journeys End - 01 (1080p) [WEB-DL]</title>
            <link>https://example.org/releases/1</link><guid>release-1</guid></item>
          <item><title>Unparseable announcement</title></item>
        </channel></rss>"""

        def fetcher(url):
            if url.endswith("bad.xml"):
                raise OSError("temporary network failure")
            return payload

        results = refresh_release_feeds(
            feeds,
            CATALOGUE,
            fetcher=fetcher,
            preferences={"resolution": {"preferred": ["1080p"]}},
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].error, None)
        matched = results[0].releases[0]
        self.assertEqual(matched.match_status, "matched")
        self.assertEqual(matched.media_id, 10)
        self.assertEqual(matched.episode, 1)
        self.assertAlmostEqual(matched.score.score, 85.45)
        self.assertTrue(matched.score.accepted)
        self.assertEqual(results[0].releases[1].match_status, "unparsed")
        self.assertIn("temporary network failure", results[1].error)

    def test_refresh_extracts_all_supported_quality_metadata_when_present(self):
        feed = RSSFeed("Metadata", "https://example.org/feed.xml")
        payload = b"""<rss><channel><item>
          <title>[GoodGroup] Frieren - 01 (1080p) [WEB-DL] [FLAC] [ENG SUB] [1.4 GB]</title>
          <description>Seeders: 75</description>
        </item></channel></rss>"""
        result = refresh_release_feeds(
            [feed], CATALOGUE, fetcher=lambda _url: payload,
        )[0].releases[0]
        self.assertEqual(result.metadata["resolution"], "1080p")
        self.assertEqual(result.metadata["source"], "WEB-DL")
        self.assertEqual(result.metadata["release_group"], "GoodGroup")
        self.assertEqual(result.metadata["audio"], "FLAC")
        self.assertEqual(result.metadata["subtitles"], "English")
        self.assertEqual(result.metadata["file_size_mb"], 1400.0)
        self.assertEqual(result.metadata["seeders"], 75)
        self.assertEqual({factor.name for factor in result.score.factors}, {
            "resolution", "source", "audio", "subtitles",
            "release_group", "file_size", "seeders",
        })

    def test_refresh_rejected_preferences_are_visible_in_score_decision(self):
        feed = RSSFeed("Quality", "https://example.org/feed.xml")
        payload = b"""<rss><channel><item>
          <title>[BadGroup] Frieren - 01 (480p) [HDTV]</title>
        </item></channel></rss>"""
        results = refresh_release_feeds(
            [feed], CATALOGUE,
            fetcher=lambda _url: payload,
            preferences={"source": {"rejected": ["HDTV"]}},
        )
        release = results[0].releases[0]
        self.assertFalse(release.score.accepted)
        self.assertIn("Rejected: source is HDTV", release.score.explanation)

    def test_fetcher_rejects_unsafe_urls_before_network_access(self):
        with self.assertRaisesRegex(FeedFetchError, "HTTP"):
            fetch_feed_content("file:///etc/passwd")



    def test_feed_store_updates_name_url_and_enabled_state(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            store = RSSFeedStore(Path(directory) / "feeds.json")
            store.add("https://example.org/old.xml", "Old name")
            updated = store.update(
                "https://example.org/old.xml",
                name="New name",
                new_url="https://example.org/new.xml",
                enabled=False,
            )
            self.assertEqual(
                updated,
                (RSSFeed("New name", "https://example.org/new.xml", False),),
            )
            self.assertEqual(store.load(), updated)

    def test_feed_store_update_rejects_missing_or_duplicate_urls(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            store = RSSFeedStore(Path(directory) / "feeds.json")
            store.add("https://example.org/one.xml")
            store.add("https://example.org/two.xml")
            with self.assertRaisesRegex(FeedParseError, "already configured"):
                store.update("https://example.org/one.xml", new_url="https://example.org/two.xml")
            with self.assertRaisesRegex(FeedParseError, "not found"):
                store.update("https://example.org/missing.xml", name="Missing")



    def test_feed_store_rejects_duplicate_json_keys_without_rewriting_file(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feeds.json"
            content = (
                '{"format":"aniyori-rss-feeds","version":1,'
                '"version":1,"feeds":[]}'
            )
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(FeedParseError, "duplicate key"):
                RSSFeedStore(path).load()
            self.assertEqual(path.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
