"""Tests for validated JSON and CSV library import/export."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from aniyori.library_io import export_csv, export_json, import_csv, import_json
from aniyori.models import AnimeEntry, WatchStatus
from aniyori.storage import LibraryStorage


class LibraryIOTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            AnimeEntry(
                title="Fullmetal Alchemist: Brotherhood",
                episodes_total=64,
                episodes_watched=32,
                status=WatchStatus.WATCHING,
                provider="anilist",
                provider_id="5114",
                cover_image="https://s4.anilist.co/file/cover.jpg",
            ),
            AnimeEntry(title="Planetes", status=WatchStatus.PLANNING),
        ]

    def test_json_round_trip_preserves_library_fields(self):
        imported = import_json(export_json(self.entries))

        self.assertEqual(imported, self.entries)
        self.assertIsNone(imported[0].storage_id)

    def test_json_rejects_invalid_format_and_version(self):
        with self.assertRaisesRegex(ValueError, "not an Aniyori"):
            import_json('{"format":"other","version":1,"entries":[]}')
        with self.assertRaisesRegex(ValueError, "unsupported"):
            import_json('{"format":"aniyori-library","version":2,"entries":[]}')
        with self.assertRaisesRegex(ValueError, "unsupported"):
            import_json('{"format":"aniyori-library","version":true,"entries":[]}')

    def test_json_rejects_invalid_entries_without_partial_results(self):
        payload = export_json(self.entries).replace('"episodes_watched": 32', '"episodes_watched": -1')
        with self.assertRaisesRegex(ValueError, "Watched episode count cannot be negative"):
            import_json(payload)

    def test_json_rejects_invalid_status_and_episode_types(self):
        with self.assertRaisesRegex(ValueError, "Unknown watch status"):
            import_json(
                '{"format":"aniyori-library","version":1,"entries":'
                '[{"title":"Example","status":"unknown"}]}'
            )
        with self.assertRaisesRegex(ValueError, "whole number"):
            import_json(
                '{"format":"aniyori-library","version":1,"entries":'
                '[{"title":"Example","episodes_watched":true}]}'
            )

    def test_failed_database_import_keeps_existing_library_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = LibraryStorage(Path(directory) / "library.sqlite3")
            original = AnimeEntry(title="Existing library entry")
            storage.add(original)
            duplicate_provider_entries = [
                AnimeEntry(title="First", provider="anilist", provider_id="21"),
                AnimeEntry(title="Duplicate", provider="anilist", provider_id="21"),
            ]

            with self.assertRaises(sqlite3.IntegrityError):
                storage.replace_all(import_json(export_json(duplicate_provider_entries)))

            self.assertEqual(
                [entry.title for entry in storage.list_entries()],
                ["Existing library entry"],
            )

    def test_csv_round_trip_preserves_library_fields(self):
        imported = import_csv(export_csv(self.entries))

        self.assertEqual(imported, self.entries)

    def test_csv_rejects_missing_columns(self):
        with self.assertRaisesRegex(ValueError, "missing required"):
            import_csv("title,status\nExample,watching\n")

    def test_csv_rejects_invalid_rows_with_row_number(self):
        content = export_csv(self.entries).replace(",32,watching,", ",not-a-number,watching,")
        with self.assertRaisesRegex(ValueError, "row 2"):
            import_csv(content)


if __name__ == "__main__":
    unittest.main()
