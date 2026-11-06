"""Tests for named library-view preset validation and persistence."""

import json
import tempfile
import unittest
from pathlib import Path

from aniyori.services.library_layout import DEFAULT_LAYOUTS, LibraryLayoutStore
from aniyori.services.library_view_presets import (
    PRESET_FORMAT,
    PRESET_VERSION,
    LibraryViewPresetError,
    LibraryViewPresetStore,
)


def sample_settings():
    return {
        "filter": "watching",
        "sort": "recently_updated",
        "view": "grid",
        "layouts": {
            view: {
                "order": list(layout["order"]),
                "visible": list(layout["visible"]),
                "widths": dict(layout["widths"]),
            }
            for view, layout in DEFAULT_LAYOUTS.items()
        },
    }


class LibraryViewPresetStoreTests(unittest.TestCase):
    def test_missing_file_returns_empty_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryViewPresetStore(Path(directory) / "presets.json")
            self.assertEqual(store.load(), {"presets": [], "default": None})

    def test_save_and_load_persists_supported_view_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presets.json"
            store = LibraryViewPresetStore(path)
            store.save_preset("Currently Watching", sample_settings())

            loaded = store.load()
            self.assertEqual(store.list_presets(), ("Currently Watching",))
            self.assertEqual(
                store.get_preset("currently watching"), sample_settings()
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(loaded["default"], None)

    def test_list_and_grid_presets_keep_both_layouts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryViewPresetStore(Path(directory) / "presets.json")
            grid = sample_settings()
            grid["view"] = "grid"
            listing = sample_settings()
            listing["view"] = "list"
            listing["layouts"]["list"]["widths"]["title"] = 420

            store.save_preset("Grid", grid)
            store.save_preset("List", listing)

            self.assertEqual(store.get_preset("Grid")["view"], "grid")
            self.assertEqual(store.get_preset("List")["view"], "list")
            self.assertEqual(
                store.get_preset("Grid")["layouts"]["list"],
                grid["layouts"]["list"],
            )
            self.assertEqual(
                store.get_preset("List")["layouts"]["grid"],
                listing["layouts"]["grid"],
            )

    def test_resetting_layout_does_not_delete_presets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout_store = LibraryLayoutStore(root / "layout.json")
            preset_store = LibraryViewPresetStore(root / "presets.json")
            preset_store.save_preset("Watching", sample_settings())
            layout = layout_store.load_all()["list"]
            layout["widths"]["title"] = 420
            layout_store.save("list", layout)

            layout_store.reset("list")

            self.assertEqual(preset_store.list_presets(), ("Watching",))
            self.assertEqual(
                preset_store.get_preset("Watching"), sample_settings()
            )
            self.assertEqual(
                layout_store.load_all()["list"]["widths"]["title"],
                DEFAULT_LAYOUTS["list"]["widths"]["title"],
            )

    def test_duplicate_names_are_case_insensitive(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryViewPresetStore(Path(directory) / "presets.json")
            store.save_preset("Favorites", sample_settings())

            with self.assertRaisesRegex(LibraryViewPresetError, "already exists"):
                store.save_preset(" favorites ", sample_settings())

    def test_update_replaces_settings_without_changing_the_preset_name(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryViewPresetStore(Path(directory) / "presets.json")
            store.save_preset("Watching", sample_settings())
            updated = {
                **sample_settings(),
                "filter": "completed",
                "sort": "progress",
                "view": "list",
            }

            self.assertEqual(store.update_preset("Watching", updated), "Watching")
            self.assertEqual(store.get_preset("Watching"), updated)

    def test_rename_updates_default_and_duplicate_copies_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryViewPresetStore(Path(directory) / "presets.json")
            store.save_preset("Watching", sample_settings())
            store.set_default("Watching")
            store.rename_preset("Watching", "In Progress")
            store.duplicate_preset("In Progress", "In Progress Copy")

            state = store.load()
            self.assertEqual(state["default"], "In Progress")
            self.assertEqual(
                store.get_preset("In Progress Copy"), sample_settings()
            )
            self.assertEqual(
                store.list_presets(), ("In Progress", "In Progress Copy")
            )

    def test_delete_default_clears_default_without_touching_other_presets(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryViewPresetStore(Path(directory) / "presets.json")
            store.save_preset("Watching", sample_settings())
            store.save_preset("Everything", {
                **sample_settings(), "filter": "all", "sort": "title"
            })
            store.set_default("Watching")

            self.assertTrue(store.delete_preset("Watching"))
            self.assertFalse(store.delete_preset("Watching"))
            self.assertEqual(store.load()["default"], None)
            self.assertEqual(store.list_presets(), ("Everything",))

    def test_rejects_invalid_names_and_unsupported_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryViewPresetStore(Path(directory) / "presets.json")
            for name in ("", "   ", "x" * 49, "bad/name", "emoji 🚀"):
                with self.subTest(name=name), self.assertRaises(LibraryViewPresetError):
                    store.save_preset(name, sample_settings())

            invalid = sample_settings()
            invalid["filter"] = "genre"
            with self.assertRaises(LibraryViewPresetError):
                store.save_preset("Invalid Filter", invalid)
            invalid = sample_settings()
            invalid["sort"] = "random"
            with self.assertRaises(LibraryViewPresetError):
                store.save_preset("Invalid Sort", invalid)
            invalid = sample_settings()
            invalid["view"] = "kanban"
            with self.assertRaises(LibraryViewPresetError):
                store.save_preset("Invalid View", invalid)
            invalid = sample_settings()
            invalid["layouts"]["list"]["visible"] = ["status"]
            with self.assertRaises(LibraryViewPresetError):
                store.save_preset("Invalid Layout", invalid)

    def test_unknown_default_is_rejected_and_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryViewPresetStore(Path(directory) / "presets.json")
            with self.assertRaises(LibraryViewPresetError):
                store.set_default("Missing")
            store.save_preset("Watching", sample_settings())
            self.assertEqual(store.set_default("Watching"), "Watching")
            self.assertIsNone(store.set_default(None))

    def test_legacy_unknown_options_degrade_to_supported_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presets.json"
            path.write_text(json.dumps({
                "format": PRESET_FORMAT,
                "version": PRESET_VERSION,
                "default": "Legacy",
                "presets": [{
                    "name": "Legacy",
                    "settings": {
                        "filter": ["unsupported"],
                        "sort": "future_sort",
                        "view": "kanban",
                        "layouts": {"list": {"order": [[]]}},
                    },
                }],
            }), encoding="utf-8")

            state = LibraryViewPresetStore(path).load()

            self.assertEqual(state["default"], "Legacy")
            self.assertEqual(
                state["presets"][0]["settings"],
                {
                    "filter": "all",
                    "sort": "title",
                    "view": "list",
                    "layouts": DEFAULT_LAYOUTS,
                },
            )

    def test_duplicate_or_invalid_disk_entries_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presets.json"
            valid = {"name": "Watching", "settings": sample_settings()}
            path.write_text(json.dumps({
                "format": PRESET_FORMAT,
                "version": PRESET_VERSION,
                "default": "WATCHING",
                "presets": [
                    valid,
                    {"name": "watching", "settings": sample_settings()},
                    {"name": "bad/name", "settings": sample_settings()},
                ],
            }), encoding="utf-8")

            state = LibraryViewPresetStore(path).load()

            self.assertEqual(len(state["presets"]), 1)
            self.assertEqual(state["default"], "Watching")

    def test_oversized_preset_file_is_rejected_without_truncating_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presets.json"
            entry = {"name": "Preset", "settings": sample_settings()}
            payload = {
                "format": PRESET_FORMAT,
                "version": PRESET_VERSION,
                "default": None,
                "presets": [entry for _ in range(101)],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(LibraryViewPresetError, "limit"):
                LibraryViewPresetStore(path).load()
            self.assertEqual(len(json.loads(path.read_text())["presets"]), 101)

    def test_corrupt_or_unsupported_store_is_reported_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presets.json"
            path.write_text("{", encoding="utf-8")
            store = LibraryViewPresetStore(path)

            with self.assertRaisesRegex(LibraryViewPresetError, "unreadable"):
                store.load()
            self.assertEqual(path.read_text(encoding="utf-8"), "{")

            path.write_text(json.dumps({"format": "wrong", "version": 1}), encoding="utf-8")
            with self.assertRaisesRegex(LibraryViewPresetError, "unsupported"):
                store.load()


if __name__ == "__main__":
    unittest.main()
