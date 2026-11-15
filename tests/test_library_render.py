"""Tests for library widget cache keys."""

import unittest
from types import SimpleNamespace

from aniyori.services.library_render import (
    library_filter_changes_preset, library_layout_signature,
    library_stack_page, library_view_for_preset, library_widget_signature,
)


class LibraryWidgetSignatureTests(unittest.TestCase):
    def test_selection_updates_preserve_the_complete_render_signature(self):
        entry = SimpleNamespace(title="Example", storage_id=7)
        airing = (1_800_000_000, 24)
        layouts = {"list": {"visible": ["title", "progress"]}}

        unselected = library_widget_signature(entry, airing, False, library_layout_signature(layouts), False)
        selected = library_widget_signature(entry, airing, True, library_layout_signature(layouts), False)

        self.assertEqual(len(selected), 5)
        self.assertEqual(selected, (entry, airing, True, repr(layouts), False))
        self.assertEqual(unselected[0:2], selected[0:2])
        self.assertNotEqual(unselected, selected)


    def test_reselecting_current_filter_does_not_detach_active_preset(self):
        self.assertFalse(library_filter_changes_preset("watching", "watching", False))
        self.assertTrue(library_filter_changes_preset("watching", "completed", False))
        self.assertFalse(library_filter_changes_preset("watching", "completed", True))

    def test_presets_capture_selected_view_while_empty_state_is_visible(self):
        # The stack displays the shared empty page, but the toggle retains Grid.
        self.assertEqual(library_view_for_preset(True), "grid")
        self.assertEqual(library_view_for_preset(False), "list")

    def test_empty_state_survives_list_and_grid_switches(self):
        for view in ("list", "grid"):
            with self.subTest(view=view):
                self.assertEqual(library_stack_page(view, False), "empty")
                self.assertEqual(library_stack_page(view, True), view)

    def test_layout_and_compact_changes_invalidate_cached_widgets(self):
        entry = SimpleNamespace(title="Example", storage_id=7)
        layouts = {"list": {"visible": ["title"]}}
        baseline = library_widget_signature(entry, None, False, library_layout_signature(layouts), False)
        changed_layout = library_widget_signature(
            entry, None, False, library_layout_signature({"list": {"visible": ["title", "status"]}}), False
        )
        compact = library_widget_signature(entry, None, False, library_layout_signature(layouts), True)

        self.assertNotEqual(baseline, changed_layout)
        self.assertNotEqual(baseline, compact)


if __name__ == "__main__":
    unittest.main()
