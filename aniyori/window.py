"""Main library window for Aniyori."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from .models import AnimeEntry, WatchStatus


APP_ID = "io.github.sakibshahariar.Aniyori"


class AnimeRow(Gtk.Box):
    def __init__(self, entry: AnimeEntry):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.set_margin_start(12)
        self.set_margin_end(12)

        poster = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
        poster.set_pixel_size(34)
        poster.set_valign(Gtk.Align.CENTER)
        poster.add_css_class("dim-label")
        self.append(poster)

        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        details.set_hexpand(True)
        details.set_valign(Gtk.Align.CENTER)
        self.append(details)

        title = Gtk.Label(label=entry.title, xalign=0)
        title.add_css_class("heading")
        title.set_ellipsize(3)
        details.append(title)

        status_text = entry.status.value.replace("_", " ").title()
        subtitle = Gtk.Label(label=f"{status_text} · {entry.progress_label}", xalign=0)
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")
        details.append(subtitle)

        if entry.progress_fraction is not None:
            progress = Gtk.ProgressBar()
            progress.set_fraction(entry.progress_fraction)
            progress.set_valign(Gtk.Align.CENTER)
            progress.set_size_request(100, -1)
            self.append(progress)


class AnimeCard(Gtk.Box):
    def __init__(self, entry: AnimeEntry):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_size_request(180, 180)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.add_css_class("card")

        poster = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
        poster.set_pixel_size(42)
        poster.set_margin_top(14)
        poster.add_css_class("dim-label")
        self.append(poster)

        title = Gtk.Label(label=entry.title, wrap=True, justify=Gtk.Justification.CENTER)
        title.add_css_class("heading")
        title.set_max_width_chars(20)
        self.append(title)

        status = entry.status.value.replace("_", " ").title()
        subtitle = Gtk.Label(label=f"{status}\n{entry.progress_label}", justify=Gtk.Justification.CENTER)
        subtitle.add_css_class("dim-label")
        subtitle.add_css_class("caption")
        self.append(subtitle)

        if entry.progress_fraction is not None:
            progress = Gtk.ProgressBar()
            progress.set_fraction(entry.progress_fraction)
            progress.set_margin_start(12)
            progress.set_margin_end(12)
            self.append(progress)


class AniyoriWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("Aniyori")
        self.set_default_size(1050, 720)
        self.set_size_request(600, 440)
        self.entries: list[AnimeEntry] = []
        self.current_filter = "all"

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
        ]:
            button = Gtk.ToggleButton(label=label)
            button.connect("toggled", self._on_filter_toggled, key)
            toolbar.append(button)
            self.filter_buttons[key] = button
        self.filter_buttons["all"].set_active(True)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        self.view_switch = Gtk.ToggleButton(label="Grid")
        self.view_switch.set_tooltip_text("Switch between list and grid")
        self.view_switch.connect("toggled", self._on_view_toggled)
        toolbar.append(self.view_switch)

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
        empty_title = Gtk.Label(label="Your library is empty")
        empty_title.add_css_class("title-2")
        self.empty_state.append(empty_title)
        empty_description = Gtk.Label(
            label="Add an anime manually for now. AniList sync will arrive in a later milestone.",
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        empty_description.set_max_width_chars(52)
        empty_description.add_css_class("dim-label")
        self.empty_state.append(empty_description)
        empty_add = Gtk.Button(label="Add anime")
        empty_add.add_css_class("suggested-action")
        empty_add.set_halign(Gtk.Align.CENTER)
        empty_add.connect("clicked", self._show_add_dialog)
        self.empty_state.append(empty_add)

        self._render_library()

    def _on_filter_toggled(self, button, key):
        if not button.get_active():
            return
        self.current_filter = key
        for other_key, other_button in self.filter_buttons.items():
            if other_key != key and other_button.get_active():
                other_button.set_active(False)
        self._render_library()

    def _on_view_toggled(self, button):
        self.stack.set_visible_child_name("grid" if button.get_active() else "list")
        button.set_label("List" if button.get_active() else "Grid")

    def _render_library(self, *_args):
        child = self.list_box.get_first_child()
        while child is not None:
            self.list_box.remove(child)
            child = self.list_box.get_first_child()
        child = self.grid_flow.get_first_child()
        while child is not None:
            self.grid_flow.remove(child)
            child = self.grid_flow.get_first_child()

        query = self.search.get_text().strip().casefold() if hasattr(self, "search") else ""
        visible = [
            entry for entry in self.entries
            if (self.current_filter == "all" or entry.status.value == self.current_filter)
            and query in entry.title.casefold()
        ]

        for entry in visible:
            self.list_box.append(AnimeRow(entry))
            self.grid_flow.insert(AnimeCard(entry), -1)

        if not visible:
            if self.empty_state.get_parent() is None:
                self.stack.add_named(self.empty_state, "empty")
            self.stack.set_visible_child_name("empty")
        else:
            self.stack.set_visible_child_name("grid" if self.view_switch.get_active() else "list")

    def _show_add_dialog(self, _button):
        dialog = Adw.AlertDialog(
            heading="Add anime",
            body="Add an entry to your local library. Online search will be added with AniList support.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        title_entry = Gtk.Entry()
        title_entry.set_placeholder_text("Anime title")
        content.append(title_entry)

        total_entry = Gtk.Entry()
        total_entry.set_placeholder_text("Total episodes (optional)")
        total_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        content.append(total_entry)

        status_model = Gtk.StringList.new(["Planning", "Watching", "Completed", "Paused", "Dropped"])
        status_dropdown = Gtk.DropDown(model=status_model)
        content.append(status_dropdown)

        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add to library")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_add_response, (title_entry, total_entry, status_dropdown))

    def _on_add_response(self, dialog, result, widgets):
        try:
            response = dialog.choose_finish(result)
        except Exception:
            return
        if response != "add":
            return

        title_entry, total_entry, status_dropdown = widgets
        title = title_entry.get_text().strip()
        if not title:
            self.toast_overlay.add_toast(Adw.Toast.new("Enter an anime title first."))
            return

        total_text = total_entry.get_text().strip()
        try:
            total = int(total_text) if total_text else None
            if total is not None and total < 0:
                raise ValueError
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
            )
        except (ValueError, IndexError):
            self.toast_overlay.add_toast(Adw.Toast.new("Check the episode count and try again."))
            return

        self.entries.append(entry)
        self.current_filter = "all"
        self.filter_buttons["all"].set_active(True)
        self.search.set_text("")
        self._render_library()
        self.toast_overlay.add_toast(Adw.Toast.new(f"Added {title} to your library."))


class AniyoriApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            window = AniyoriWindow(application=self)
        window.present()
