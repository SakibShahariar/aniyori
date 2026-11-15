"""Tests for library widget cache keys."""

import unittest
from types import SimpleNamespace

from aniyori.services.library_render import library_widget_signature


class LibraryWidgetSignatureTests(unittest.TestCase):
    def test_selection_updates_preserve_the_complete_render_signature(self):
        entry = SimpleNamespace(title="Example", storage_id=7)
        airing = (1_800_000_000, 24)
        layouts = {"list": {"visible": ["title", "progress"]}}

        unselected = library_widget_signature(entry, airing, False, layouts, False)
        selected = library_widget_signature(entry, airing, True, layouts, False)

        self.assertEqual(len(selected), 5)
        self.assertEqual(selected, (entry, airing, True, repr(layouts), False))
        self.assertEqual(unselected[0:2], selected[0:2])
        self.assertNotEqual(unselected, selected)

    def test_layout_and_compact_changes_invalidate_cached_widgets(self):
        entry = SimpleNamespace(title="Example", storage_id=7)
        layouts = {"list": {"visible": ["title"]}}
        baseline = library_widget_signature(entry, None, False, layouts, False)
        changed_layout = library_widget_signature(
            entry, None, False, {"list": {"visible": ["title", "status"]}}, False
        )
        compact = library_widget_signature(entry, None, False, layouts, True)

        self.assertNotEqual(baseline, changed_layout)
        self.assertNotEqual(baseline, compact)


if __name__ == "__main__":
    unittest.main()
