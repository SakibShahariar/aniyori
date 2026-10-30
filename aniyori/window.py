"""Main library window for Aniyori."""

import logging
import sqlite3
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .models import AnimeEntry, WatchStatus, parse_episode_count
from .search import SearchGeneration
from .services.anilist import AniListClient, AniListError
from .services.covers import get_cached_cover
from .storage import LibraryStorage
from .statistics import calculate_library_statistics

LOGGER = logging.getLogger(__name__)


def _load_cover_async(picture: Gtk.Picture, url: str | None) -> None:
    """Load a cached/downloaded cover without blocking the GTK main thread."""
    if not url:
        return

    def worker():
        try:
            path = get_cached_cover(url)
        except (OSError, RuntimeError, ValueError):
            LOGGER.debug("Could not load cover image %s", url, exc_info=True)
            return
        GLib.idle_add(_apply_cover_texture, picture, str(path))

    threading.Thread(target=worker, daemon=True).start()


def _apply_cover_texture(picture: Gtk.Picture, path: str):
    if picture.get_parent() is None:
        return GLib.SOURCE_REMOVE
    try:
        texture = Gdk.Texture.new_from_filename(path)
    except GLib.Error:
        LOGGER.debug("Could not decode cached cover image %s", path, exc_info=True)
        return GLib.SOURCE_REMOVE
    picture.set_paintable(texture)
    return GLib.SOURCE_REMOVE


class AnimeRow(Gtk.Box):
    def __init__(self, entry: AnimeEntry, on_progress, on_remove, on_edit):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.set_margin_start(12)
        self.set_margin_end(12)

        placeholder = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
        placeholder.set_pixel_size(34)
        poster = Gtk.Picture()
        poster.set_size_request(48, 68)
        poster.set_can_shrink(True)
        poster.set_content_fit(Gtk.ContentFit.COVER)
        poster.set_paintable(placeholder.get_paintable())
        poster.set_valign(Gtk.Align.CENTER)
        self.append(poster)
        _load_cover_async(poster, entry.cover_image)

        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        details.set_hexpand(True)
        details.set_valign(Gtk.Align.CENTER)
        self.append(details)

        title = Gtk.Label(label=entry.title, xalign=0)
        title.add_css_class("heading")
        title.set_ellipsize(3)
        details.append(title)

        status_text = entry.status.value.replace("_", " ").title()
        source_text = (
            f"{entry.provider.title()} #{entry.provider_id}"
            if entry.provider and entry.provider_id
            else f"Manual entry #{entry.storage_id}" if entry.storage_id is not None else "Manual entry"
        )
        subtitle = Gtk.Label(
            label=f"{status_text} · {entry.progress_label} · {source_text}", xalign=0
        )
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")
        details.append(subtitle)

        if entry.progress_fraction is not None:
            progress = Gtk.ProgressBar()
            progress.set_fraction(entry.progress_fraction)
            progress.set_valign(Gtk.Align.CENTER)
            progress.set_size_request(100, -1)
            self.append(progress)

        next_button = Gtk.Button(label="+1")
        can_increment = not (
            entry.status == WatchStatus.COMPLETED
            and entry.episodes_total is not None
            and entry.episodes_watched >= entry.episodes_total
        )
        next_button.set_sensitive(can_increment)
        next_button.set_tooltip_text(
            "Mark one more episode watched" if can_increment else "All known episodes are completed"
        )
        next_button.set_valign(Gtk.Align.CENTER)
        next_button.connect("clicked", lambda _button: on_progress(entry))
        self.append(next_button)

        edit_button = Gtk.Button.new_from_icon_name("document-edit-symbolic")
        edit_button.set_tooltip_text("Edit anime details")
        edit_button.connect("clicked", lambda _button: on_edit(entry))
        self.append(edit_button)

        remove_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        remove_button.set_tooltip_text("Remove anime from library")
        remove_button.connect("clicked", lambda _button: on_remove(entry))
        self.append(remove_button)


class AnimeCard(Gtk.Box):
    def __init__(self, entry: AnimeEntry, on_progress, on_remove, on_edit):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_size_request(180, 180)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.add_css_class("card")

        placeholder = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
        placeholder.set_pixel_size(42)
        poster = Gtk.Picture()
        poster.set_size_request(112, 148)
        poster.set_can_shrink(True)
        poster.set_content_fit(Gtk.ContentFit.COVER)
        poster.set_paintable(placeholder.get_paintable())
        poster.set_halign(Gtk.Align.CENTER)
        poster.set_margin_top(14)
        self.append(poster)
        _load_cover_async(poster, entry.cover_image)

        title = Gtk.Label(label=entry.title, wrap=True, justify=Gtk.Justification.CENTER)
        title.add_css_class("heading")
        title.set_max_width_chars(20)
        self.append(title)

        status = entry.status.value.replace("_", " ").title()
        source_text = (
            f"{entry.provider.title()} #{entry.provider_id}"
            if entry.provider and entry.provider_id
            else f"Manual entry #{entry.storage_id}" if entry.storage_id is not None else "Manual entry"
        )
        subtitle = Gtk.Label(
            label=f"{status}\n{entry.progress_label}\n{source_text}",
            justify=Gtk.Justification.CENTER,
        )
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")
        self.append(subtitle)

        if entry.progress_fraction is not None:
            progress = Gtk.ProgressBar()
            progress.set_fraction(entry.progress_fraction)
            progress.set_margin_start(12)
            progress.set_margin_end(12)
            self.append(progress)

        next_button = Gtk.Button(label="+1 episode")
        can_increment = not (
            entry.status == WatchStatus.COMPLETED
            and entry.episodes_total is not None
            and entry.episodes_watched >= entry.episodes_total
        )
        next_button.set_sensitive(can_increment)
        next_button.set_tooltip_text(
            "Mark one more episode watched" if can_increment else "All known episodes are completed"
        )
        next_button.set_halign(Gtk.Align.CENTER)
        next_button.connect("clicked", lambda _button: on_progress(entry))
        self.append(next_button)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.CENTER)
        edit_button = Gtk.Button.new_from_icon_name("document-edit-symbolic")
        edit_button.set_tooltip_text("Edit anime details")
        edit_button.connect("clicked", lambda _button: on_edit(entry))
        actions.append(edit_button)
        remove_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        remove_button.set_tooltip_text("Remove anime from library")
        remove_button.connect("clicked", lambda _button: on_remove(entry))
        actions.append(remove_button)
        self.append(actions)


class AniyoriWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Aniyori")
        self.set_default_size(1050, 720)
        self.set_size_request(600, 440)
        self.storage = LibraryStorage()
        self.entries: list[AnimeEntry] = self.storage.list_entries()
        self.current_filter = "all"
        self._undo_entry: AnimeEntry | None = None
        self._undo_toast = None
        undo_action = Gio.SimpleAction.new("undo-delete", None)
        undo_action.connect("activate", self._undo_last_removal)
        self.add_action(undo_action)
        for name, callback in [
            ("add-anime", lambda: self._show_add_dialog(None)),
            ("focus-search", lambda: self.search.grab_focus()),
            ("quit", lambda: self.get_application().quit()),
            ("statistics", self._show_statistics_dialog),
            ("about", self._show_about_dialog),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _parameter, callback=callback: callback())
            self.add_action(action)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)
        header.set_title_widget(Adw.WindowTitle(title="Aniyori", subtitle="Your anime library"))

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search your library")
        self.search.set_size_request(220, -1)
        self.search.connect("search-changed", self._render_library)
        header.pack_start(self.search)

        add_button = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_button.set_tooltip_text("Add anime")
        add_button.add_css_class("suggested-action")
        add_button.connect("clicked", self._show_add_dialog)
        header.pack_end(add_button)

        primary_menu = Gio.Menu()
        primary_menu.append("Add Anime", "win.add-anime")
        primary_menu.append("Search Library", "win.focus-search")
        primary_menu.append("Library Statistics", "win.statistics")
        primary_menu.append("About Aniyori", "win.about")
        primary_menu.append("Quit", "win.quit")
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text("Main menu")
        menu_button.set_menu_model(primary_menu)
        header.pack_end(menu_button)

        shortcuts = Gtk.ShortcutController()
        shortcuts.set_scope(Gtk.ShortcutScope.GLOBAL)
        for trigger, action_name in [
            ("<Control>n", "win.add-anime"),
            ("<Control>f", "win.focus-search"),
            ("<Control>q", "win.quit"),
        ]:
            shortcuts.add_shortcut(
                Gtk.Shortcut.new(
                    Gtk.ShortcutTrigger.parse_string(trigger),
                    Gtk.NamedAction.new(action_name),
                )
            )
        self.add_controller(shortcuts)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        body.set_margin_start(20)
        body.set_margin_end(20)
        body.set_margin_top(12)
        body.set_margin_bottom(12)
        root.append(body)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_bottom(12)
        body.append(toolbar)

        self.filter_buttons = {}
        for key, label in [
            ("all", "All"),
            ("watching", "Watching"),
            ("planning", "Planning"),
            ("completed", "Completed"),
            ("paused", "Paused"),
            ("dropped", "Dropped"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.connect("toggled", self._on_filter_toggled, key)
            toolbar.append(button)
            self.filter_buttons[key] = button
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        self.view_switches = {}
        first_view_button = None
        for key, label in [("list", "List"), ("grid", "Grid")]:
            button = Gtk.ToggleButton(label=label)
            if first_view_button is None:
                first_view_button = button
            else:
                button.set_group(first_view_button)
            button.connect("toggled", self._on_view_toggled, key)
            toolbar.append(button)
            self.view_switches[key] = button

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_vexpand(True)
        body.append(self.toast_overlay)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.toast_overlay.set_child(self.stack)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        self.list_scroll = Gtk.ScrolledWindow()
        self.list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_scroll.set_child(self.list_box)
        self.stack.add_named(self.list_scroll, "list")

        self.grid_flow = Gtk.FlowBox()
        self.grid_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid_flow.set_homogeneous(True)
        self.grid_flow.set_min_children_per_line(2)
        self.grid_flow.set_max_children_per_line(6)
        self.grid_flow.set_row_spacing(12)
        self.grid_flow.set_column_spacing(12)
        self.grid_flow.set_valign(Gtk.Align.START)
        self.grid_scroll = Gtk.ScrolledWindow()
        self.grid_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.grid_scroll.set_child(self.grid_flow)
        self.stack.add_named(self.grid_scroll, "grid")

        self.empty_state = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        self.empty_state.set_margin_top(40)
        self.empty_state.set_margin_bottom(40)
        empty_icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
        empty_icon.set_pixel_size(48)
        empty_icon.add_css_class("dim-label")
        self.empty_state.append(empty_icon)
        self.empty_title = Gtk.Label(label="Your library is empty")
        self.empty_title.add_css_class("title-2")
        self.empty_state.append(self.empty_title)
        self.empty_description = Gtk.Label(
            label="Add an anime manually for now, or search the AniList catalogue.",
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        self.empty_description.set_max_width_chars(52)
        self.empty_description.add_css_class("dim-label")
        self.empty_state.append(self.empty_description)
        self.empty_add = Gtk.Button(label="Add anime")
        self.empty_add.add_css_class("suggested-action")
        self.empty_add.set_halign(Gtk.Align.CENTER)
        self.empty_add.connect("clicked", self._show_add_dialog)
        self.empty_state.append(self.empty_add)

        self.view_switches["list"].set_active(True)
        self._render_library()
        self.filter_buttons["all"].set_active(True)

    def _show_statistics_dialog(self):
        stats = calculate_library_statistics(self.entries)
        statuses = stats["status_counts"]
        status_lines = [
            f"{status.value.title()}: {statuses[status.value]}"
            for status in WatchStatus
        ]
        estimated_hours = stats["estimated_minutes"] / 60
        body = (
            f"Anime in library: {stats['anime_count']}\n"
            f"Episodes watched: {stats['episodes_watched']}\n"
            f"Known episode total: {stats['known_episodes_total']}\n"
            f"Completed anime: {stats['completion_rate']}%\n"
            f"Estimated watch time: {estimated_hours:.1f} hours "
            "(24 minutes per episode)\n\n"
            + "\n".join(status_lines)
        )
        dialog = Adw.AlertDialog(
            heading="Library Statistics",
            body=body,
        )
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)

    def _show_about_dialog(self):
        about = Adw.AboutDialog(
            application_name="Aniyori",
            application_icon="io.github.sakibshahariar.Aniyori",
            version="0.1.0",
            developer_name="Sakib Shahariar",
            comments="A native Linux anime library and progress tracker.",
        )
        about.present(self)

    def _on_filter_toggled(self, button, key):
        if not button.get_active():
            if self.current_filter == key:
                button.set_active(True)
            return
        self.current_filter = key
        for other_key, other_button in self.filter_buttons.items():
            if other_key != key and other_button.get_active():
                other_button.set_active(False)
        self._render_library()

    def _on_view_toggled(self, button, key):
        if not button.get_active():
            return
        self.stack.set_visible_child_name(key)

    def _render_library(self, *_args):
        list_scroll_value = self.list_scroll.get_vadjustment().get_value()
        grid_scroll_value = self.grid_scroll.get_vadjustment().get_value()

        if not hasattr(self, "_row_widgets"):
            self._row_widgets = {}
            self._card_widgets = {}
            self._widget_entries = {}

        current_keys = {
            entry.storage_id if entry.storage_id is not None else ("transient", id(entry))
            for entry in self.entries
        }
        for key in set(self._row_widgets) - current_keys:
            row = self._row_widgets.pop(key)
            card = self._card_widgets.pop(key)
            self._widget_entries.pop(key, None)
            if row.get_parent() is not None:
                self.list_box.remove(row.get_parent())
            if card.get_parent() is not None:
                self.grid_flow.remove(card.get_parent())

        query = self.search.get_text().strip().casefold() if hasattr(self, "search") else ""
        for position, entry in enumerate(self.entries):
            key = entry.storage_id if entry.storage_id is not None else ("transient", id(entry))
            row = self._row_widgets.get(key)
            card = self._card_widgets.get(key)

            if row is None or self._widget_entries.get(key) != entry:
                if row is not None:
                    if row.get_parent() is not None:
                        self.list_box.remove(row.get_parent())
                    if card.get_parent() is not None:
                        self.grid_flow.remove(card.get_parent())

                row = AnimeRow(
                    entry,
                    self._increment_progress,
                    self._confirm_remove_entry,
                    self._show_edit_dialog,
                )
                card = AnimeCard(
                    entry,
                    self._increment_progress,
                    self._confirm_remove_entry,
                    self._show_edit_dialog,
                )
                self.list_box.insert(row, position)
                self.grid_flow.insert(card, position)
                self._row_widgets[key] = row
                self._card_widgets[key] = card
                self._widget_entries[key] = entry
            else:
                self.list_box.reorder_child(row.get_parent(), position)
                self.grid_flow.reorder_child(card.get_parent(), position)

            is_visible = (
                (self.current_filter == "all" or entry.status.value == self.current_filter)
                and query in entry.title.casefold()
            )
            row.get_parent().set_visible(is_visible)
            card.get_parent().set_visible(is_visible)

        visible_count = sum(
            1
            for entry in self.entries
            if (self.current_filter == "all" or entry.status.value == self.current_filter)
            and query in entry.title.casefold()
        )
        if not visible_count:
            if not self.entries:
                self.empty_title.set_label("Your library is empty")
                self.empty_description.set_label(
                    "Add an anime manually, or search the AniList catalogue to get started."
                )
                self.empty_add.set_visible(True)
            else:
                self.empty_title.set_label("No matching anime")
                self.empty_description.set_label(
                    "Try a different search or choose another status filter."
                )
                self.empty_add.set_visible(False)
            if self.empty_state.get_parent() is None:
                self.stack.add_named(self.empty_state, "empty")
            self.stack.set_visible_child_name("empty")
        else:
            self.stack.set_visible_child_name(
                "grid" if self.view_switches["grid"].get_active() else "list"
            )
        GLib.idle_add(
            self._restore_scroll_positions, list_scroll_value, grid_scroll_value
        )

    def _restore_scroll_positions(self, list_value: float, grid_value: float):
        self.list_scroll.get_vadjustment().set_value(list_value)
        self.grid_scroll.get_vadjustment().set_value(grid_value)
        return GLib.SOURCE_REMOVE

    def _increment_progress(self, entry: AnimeEntry):
        if entry.episodes_total is not None and entry.episodes_watched >= entry.episodes_total:
            self.toast_overlay.add_toast(Adw.Toast.new("All known episodes are already marked watched."))
            return
        try:
            if entry.storage_id is None:
                self.toast_overlay.add_toast(Adw.Toast.new("This library entry has no storage ID."))
                return
            updated = self.storage.update_progress(entry.storage_id, entry.episodes_watched + 1)
        except ValueError as error:
            self.toast_overlay.add_toast(Adw.Toast.new(str(error)))
            return
        if updated:
            self.entries = self.storage.list_entries()
            self._render_library()
            self.toast_overlay.add_toast(Adw.Toast.new(f"Progress updated: {entry.title}"))
        else:
            self.toast_overlay.add_toast(
                Adw.Toast.new("That anime could not be updated. Try again.")
            )

    def _show_edit_dialog(self, entry: AnimeEntry):
        dialog = Adw.AlertDialog(
            heading="Edit anime",
            body="Update the title, episode counts, and library status.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        title_entry = Gtk.Entry(text=entry.title)
        title_entry.set_placeholder_text("Anime title")
        content.append(title_entry)
        total_entry = Gtk.Entry(text="" if entry.episodes_total is None else str(entry.episodes_total))
        total_entry.set_placeholder_text("Total episodes (optional)")
        total_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        content.append(total_entry)
        watched_entry = Gtk.Entry(text=str(entry.episodes_watched))
        watched_entry.set_placeholder_text("Episodes watched")
        watched_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        content.append(watched_entry)
        statuses = [WatchStatus.PLANNING, WatchStatus.WATCHING, WatchStatus.COMPLETED,
                    WatchStatus.PAUSED, WatchStatus.DROPPED]
        status_dropdown = Gtk.DropDown(model=Gtk.StringList.new(
            [status.value.title() for status in statuses]
        ))
        status_dropdown.set_selected(statuses.index(entry.status))
        content.append(status_dropdown)
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save changes")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_edit_response,
                      (entry, title_entry, total_entry, watched_entry, status_dropdown, statuses))

    def _on_edit_response(self, dialog, result, widgets):
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            LOGGER.warning("Could not finish an application dialog", exc_info=True)
            return
        if response != "save":
            return
        original, title_entry, total_entry, watched_entry, status_dropdown, statuses = widgets
        try:
            title = title_entry.get_text().strip()
            total = parse_episode_count(
                total_entry.get_text(), optional=True, field_name="Total episode count"
            )
            watched = parse_episode_count(
                watched_entry.get_text(), field_name="Watched episode count"
            )
            status = statuses[status_dropdown.get_selected()]
            if not title:
                raise ValueError("Anime title must not be empty.")
            if total is not None and total < 0:
                raise ValueError("Total episode count cannot be negative.")
            if watched < 0 or (total is not None and watched > total):
                raise ValueError("Watched episodes must be between zero and the total.")
            if status == WatchStatus.COMPLETED and total is not None:
                watched = total
            edited = AnimeEntry(title=title, episodes_total=total, episodes_watched=watched,
                                status=status, provider=original.provider,
                                provider_id=original.provider_id, cover_image=original.cover_image,
                                storage_id=original.storage_id)
            if not self.storage.update_entry(edited):
                self.toast_overlay.add_toast(Adw.Toast.new("That anime no longer exists."))
                return
        except (ValueError, IndexError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(str(error) or "Check the entered values."))
            return
        self.entries = self.storage.list_entries()
        self._render_library()
        self.toast_overlay.add_toast(Adw.Toast.new(f"Updated {edited.title}."))

    def _confirm_remove_entry(self, entry: AnimeEntry):
        dialog = Adw.AlertDialog(
            heading="Remove anime?",
            body=f"Remove ‘{entry.title}’ from your local library? You can undo this for 10 seconds.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_remove_response, entry)

    def _on_remove_response(self, dialog, result, entry: AnimeEntry):
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            LOGGER.warning("Could not finish an application dialog", exc_info=True)
            return
        if response != "remove":
            return
        if entry.storage_id is None:
            self.toast_overlay.add_toast(Adw.Toast.new("This library entry has no storage ID."))
            return
        if not self.storage.remove(entry.storage_id):
            self.toast_overlay.add_toast(Adw.Toast.new("That anime was already removed."))
            return
        self.entries = self.storage.list_entries()
        self._render_library()
        if self._undo_toast is not None:
            self._undo_entry = None
            self._undo_toast.dismiss()
            self._undo_toast = None
        self._undo_entry = entry
        toast = Adw.Toast.new(f"Removed {entry.title}.")
        toast.set_button_label("Undo")
        toast.set_action_name("win.undo-delete")
        toast.set_timeout(10)
        toast.connect("dismissed", self._on_undo_toast_dismissed, entry)
        self._undo_toast = toast
        self.toast_overlay.add_toast(toast)

    def _on_undo_toast_dismissed(self, _toast, entry: AnimeEntry):
        if self._undo_entry is entry:
            self._undo_entry = None
            self._undo_toast = None

    def _undo_last_removal(self, _action, _parameter):
        entry = self._undo_entry
        if entry is None:
            return
        self._undo_entry = None
        self._undo_toast = None
        try:
            self.storage.restore(entry)
        except (ValueError, sqlite3.Error, OSError):
            LOGGER.exception("Could not restore deleted anime entry %r", entry.title)
            self.toast_overlay.add_toast(
                Adw.Toast.new("Could not undo removal. The library may have changed.")
            )
            return
        self.entries = self.storage.list_entries()
        self._render_library()
        self.toast_overlay.add_toast(Adw.Toast.new(f"Restored {entry.title}."))

    def _show_add_dialog(self, _button):
        dialog = Adw.AlertDialog(
            heading="Add anime",
            body="Search AniList or enter a title manually, then review its details.",
        )
        pages = Gtk.Stack()
        pages.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)

        search_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        title_entry = Gtk.Entry()
        title_entry.set_placeholder_text("Anime title (manual entry)")
        search_page.append(title_entry)

        catalogue_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        catalogue_search = Gtk.Entry()
        catalogue_search.set_placeholder_text("Search AniList catalogue")
        catalogue_search.set_hexpand(True)
        catalogue_row.append(catalogue_search)
        catalogue_button = Gtk.Button(label="Search")
        catalogue_row.append(catalogue_button)
        search_page.append(catalogue_row)

        catalogue_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new(["Search results will appear here"])
        )
        catalogue_dropdown.set_sensitive(False)
        search_page.append(catalogue_dropdown)
        next_button = Gtk.Button(label="Review details")
        next_button.add_css_class("suggested-action")
        next_button.set_halign(Gtk.Align.END)
        search_page.append(next_button)
        pages.add_named(search_page, "search")

        details_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        detail_title_entry = Gtk.Entry()
        detail_title_entry.set_placeholder_text("Anime title")
        details_page.append(detail_title_entry)
        details_summary = Gtk.Label(xalign=0, wrap=True)
        details_summary.add_css_class("dim-label")
        details_page.append(details_summary)

        total_entry = Gtk.Entry()
        total_entry.set_placeholder_text("Total episodes (optional)")
        total_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        details_page.append(total_entry)

        statuses = [
            WatchStatus.PLANNING,
            WatchStatus.WATCHING,
            WatchStatus.COMPLETED,
            WatchStatus.PAUSED,
            WatchStatus.DROPPED,
        ]
        status_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new([status.value.title() for status in statuses])
        )
        details_page.append(status_dropdown)
        back_button = Gtk.Button(label="Back")
        back_button.set_halign(Gtk.Align.START)
        details_page.append(back_button)
        pages.add_named(details_page, "details")
        dialog.set_extra_child(pages)

        catalogue_state = {"results": [], "selected": None, "pending": False}
        search_generation = SearchGeneration()

        def invalidate_pending_search():
            if not catalogue_state["pending"]:
                return
            search_generation.invalidate()
            catalogue_state["pending"] = False
            catalogue_state["results"] = []
            catalogue_state["selected"] = None
            catalogue_dropdown.set_model(
                Gtk.StringList.new(["Search results will appear here"])
            )
            catalogue_dropdown.set_sensitive(False)
            catalogue_button.set_sensitive(True)
            catalogue_button.set_label("Search")

        def clear_catalogue_selection_if_title_changed(entry_widget):
            selected = catalogue_state["selected"]
            if selected and entry_widget.get_text() != selected["title"]:
                catalogue_state["selected"] = None
            invalidate_pending_search()

        title_entry.connect("changed", clear_catalogue_selection_if_title_changed)
        catalogue_search.connect("changed", lambda _entry: invalidate_pending_search())

        def select_catalogue_result(dropdown, _property):
            index = dropdown.get_selected()
            results = catalogue_state["results"]
            if index >= len(results):
                return
            item = results[index]
            catalogue_state["selected"] = item
            title_entry.set_text(item["title"])
            total_entry.set_text(
                str(item["episodes"]) if item["episodes"] is not None else ""
            )

        def apply_catalogue_results(results, request_id):
            if not search_generation.is_current(request_id):
                return
            catalogue_state["pending"] = False
            catalogue_state["results"] = results
            catalogue_state["selected"] = None
            labels = [
                "{} · {} eps".format(
                    item["title"], item["episodes"] if item["episodes"] else "unknown"
                )
                for item in results
            ] or ["No results found"]
            catalogue_dropdown.set_model(Gtk.StringList.new(labels))
            catalogue_dropdown.set_sensitive(bool(results))
            catalogue_button.set_sensitive(True)
            catalogue_button.set_label("Search")
            if results:
                catalogue_dropdown.set_selected(0)
                select_catalogue_result(catalogue_dropdown, None)
            else:
                self.toast_overlay.add_toast(Adw.Toast.new("No AniList results found."))

        def show_catalogue_error(message, request_id):
            if not search_generation.is_current(request_id):
                return
            catalogue_state["pending"] = False
            catalogue_state["results"] = []
            catalogue_state["selected"] = None
            catalogue_dropdown.set_model(
                Gtk.StringList.new(["Search failed. Try again."])
            )
            catalogue_dropdown.set_sensitive(False)
            catalogue_button.set_sensitive(True)
            catalogue_button.set_label("Retry")
            self.toast_overlay.add_toast(Adw.Toast.new("AniList search failed: " + message))

        def start_catalogue_search(_button):
            query = catalogue_search.get_text().strip()
            if not query:
                self.toast_overlay.add_toast(
                    Adw.Toast.new("Enter a title to search AniList.")
                )
                return
            request_id = search_generation.begin()
            catalogue_state["pending"] = True
            catalogue_state["results"] = []
            catalogue_state["selected"] = None
            catalogue_dropdown.set_model(Gtk.StringList.new(["Searching AniList…"]))
            catalogue_dropdown.set_sensitive(False)
            catalogue_button.set_sensitive(False)
            catalogue_button.set_label("Searching…")

            def worker():
                try:
                    results = AniListClient().search_anime(query)
                    GLib.idle_add(apply_catalogue_results, results, request_id)
                except AniListError as error:
                    GLib.idle_add(show_catalogue_error, str(error), request_id)
                except Exception:
                    LOGGER.exception(
                        "Unexpected error while searching AniList for %r", query
                    )
                    GLib.idle_add(
                        show_catalogue_error,
                        "An unexpected error occurred. Please try again.",
                        request_id,
                    )

            threading.Thread(target=worker, daemon=True).start()

        def show_details(_button):
            title = title_entry.get_text().strip()
            if not title:
                self.toast_overlay.add_toast(
                    Adw.Toast.new("Enter a title or select an AniList result first.")
                )
                return
            detail_title_entry.set_text(title)
            selected = catalogue_state["selected"]
            if selected:
                metadata = [
                    value for value in (selected.get("format"), selected.get("season_year"))
                    if value
                ]
                details_summary.set_label(
                    "AniList catalogue entry"
                    + (f" · {' · '.join(str(value) for value in metadata)}" if metadata else "")
                )
            else:
                details_summary.set_label("Manual library entry")
            pages.set_visible_child_name("details")
            dialog.set_response_enabled("add", True)

        def show_search(_button):
            title_entry.set_text(detail_title_entry.get_text())
            pages.set_visible_child_name("search")
            dialog.set_response_enabled("add", False)

        catalogue_button.connect("clicked", start_catalogue_search)
        catalogue_dropdown.connect("notify::selected", select_catalogue_result)
        next_button.connect("clicked", show_details)
        back_button.connect("clicked", show_search)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add to library")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_enabled("add", False)
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")
        dialog.choose(
            self,
            None,
            self._on_add_response,
            (detail_title_entry, total_entry, status_dropdown, catalogue_state),
        )

    def _on_add_response(self, dialog, result, widgets):
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            LOGGER.warning("Could not finish an application dialog", exc_info=True)
            return
        if response != "add":
            return

        title_entry, total_entry, status_dropdown, catalogue_state = widgets
        title = title_entry.get_text().strip()
        if not title:
            self.toast_overlay.add_toast(Adw.Toast.new("Enter an anime title first."))
            return

        try:
            total = parse_episode_count(
                total_entry.get_text(), optional=True, field_name="Total episode count"
            )
            status = [
                WatchStatus.PLANNING,
                WatchStatus.WATCHING,
                WatchStatus.COMPLETED,
                WatchStatus.PAUSED,
                WatchStatus.DROPPED,
            ][status_dropdown.get_selected()]
            watched = total if status == WatchStatus.COMPLETED and total is not None else 0
            entry = AnimeEntry(
                title=title,
                episodes_total=total,
                episodes_watched=watched,
                status=status,
                provider="anilist" if catalogue_state["selected"] else None,
                provider_id=(
                    str(catalogue_state["selected"]["id"])
                    if catalogue_state["selected"] else None
                ),
                cover_image=(
                    catalogue_state["selected"].get("cover_image")
                    if catalogue_state["selected"] else None
                ),
            )
        except (ValueError, IndexError):
            self.toast_overlay.add_toast(Adw.Toast.new("Check the episode count and try again."))
            return

        if entry.provider is None and entry.provider_id is None:
            matches = self.storage.find_manual_title_matches(entry.title)
            if matches:
                self._show_duplicate_choice(entry, matches)
                return
        self._save_new_entry(entry)

    def _show_duplicate_choice(self, entry: AnimeEntry, matches: list[AnimeEntry]):
        dialog = Adw.AlertDialog(
            heading="Possible duplicate",
            body=(
                f"{len(matches)} manual {'entry matches' if len(matches) == 1 else 'entries match'} "
                f"“{entry.title}”. Edit an existing entry or add another edition."
            ),
        )
        labels = [
            f"#{item.storage_id} · {item.status.value.title()} · {item.progress_label}"
            for item in matches
        ]
        dropdown = Gtk.DropDown(model=Gtk.StringList.new(labels))
        dropdown.set_selected(0)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.append(Gtk.Label(label="Existing entries", xalign=0))
        content.append(dropdown)
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("edit", "Edit selected")
        dialog.add_response("add-anyway", "Add another edition")
        dialog.set_response_appearance("edit", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("edit")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_duplicate_choice_response, (entry, matches, dropdown))

    def _on_duplicate_choice_response(self, dialog, result, data):
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            LOGGER.warning("Could not finish duplicate-entry dialog", exc_info=True)
            return
        entry, matches, dropdown = data
        if response == "edit":
            index = dropdown.get_selected()
            if index < len(matches):
                self._show_edit_dialog(matches[index])
        elif response == "add-anyway":
            self._save_new_entry(entry)

    def _save_new_entry(self, entry: AnimeEntry):
        try:
            self.storage.add(entry)
        except ValueError as error:
            self.toast_overlay.add_toast(Adw.Toast.new(str(error)))
            return
        except (sqlite3.Error, OSError):
            LOGGER.exception("Could not save anime entry %r", entry.title)
            self.toast_overlay.add_toast(
                Adw.Toast.new("Could not save anime. Check storage availability and permissions.")
            )
            return
        self.entries = self.storage.list_entries()
        self.current_filter = "all"
        self.filter_buttons["all"].set_active(True)
        self.search.set_text("")
        self._render_library()
        self.toast_overlay.add_toast(Adw.Toast.new(f"Added {entry.title} to your library."))

