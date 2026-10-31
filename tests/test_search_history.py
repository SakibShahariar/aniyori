"""Tests for persistent recent search history and saved queries."""

import json
import tempfile
import unittest
from pathlib import Path

from aniyori.services.search_history import (
    MAX_HISTORY_ITEMS, SearchHistoryError, SearchHistoryStore,
)


class SearchHistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "config" / "search-history.json"
        self.store = SearchHistoryStore(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_file_starts_with_empty_history_and_saved_searches(self):
        self.assertEqual(self.store.list_history("anilist"), ())
        self.assertEqual(self.store.list_saved_searches("torrent"), ())

    def test_recent_queries_are_deduplicated_most_recent_first_and_bounded(self):
        self.store.record_query("anilist", "Naruto")
        self.store.record_query("anilist", "One Piece")
        self.store.record_query("anilist", " naruto ")
        self.assertEqual(self.store.list_history("anilist"), ("naruto", "One Piece"))
        for index in range(MAX_HISTORY_ITEMS + 5):
            self.store.record_query("anilist", f"query {index}")
        history = self.store.list_history("anilist")
        self.assertEqual(len(history), MAX_HISTORY_ITEMS)
        self.assertEqual(history[0], f"query {MAX_HISTORY_ITEMS + 4}")

    def test_blank_query_is_not_recorded(self):
        self.assertFalse(self.store.record_query("anilist", "   "))
        self.assertEqual(self.store.list_history("anilist"), ())

    def test_saved_searches_can_be_reused_and_removed(self):
        self.assertTrue(self.store.save_search("anilist", "Seasonal", "2026 fall anime"))
        self.assertFalse(self.store.save_search("anilist", "seasonal", "different query"))
        saved = self.store.list_saved_searches("anilist")
        self.assertEqual(saved, ({"name": "Seasonal", "query": "2026 fall anime"},))
        self.assertTrue(self.store.remove_saved_search("anilist", "SEASONAL"))
        self.assertEqual(self.store.list_saved_searches("anilist"), ())

    def test_individual_and_all_history_entries_can_be_removed(self):
        self.store.record_query("torrent", "Frieren")
        self.store.record_query("torrent", "Dandadan")
        self.assertTrue(self.store.remove_history("torrent", "frieren"))
        self.assertEqual(self.store.list_history("torrent"), ("Dandadan",))
        self.assertEqual(self.store.clear_history("torrent"), 1)
        self.assertEqual(self.store.list_history("torrent"), ())

    def test_domains_are_isolated(self):
        self.store.record_query("anilist", "Frieren")
        self.store.record_query("torrent", "Frieren")
        self.assertEqual(self.store.list_history("anilist"), ("Frieren",))
        self.assertEqual(self.store.list_history("torrent"), ("Frieren",))

    def test_invalid_domain_and_saved_search_values_are_rejected(self):
        with self.assertRaises(SearchHistoryError):
            self.store.list_history("unknown")
        with self.assertRaises(SearchHistoryError):
            self.store.save_search("anilist", "", "query")
        with self.assertRaises(SearchHistoryError):
            self.store.save_search("anilist", "name", "")

    def test_malformed_existing_file_is_not_silently_reset(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(SearchHistoryError, "invalid JSON"):
            self.store.record_query("anilist", "Naruto")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")

    def test_boolean_or_wrong_version_is_rejected(self):
        self.path.parent.mkdir(parents=True)
        payload = {
            "format": "aniyori-search-history",
            "version": True,
            "history": {"anilist": [], "torrent": []},
            "saved": {"anilist": [], "torrent": []},
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(SearchHistoryError, "unsupported format"):
            self.store.list_history("anilist")

    def test_duplicate_json_keys_are_rejected_without_overwriting(self):
        self.path.parent.mkdir(parents=True)
        content = (
            '{"format":"aniyori-search-history","version":1,'
            '"history":{"anilist":[],"anilist":["injected"],"torrent":[]},'
            '"saved":{"anilist":[],"torrent":[]}}'
        )
        self.path.write_text(content, encoding="utf-8")
        with self.assertRaisesRegex(SearchHistoryError, "Duplicate saved-search key"):
            self.store.record_query("anilist", "Naruto")
        self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_saved_history_round_trips_across_instances(self):
        self.store.record_query("anilist", "Naruto")
        self.store.save_search("anilist", "My Query", "Naruto Shippuden")
        reopened = SearchHistoryStore(self.path)
        self.assertEqual(reopened.list_history("anilist"), ("Naruto",))
        self.assertEqual(reopened.list_saved_searches("anilist")[0]["query"], "Naruto Shippuden")


if __name__ == "__main__":
    unittest.main()
