import unittest
from datetime import date

from aniyori.services.seasons import filter_season_results, season_for_date


class SeasonHelpersTests(unittest.TestCase):
    def test_season_for_date_covers_all_four_seasons(self):
        self.assertEqual(season_for_date(date(2026, 1, 1)), ("WINTER", 2026))
        self.assertEqual(season_for_date(date(2026, 4, 1)), ("SPRING", 2026))
        self.assertEqual(season_for_date(date(2026, 7, 1)), ("SUMMER", 2026))
        self.assertEqual(season_for_date(date(2026, 10, 1)), ("FALL", 2026))
        self.assertEqual(season_for_date(date(2026, 12, 31)), ("FALL", 2026))

    def test_filters_by_title_genre_format_and_status(self):
        results = [
            {"title": "Alpha", "genres": ["Action"], "format": "TV", "status": "RELEASING"},
            {"title": "Beta", "genres": ["Comedy"], "format": "MOVIE", "status": "FINISHED"},
        ]
        self.assertEqual(len(filter_season_results(results, query="alp")), 1)
        self.assertEqual(len(filter_season_results(results, genre="Comedy")), 1)
        self.assertEqual(len(filter_season_results(results, format_name="TV")), 1)
        self.assertEqual(len(filter_season_results(results, status="FINISHED")), 1)

    def test_sort_modes_and_input_immutability(self):
        results = [
            {"title": "Zulu", "popularity": 10, "average_score": 70, "start_date": {"year": 2026}},
            {"title": "Alpha", "popularity": 20, "average_score": 90, "start_date": {"year": 2025}},
        ]
        original = list(results)
        self.assertEqual(filter_season_results(results)[0]["title"], "Alpha")
        self.assertEqual(filter_season_results(results, sort_by="score")[0]["title"], "Alpha")
        self.assertEqual(filter_season_results(results, sort_by="title")[0]["title"], "Alpha")
        self.assertEqual(filter_season_results(results, sort_by="start_date")[0]["title"], "Zulu")
        self.assertEqual(results, original)

    def test_rejects_unknown_sort_mode(self):
        with self.assertRaises(ValueError):
            filter_season_results([], sort_by="random")


if __name__ == "__main__":
    unittest.main()
