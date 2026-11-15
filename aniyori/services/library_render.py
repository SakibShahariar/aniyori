"""Pure helpers for keeping cached library widgets in sync."""


def library_widget_signature(entry, airing, selected, layouts, compact):
    """Return the complete cache key shared by selection and rendering."""
    return entry, airing, selected, repr(layouts), compact


def library_stack_page(view, has_visible_entries):
    """Keep the empty-state page visible when switching library views."""
    return view if has_visible_entries else "empty"


def library_view_for_preset(grid_active):
    """Return the selected library view even while its empty-state page is shown."""
    return "grid" if grid_active else "list"
