"""Offline tests for the AniList catalogue client."""

import io
import json
import tempfile
import unittest
from unittest.mock import patch

from urllib.error import HTTPError, URLError

from aniyori.services.anilist import (
    MAX_ANILIST_RESPONSE_BYTES, AniListClient, AniListError, _normalise_media,
)
from aniyori.services.metadata_cache import MetadataCache


def response_for(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class AniListClientTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.client = AniListClient(cache=MetadataCache(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_request_rejects_oversized_response(self):
        response = io.BytesIO(b" " * (MAX_ANILIST_RESPONSE_BYTES + 1))
        with patch("aniyori.services.anilist.urlopen", return_value=response):
            with self.assertRaisesRegex(AniListError, "exceeds the maximum allowed size"):
                self.client.search_anime("Naruto")

    def test_request_rejects_truncated_json_response(self):
        with patch(
            "aniyori.services.anilist.urlopen",
            return_value=io.BytesIO(b'{"data":'),
        ):
            with self.assertRaisesRegex(AniListError, "invalid JSON"):
                self.client.search_anime("Naruto")

    def test_request_reports_http_rate_limits_and_network_timeouts(self):
        rate_limited = HTTPError(
            "https://graphql.anilist.co", 429, "Too Many Requests", None, None
        )
        for error, message in (
            (rate_limited, "HTTP 429"),
            (TimeoutError("timed out"), "Could not reach AniList"),
            (URLError("offline"), "Could not reach AniList"),
        ):
            with self.subTest(error=error):
                with patch(
                    "aniyori.services.anilist.urlopen", side_effect=error
                ):
                    with self.assertRaisesRegex(AniListError, message):
                        self.client.search_anime("Naruto")

    def test_search_normalises_results(self):
        payload = {
            "data": {
                "Page": {
                    "media": [{
                        "id": 21,
                        "title": {"romaji": "Example", "english": "Example Anime", "native": None},
                        "episodes": 12,
                        "coverImage": {"medium": "medium.jpg", "large": "large.jpg"},
                        "genres": ["Adventure"],
                        "siteUrl": "https://anilist.co/anime/21",
                    }]
                }
            }
        }
        with patch("aniyori.services.anilist.urlopen", return_value=response_for(payload)):
            results = self.client.search_anime("Example")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Example Anime")
        self.assertEqual(results[0]["id"], 21)
        self.assertEqual(results[0]["cover_image"], "large.jpg")

    def test_search_rejects_malformed_page_and_media_shapes(self):
        for payload in (
            {"Page": None},
            {"Page": []},
            {"Page": {"media": {}}},
            {"Page": {"media": [None]}},
        ):
            with self.subTest(payload=payload):
                with patch.object(self.client, "_request", return_value=payload):
                    with self.assertRaises(AniListError):
                        self.client.search_anime("Example", refresh=True)

    def test_normalise_media_builds_supported_trailer_urls(self):
        youtube = _normalise_media({
            "title": {"romaji": "Example"},
            "trailer": {"id": "abcdefghijk", "site": "youtube", "thumbnail": "https://img.example/thumb.jpg"},
        })
        self.assertEqual(
            youtube["trailer_url"],
            "https://www.youtube.com/watch?v=abcdefghijk",
        )
        self.assertEqual(youtube["trailer_thumbnail"], "https://img.example/thumb.jpg")
        dailymotion = _normalise_media({
            "title": {"romaji": "Example"},
            "trailer": {"id": "x8abc123", "site": "dailymotion"},
        })
        self.assertEqual(dailymotion["trailer_url"], "https://www.dailymotion.com/video/x8abc123")
        for trailer in (
            {"id": "short", "site": "youtube"},
            {"id": "abcdefghijk", "site": "unknown"},
            {"id": "javascript:alert(1)", "site": "dailymotion"},
        ):
            with self.subTest(trailer=trailer):
                self.assertIsNone(_normalise_media({
                    "title": {"romaji": "Example"}, "trailer": trailer,
                })["trailer_url"])

    def test_normalise_media_handles_malformed_optional_nested_fields(self):
        result = _normalise_media({
            "id": 21, "title": "unexpected", "coverImage": [], "genres": "Adventure"
        })
        self.assertEqual(result["title"], "Untitled anime")
        self.assertIsNone(result["cover_image"])
        self.assertEqual(result["genres"], [])

    def test_blank_search_does_not_make_request(self):
        with patch("aniyori.services.anilist.urlopen") as open_url:
            self.assertEqual(AniListClient().search_anime("  "), [])
        open_url.assert_not_called()

    def test_search_uses_ten_results_by_default(self):
        with patch.object(AniListClient, "_request", return_value={"Page": {"media": []}}) as request:
            self.assertEqual(AniListClient().search_anime("Naruto"), [])
        self.assertEqual(request.call_args.args[1]["perPage"], 10)

    def test_search_accepts_maximum_page_size(self):
        with patch.object(AniListClient, "_request", return_value={"Page": {"media": []}}) as request:
            self.assertEqual(AniListClient().search_anime("Naruto", per_page=25), [])
        self.assertEqual(request.call_args.args[1]["perPage"], 25)

    def test_rejects_invalid_page_size(self):
        with self.assertRaises(ValueError):
            AniListClient().search_anime("Naruto", per_page=26)

    def test_graphql_errors_are_reported(self):
        payload = {"errors": [{"message": "Rate limited"}], "data": {}}
        with patch("aniyori.services.anilist.urlopen", return_value=response_for(payload)):
            with self.assertRaisesRegex(AniListError, "Rate limited"):
                AniListClient().search_anime("Naruto")

    def test_malformed_graphql_errors_raise_client_error(self):
        malformed_errors = (
            "unexpected",
            {"message": "not a list"},
            [None],
            ["Rate limited"],
            [{}],
            [{"message": 42}],
            [{"message": "   "}],
        )
        for errors in malformed_errors:
            with self.subTest(errors=errors):
                payload = {"errors": errors, "data": {}}
                with patch(
                    "aniyori.services.anilist.urlopen",
                    return_value=response_for(payload),
                ):
                    with self.assertRaisesRegex(AniListError, "malformed GraphQL errors"):
                        AniListClient().search_anime("Naruto")

    def test_non_object_json_responses_raise_client_error(self):
        for payload in ([], "unexpected", 42, None):
            with self.subTest(payload=payload):
                with patch(
                    "aniyori.services.anilist.urlopen",
                    return_value=response_for(payload),
                ):
                    with self.assertRaisesRegex(AniListError, "must be a JSON object"):
                        AniListClient().search_anime("Naruto")

    def test_missing_detail_is_reported(self):
        with patch("aniyori.services.anilist.urlopen", return_value=response_for({"data": {"Media": None}})):
            with self.assertRaisesRegex(AniListError, "was not found"):
                AniListClient().get_anime(123)

    def test_normaliser_includes_valid_next_airing_data(self):
        result = _normalise_media({
            "id": 21,
            "title": {"english": "Example"},
            "nextAiringEpisode": {
                "airingAt": 1_800_000_000,
                "timeUntilAiring": 3600,
                "episode": 13,
            },
        })
        self.assertEqual(result["next_episode"], 13)
        self.assertEqual(result["next_airing_at"], 1_800_000_000)
        self.assertEqual(result["time_until_airing"], 3600)

    def test_normaliser_uses_clean_fallback_for_missing_or_invalid_airing_data(self):
        for airing in (None, [], {}, {
            "airingAt": True, "timeUntilAiring": -1, "episode": "13"
        }):
            with self.subTest(airing=airing):
                result = _normalise_media({
                    "id": 21, "title": {"english": "Example"},
                    "nextAiringEpisode": airing,
                })
                self.assertIsNone(result["next_episode"])
                self.assertIsNone(result["next_airing_at"])
                self.assertIsNone(result["time_until_airing"])

    def test_normaliser_handles_sparse_data(self):
        result = _normalise_media({"id": 1, "title": {}, "coverImage": None})
        self.assertEqual(result["title"], "Untitled anime")
        self.assertEqual(result["genres"], [])
        self.assertEqual(result["description"], "")

    def test_rejects_boolean_media_id(self):
        with self.assertRaises(ValueError):
            AniListClient().get_anime(True)


    def test_search_uses_fresh_cached_metadata_without_network(self):
        expected = [{"id": 21, "title": "Cached", "genres": []}]
        self.client.cache.set("search", '{"per_page": 10, "search": "example"}', expected)

        with patch.object(self.client, "_request") as request:
            self.assertEqual(self.client.search_anime("Example"), expected)

        request.assert_not_called()

    def test_search_returns_stale_cache_when_network_is_unavailable(self):
        from aniyori.services.metadata_cache import MetadataCache

        stale_client = AniListClient(
            cache=MetadataCache(self.temp_dir.name, ttl=0)
        )
        expected = [{"id": 21, "title": "Offline result"}]
        stale_client.cache.set(
            "search", '{"per_page": 10, "search": "example"}', expected
        )

        with patch.object(
            stale_client, "_request", side_effect=AniListError("offline")
        ):
            self.assertEqual(stale_client.search_anime("Example"), expected)

    def test_refresh_bypasses_fresh_search_cache(self):
        cached = [{"id": 21, "title": "Old title"}]
        self.client.cache.set(
            "search", '{"per_page": 10, "search": "example"}', cached
        )
        payload = {
            "Page": {
                "media": [{
                    "id": 21,
                    "title": {"english": "New title"},
                    "coverImage": {},
                }]
            }
        }
        with patch.object(self.client, "_request", return_value=payload) as request:
            results = self.client.search_anime("Example", refresh=True)

        request.assert_called_once()
        self.assertEqual(results[0]["title"], "New title")

    def test_clear_cache_invalidates_cached_metadata(self):
        self.client.cache.set("details", "21", {"id": 21})
        self.client.clear_cache()
        self.assertIsNone(self.client.cache.get("details", "21"))

    def test_detail_uses_cache_and_refreshes_when_requested(self):
        cached = {"id": 21, "title": "Cached title"}
        self.client.cache.set("details", "21", cached)
        with patch.object(self.client, "_request") as request:
            self.assertEqual(self.client.get_anime(21), cached)
        request.assert_not_called()

        payload = {"Media": {"id": 21, "title": {"english": "Fresh title"}}}
        with patch.object(self.client, "_request", return_value=payload) as request:
            result = self.client.get_anime(21, refresh=True)
        request.assert_called_once()
        self.assertEqual(result["title"], "Fresh title")


    def test_search_season_normalises_results_and_uses_season_variables(self):
        payload = {"Page": {"media": [{
            "id": 101, "title": {"romaji": "Seasonal Example", "english": "Seasonal Example"},
            "episodes": 12, "format": "TV", "status": "RELEASING", "season": "FALL",
            "seasonYear": 2026, "popularity": 12345, "averageScore": 82,
            "startDate": {"year": 2026, "month": 10, "day": 1},
            "coverImage": {"large": "https://example.test/cover.jpg"},
            "genres": ["Adventure"], "siteUrl": "https://anilist.co/anime/101",
            "nextAiringEpisode": {"airingAt": 1790812800, "timeUntilAiring": 3600, "episode": 5},
            "trailer": {"id": "dQw4w9WgXcQ", "site": "youtube", "thumbnail": "https://example.test/trailer.jpg"},
        }]}}
        with patch.object(self.client, "_request", return_value=payload) as request:
            results = self.client.search_season("fall", 2026)
        self.assertEqual(request.call_args.args[1], {"season": "FALL", "seasonYear": 2026, "perPage": 50})
        self.assertEqual(results[0]["title"], "Seasonal Example")
        self.assertEqual(results[0]["season"], "FALL")
        self.assertEqual(results[0]["popularity"], 12345)
        self.assertEqual(results[0]["average_score"], 82)
        self.assertEqual(results[0]["genres"], ["Adventure"])
        self.assertEqual(results[0]["next_airing_at"], 1790812800)
        self.assertEqual(results[0]["trailer_url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(results[0]["trailer_thumbnail"], "https://example.test/trailer.jpg")

    def test_search_season_cache_and_offline_fallback(self):
        payload = {"Page": {"media": [{"id": 101, "title": {"romaji": "Cached"}}]}}
        with patch.object(self.client, "_request", return_value=payload) as request:
            first = self.client.search_season("WINTER", 2026)
            second = self.client.search_season("WINTER", 2026)
        self.assertEqual(first, second)
        self.assertEqual(request.call_count, 1)
        with patch.object(self.client, "_request", side_effect=AniListError("offline")):
            self.assertEqual(self.client.search_season("WINTER", 2026, refresh=True), first)

    def test_search_season_rejects_invalid_parameters_and_malformed_pages(self):
        for season, year, per_page in (("MONSOON", 2026, 50), ("WINTER", 1969, 50), ("WINTER", 2026, 51), ("WINTER", True, 50)):
            with self.subTest(season=season, year=year, per_page=per_page):
                with self.assertRaises(ValueError):
                    self.client.search_season(season, year, per_page)
        for payload in ({"Page": None}, {"Page": {"media": {}}}, {"Page": {"media": [None]}}):
            with self.subTest(payload=payload):
                with patch.object(self.client, "_request", return_value=payload):
                    with self.assertRaises(AniListError):
                        self.client.search_season("WINTER", 2026, refresh=True)


if __name__ == "__main__":
    unittest.main()

