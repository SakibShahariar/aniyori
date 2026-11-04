"""Integration tests for per-anime release preference decisions."""

import unittest

from aniyori.services.release_monitor import refresh_release_feeds
from aniyori.services.rss import RSSFeed


FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title><item>
<title>[Group] Frieren - 01 [1080p] [WEB-DL] [1GB]</title>
<link>https://example.com/release</link><guid>release-1</guid>
<description>English subtitles</description>
</item></channel></rss>"""


def refresh(feed_content=FEED, **kwargs):
    return refresh_release_feeds(
        [RSSFeed("Test feed", "https://example.com/feed")],
        [{"id": 1, "title": "Frieren"}],
        fetcher=lambda _url: feed_content,
        **kwargs,
    )[0].releases[0]


class AnimeReleasePreferenceIntegrationTests(unittest.TestCase):
    def test_per_anime_attribute_override_takes_precedence_over_global(self):
        release = refresh(
            preferences={"resolution": {"preferred": ["1080p"], "rejected": []}},
            anime_preferences={
                "1": {"preferences": {"resolution": {"preferred": [], "rejected": ["1080p"]}}}
            },
        )
        self.assertFalse(release.eligible)
        self.assertFalse(release.score.accepted)
        self.assertIn("Preference matched (rejected)", release.decision_explanation)

    def test_missing_anime_override_inherits_global_preferences(self):
        release = refresh(
            preferences={"resolution": {"preferred": [], "rejected": ["1080p"]}}
        )
        self.assertFalse(release.eligible)
        self.assertFalse(release.score.accepted)

    def test_per_anime_download_toggle_disables_release(self):
        release = refresh(anime_preferences={"1": {"enabled": False}})
        self.assertFalse(release.eligible)
        self.assertIn("Downloads are disabled", release.decision_explanation)

    def test_per_anime_file_size_limits_reject_out_of_range_and_unknown_size(self):
        too_large = refresh(anime_preferences={"1": {"max_file_size_mb": 500}})
        self.assertFalse(too_large.eligible)
        self.assertIn("exceeds the per-anime maximum", too_large.decision_explanation)

        unknown_size = refresh(
            feed_content=FEED.replace(b" [1GB]", b""),
            anime_preferences={"1": {"min_file_size_mb": 100}},
        )
        self.assertFalse(unknown_size.eligible)
        self.assertIn("size is unknown", unknown_size.decision_explanation)


if __name__ == "__main__":
    unittest.main()
