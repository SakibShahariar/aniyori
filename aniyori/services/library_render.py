"""Pure helpers for keeping cached library widgets in sync."""


def library_layout_signature(layouts):
    """Serialize the small layout configuration once per library render."""
    return repr(layouts)


def library_widget_signature(entry, airing, selected, layout_signature, compact):
    """Return the complete cache key shared by selection and rendering."""
    return entry, airing, selected, layout_signature, compact


def library_stack_page(view, has_visible_entries):
    """Keep the empty-state page visible when switching library views."""
    return view if has_visible_entries else "empty"


def library_view_for_preset(grid_active):
    """Return the selected library view even while its empty-state page is shown."""
    return "grid" if grid_active else "list"
