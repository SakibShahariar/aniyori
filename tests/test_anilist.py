"""Offline tests for the AniList catalogue client."""

import io
import json
import tempfile
import unittest
from unittest.mock import patch

from aniyori.services.anilist import AniListClient, AniListError, _normalise_media
from aniyori.services.metadata_cache import MetadataCache


def response_for(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class AniListClientTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.client = AniListClient(cache=MetadataCache(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

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


if __name__ == "__main__":
    unittest.main()
