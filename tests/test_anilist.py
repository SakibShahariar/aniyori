"""Offline tests for the AniList catalogue client."""

import io
import json
import unittest
from unittest.mock import patch

from aniyori.services.anilist import AniListClient, AniListError, _normalise_media


def response_for(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class AniListClientTests(unittest.TestCase):
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
            results = AniListClient().search_anime("Example")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Example Anime")
        self.assertEqual(results[0]["id"], 21)
        self.assertEqual(results[0]["cover_image"], "large.jpg")

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


if __name__ == "__main__":
    unittest.main()
