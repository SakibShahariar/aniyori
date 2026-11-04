"""Tests for per-view library layout validation and persistence."""

import tempfile
import unittest
from pathlib import Path

from aniyori.services.library_layout import (
    COLUMNS, DEFAULT_LAYOUTS, LibraryLayoutError, LibraryLayoutStore,
)


class LibraryLayoutStoreTests(unittest.TestCase):
    def test_default_layouts_are_available_without_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            layouts = LibraryLayoutStore(Path(directory) / "layout.json").load_all()
            self.assertEqual(layouts, DEFAULT_LAYOUTS)

    def test_list_and_grid_layouts_persist_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layout.json"
            store = LibraryLayoutStore(path)
            layouts = store.load_all()
            layouts["list"]["order"] = ["status", "title", "progress", "source", "airing"]
            layouts["list"]["visible"].remove("airing")
            layouts["list"]["widths"]["title"] = 420
            layouts["grid"]["widths"]["card_width"] = 280
            store.save("list", layouts["list"])
            store.save("grid", layouts["grid"])
            loaded = store.load_all()
            self.assertEqual(loaded["list"]["order"][0], "status")
            self.assertNotIn("airing", loaded["list"]["visible"])
            self.assertEqual(loaded["list"]["widths"]["title"], 420)
            self.assertEqual(loaded["grid"]["widths"]["card_width"], 280)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_reset_restores_view_defaults_without_changing_other_view(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryLayoutStore(Path(directory) / "layout.json")
            grid = store.load_all()["grid"]
            grid["widths"]["card_width"] = 300
            store.save("grid", grid)
            list_layout = store.load_all()["list"]
            list_layout["visible"].remove("source")
            store.save("list", list_layout)
            store.reset("list")
            loaded = store.load_all()
            self.assertEqual(loaded["list"], DEFAULT_LAYOUTS["list"])
            self.assertEqual(loaded["grid"]["widths"]["card_width"], 300)

    def test_rejects_hidden_title_duplicate_columns_and_invalid_widths(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryLayoutStore(Path(directory) / "layout.json")
            layout = store.load_all()["list"]
            invalid = dict(layout, visible=["status"])
            with self.assertRaises(LibraryLayoutError):
                store.save("list", invalid)
            invalid = dict(layout, order=["title", "title", "progress", "source", "airing"])
            with self.assertRaises(LibraryLayoutError):
                store.save("list", invalid)
            invalid = dict(layout, widths={**layout["widths"], "title": 50})
            with self.assertRaises(LibraryLayoutError):
                store.save("list", invalid)

    def test_rejects_unknown_view_and_corrupt_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layout.json"
            store = LibraryLayoutStore(path)
            with self.assertRaises(LibraryLayoutError):
                store.save("compact", {})
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(LibraryLayoutError, "unreadable"):
                store.load_all()


if __name__ == "__main__":
    unittest.main()
