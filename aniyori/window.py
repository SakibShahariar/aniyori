"""Main library window for Aniyori."""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .models import MAX_EPISODE_COUNT, AnimeEntry, WatchStatus, parse_episode_count
from .backup import BackupError, create_backup, default_config_dir, restore_backup
from .services.recognition_exclusions import RecognitionExclusionError, RecognitionExclusionStore
from .library_io import export_csv, export_json, import_csv, import_json
from .search import SearchGeneration
from .services.search_history import SearchHistoryError, SearchHistoryStore
from .services.anilist import AniListClient, AniListError
from .services.airing import format_airing_countdown
from .services.seasons import SEASONS, filter_season_results, season_for_date
from .services.scan_locations import ScanLocationStore
from .services.scan_library import scan_configured_library
from .services.release_scoring import (
    DEFAULT_MINIMUM_SCORE, DEFAULT_WEIGHTS, ReleaseScoringSettingsStore,
)
from .services.release_monitor import filter_release_results, refresh_release_feeds
from .services.release_rules import ReleaseRuleStore, evaluate_release_rules
from .services.credentials import CredentialStoreError, SecretServiceCredentialStore
from .services.qbittorrent import (
    QBittorrentClient, QBittorrentError, QBittorrentSettings, QBittorrentSettingsStore,
)
from .services.rss import FeedParseError, RSSFeedStore, build_nyaa_search_url
from .services.anime_release_preferences import AnimeReleasePreferenceError, AnimeReleasePreferenceStore
from .services.release_preferences import (
    PREFERENCE_ATTRIBUTES, ReleasePreferenceError, ReleasePreferenceStore,
    evaluate_release_preferences,
)
from .services.share_templates import (
    DEFAULT_SHARE_TEMPLATE, ShareTemplateError, ShareTemplateStore,
    render_share_template, share_context_for_entry,
)
from .services.covers import get_cached_cover
from .storage import LibraryStorage
from .statistics import calculate_history_insights, calculate_library_statistics
from .services.library_sort import SORT_MODES, sort_library_entries
from .services.external_links import ExternalLinkError, ExternalLinkStore, links_for_entry
from .services.webhooks import WebhookError, WebhookStore, deliver_webhooks
from .services.player_detection import (
    PlayerDetectionSettings, PlayerDetectionSettingsStore,
    match_playback_file, playback_finished, supported_player_names,
)
from .services.notifications import (
    EVENT_TYPES, NotificationError, NotificationPreferences, NotificationStore,
)
from .services.network import NetworkSettings, NetworkSettingsError, NetworkSettingsStore
from .services.profiles import ProfileError, ProfileStore
from .services.library_layout import DEFAULT_LAYOUTS as DEFAULT_LIBRARY_LAYOUTS, LibraryLayoutError, LibraryLayoutStore

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
    def __init__(self, entry: AnimeEntry, on_progress, on_remove, on_edit, airing=None, selected=False, on_select=None, on_links=None, on_episodes=None, layout=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.set_margin_start(12)
        self.set_margin_end(12)

        self.selection_check = Gtk.CheckButton()
        self.selection_check.set_active(selected)
        self.selection_check.set_tooltip_text("Select anime for bulk actions")
        self.selection_check.connect(
            "toggled",
            lambda button: on_select(entry, button.get_active()) if on_select else None,
        )
        self.prepend(self.selection_check)

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
        layout = layout or DEFAULT_LIBRARY_LAYOUTS["list"]
        title.set_size_request(layout["widths"]["title"], -1)
        details.append(title)

        status_text = entry.status.value.replace("_", " ").title()
        source_text = (
            f"{entry.provider.title()} #{entry.provider_id}"
            if entry.provider and entry.provider_id
            else f"Manual entry #{entry.storage_id}" if entry.storage_id is not None else "Manual entry"
        )
        metadata = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        metadata.set_hexpand(True)
        self.layout_fields = {
            "status": Gtk.Label(label=status_text, xalign=0),
            "progress": Gtk.Label(label=entry.progress_label, xalign=0),
            "source": Gtk.Label(label=source_text, xalign=0),
            "airing": Gtk.Label(label=format_airing_countdown(*airing) if airing is not None else "", xalign=0),
        }
        self.airing_label = self.layout_fields["airing"]
        for column in layout["order"]:
            if column == "title":
                continue
            field = self.layout_fields[column]
            field.set_visible(column in layout["visible"] and (column != "airing" or airing is not None))
            field.set_size_request(layout["widths"].get(column, -1), -1)
            field.add_css_class("dim-label")
            field.add_css_class("caption")
            metadata.append(field)
        self.airing_label.add_css_class("accent")
        details.append(metadata)

        if entry.progress_fraction is not None:
            progress = Gtk.ProgressBar()
            progress.set_fraction(entry.progress_fraction)
            progress.set_valign(Gtk.Align.CENTER)
            progress.set_size_request(100, -1)
            progress.set_visible("progress" in layout["visible"])
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

        episodes_button = Gtk.Button(label="Episodes")
        episodes_button.set_tooltip_text("Edit watched state for individual episodes")
        episodes_button.connect("clicked", lambda _button: on_episodes(entry) if on_episodes else None)
        self.append(episodes_button)

        links_button = Gtk.Button(label="Links")
        links_button.set_tooltip_text("Open external anime information links")
        links_button.connect("clicked", lambda button: on_links(entry, button) if on_links else None)
        self.append(links_button)

        edit_button = Gtk.Button.new_from_icon_name("document-edit-symbolic")
        edit_button.set_tooltip_text("Edit anime details")
        edit_button.connect("clicked", lambda _button: on_edit(entry))
        self.append(edit_button)

        remove_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        remove_button.set_tooltip_text("Remove anime from library")
        remove_button.connect("clicked", lambda _button: on_remove(entry))
        self.append(remove_button)


class AnimeCard(Gtk.Box):
    def __init__(self, entry: AnimeEntry, on_progress, on_remove, on_edit, airing=None, selected=False, on_select=None, on_links=None, on_episodes=None, layout=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_size_request(180, 180)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.add_css_class("card")

        self.selection_check = Gtk.CheckButton()
        self.selection_check.set_active(selected)
        self.selection_check.set_tooltip_text("Select anime for bulk actions")
        self.selection_check.connect(
            "toggled",
            lambda button: on_select(entry, button.get_active()) if on_select else None,
        )
        self.prepend(self.selection_check)

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
        layout = layout or DEFAULT_LIBRARY_LAYOUTS["grid"]

        status = entry.status.value.replace("_", " ").title()
        source_text = (
            f"{entry.provider.title()} #{entry.provider_id}"
            if entry.provider and entry.provider_id
            else f"Manual entry #{entry.storage_id}" if entry.storage_id is not None else "Manual entry"
        )
        self.layout_fields = {
            "status": Gtk.Label(label=status, justify=Gtk.Justification.CENTER),
            "progress": Gtk.Label(label=entry.progress_label, justify=Gtk.Justification.CENTER),
            "source": Gtk.Label(label=source_text, justify=Gtk.Justification.CENTER),
            "airing": Gtk.Label(label=format_airing_countdown(*airing) if airing is not None else "", justify=Gtk.Justification.CENTER),
        }
        self.airing_label = self.layout_fields["airing"]
        for column in layout["order"]:
            if column == "title":
                continue
            field = self.layout_fields[column]
            field.set_visible(column in layout["visible"] and (column != "airing" or airing is not None))
            field.add_css_class("dim-label")
            field.add_css_class("caption")
            self.append(field)

        if entry.progress_fraction is not None:
            progress = Gtk.ProgressBar()
            progress.set_fraction(entry.progress_fraction)
            progress.set_margin_start(12)
            progress.set_margin_end(12)
            progress.set_visible("progress" in layout["visible"])
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

        episodes_button = Gtk.Button(label="Episodes")
        episodes_button.set_tooltip_text("Edit watched state for individual episodes")
        episodes_button.connect("clicked", lambda _button: on_episodes(entry) if on_episodes else None)
        episodes_button.set_halign(Gtk.Align.CENTER)
        self.append(episodes_button)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.CENTER)
        links_button = Gtk.Button.new_from_icon_name("external-link-symbolic")
        links_button.set_tooltip_text("Open external anime information links")
        links_button.connect("clicked", lambda button: on_links(entry, button) if on_links else None)
        actions.append(links_button)
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
        self._airing_by_id = {}
        self._airing_refresh_running = False
        self._airing_notification_timers = {}
        self._selected_entry_ids = set()
        self.scan_location_store = ScanLocationStore()
        self.recognition_exclusion_store = RecognitionExclusionStore()
        self.share_template_store = ShareTemplateStore()
        self.external_link_store = ExternalLinkStore()
        self.webhook_store = WebhookStore()
        self.notification_store = NotificationStore()
        self.player_detection_store = PlayerDetectionSettingsStore()
        try:
            self.player_detection_settings = self.player_detection_store.load()
        except (OSError, ValueError) as error:
            LOGGER.warning("Could not load player detection settings: %s", error)
            self.player_detection_settings = PlayerDetectionSettings()
        self._player_poll_running = False
        self._player_poll_source = None
        self.network_settings_store = NetworkSettingsStore()
        self.profile_store = ProfileStore()
        self.library_layout_store = LibraryLayoutStore()
        try:
            self.library_layouts = self.library_layout_store.load_all()
        except (OSError, LibraryLayoutError) as error:
            LOGGER.warning("Could not load saved library layout: %s", error)
            self.library_layouts = {view: {"order": list(layout["order"]), "visible": list(layout["visible"]), "widths": dict(layout["widths"])} for view, layout in DEFAULT_LIBRARY_LAYOUTS.items()}
        self.release_preference_store = ReleasePreferenceStore()
        self.anime_release_preference_store = AnimeReleasePreferenceStore()
        self.release_scoring_store = ReleaseScoringSettingsStore()
        self.release_rule_store = ReleaseRuleStore()
        self.rss_feed_store = RSSFeedStore()
        self.qbittorrent_settings_store = QBittorrentSettingsStore()
        self.release_results = ()
        self._release_refresh_running = False
        self.search_history_store = SearchHistoryStore()
        self._scan_cancel_event = None
        self._scan_generation = 0
        self.current_filter = "all"
        self.library_sort_mode = "title"
        self._undo_entry: AnimeEntry | None = None
        self._undo_toast = None
        undo_action = Gio.SimpleAction.new("undo-delete", None)
        undo_action.connect("activate", self._undo_last_removal)
        self.add_action(undo_action)
        for name, callback in [
            ("add-anime", lambda: self._show_add_dialog(None)),
            ("season-discovery", self._show_season_discovery),
            ("focus-search", lambda: self.search.grab_focus()),
            ("quit", lambda: self.get_application().quit()),
            ("statistics", self._show_statistics_dialog),
            ("watch-history", self._show_watch_history_dialog),
            ("manage-webhooks", self._show_webhook_manager),
            ("notifications", self._show_notification_center),
            ("notification-preferences", self._show_notification_preferences),
            ("player-detection", self._show_player_detection_preferences),
            ("network-settings", self._show_network_settings_dialog),
            ("profiles", self._show_profiles_dialog),
            ("library-layout", self._show_library_layout_dialog),
            ("export-json", lambda: self._show_export_dialog("json")),
            ("export-csv", lambda: self._show_export_dialog("csv")),
            ("import-library", self._show_import_dialog),
            ("create-backup", self._show_backup_dialog),
            ("restore-backup", self._show_restore_backup_dialog),
            ("scan-folders", self._show_scan_folders_dialog),
            ("share-format", self._show_share_format_dialog),
            ("manage-external-links", self._show_external_links_manager),
            ("release-preferences", self._show_release_preferences_dialog),
            ("release-scoring", self._show_release_scoring_dialog),
            ("manage-release-feeds", self._show_release_feed_manager),
            ("manage-release-rules", self._show_release_rule_manager),
            ("configure-qbittorrent", self._show_qbittorrent_settings_dialog),
            ("download-queue", self._show_download_queue),
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
        primary_menu.append("Season Discovery", "win.season-discovery")
        primary_menu.append("Search Library", "win.focus-search")
        primary_menu.append("Library Statistics", "win.statistics")
        primary_menu.append("Watch History", "win.watch-history")
        primary_menu.append("Manage Webhooks", "win.manage-webhooks")
        primary_menu.append("Notifications", "win.notifications")
        primary_menu.append("Notification Preferences", "win.notification-preferences")
        primary_menu.append("Local Player Detection", "win.player-detection")
        primary_menu.append("Network Settings", "win.network-settings")
        primary_menu.append("Profiles & Portable Mode", "win.profiles")
        primary_menu.append("Customize Library Layout", "win.library-layout")
        primary_menu.append("Export Library (JSON)", "win.export-json")
        primary_menu.append("Export Library (CSV)", "win.export-csv")
        primary_menu.append("Import Library", "win.import-library")
        primary_menu.append("Create Full Backup", "win.create-backup")
        primary_menu.append("Restore Full Backup", "win.restore-backup")
        primary_menu.append("Scan Local Folders", "win.scan-folders")
        primary_menu.append("Share Format", "win.share-format")
        primary_menu.append("Manage External Links", "win.manage-external-links")
        primary_menu.append("Release Preferences", "win.release-preferences")
        primary_menu.append("Release Scoring Weights", "win.release-scoring")
        primary_menu.append("Manage Release Feeds", "win.manage-release-feeds")
        primary_menu.append("Manage Smart Release Rules", "win.manage-release-rules")
        primary_menu.append("Download Queue", "win.download-queue")
        primary_menu.append("Configure qBittorrent", "win.configure-qbittorrent")
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

        self.bulk_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.bulk_bar.set_margin_bottom(10)
        self.bulk_bar.set_visible(False)
        self.bulk_count_label = Gtk.Label(label="0 selected")
        self.bulk_bar.append(self.bulk_count_label)
        self.bulk_status_dropdown = Gtk.DropDown(model=Gtk.StringList.new(
            ["Planning", "Watching", "Completed", "Paused", "Dropped"]
        ))
        self.bulk_bar.append(self.bulk_status_dropdown)
        bulk_status_button = Gtk.Button(label="Set Status")
        bulk_status_button.connect("clicked", self._apply_bulk_status)
        self.bulk_bar.append(bulk_status_button)
        self.bulk_progress_entry = Gtk.Entry()
        self.bulk_progress_entry.set_placeholder_text("Watched episodes")
        self.bulk_progress_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self.bulk_progress_entry.set_width_chars(8)
        self.bulk_bar.append(self.bulk_progress_entry)
        bulk_progress_button = Gtk.Button(label="Set Progress")
        bulk_progress_button.connect("clicked", self._apply_bulk_progress)
        self.bulk_bar.append(bulk_progress_button)
        bulk_delete_button = Gtk.Button(label="Delete")
        bulk_delete_button.add_css_class("destructive-action")
        bulk_delete_button.connect("clicked", self._confirm_bulk_delete)
        self.bulk_bar.append(bulk_delete_button)
        clear_selection_button = Gtk.Button(label="Clear")
        clear_selection_button.connect("clicked", lambda _button: self._clear_bulk_selection())
        self.bulk_bar.append(clear_selection_button)
        body.append(self.bulk_bar)

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
        sort_label = Gtk.Label(label="Sort:")
        sort_label.add_css_class("dim-label")
        toolbar.append(sort_label)
        self.library_sort_dropdown = Gtk.DropDown.new_from_strings(
            ["Title", "Progress", "Recently Updated", "Next Airing"]
        )
        self.library_sort_dropdown.set_selected(0)
        self.library_sort_dropdown.connect("notify::selected", self._on_library_sort_changed)
        toolbar.append(self.library_sort_dropdown)
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

        releases_button = Gtk.Button(label="Releases")
        releases_button.set_tooltip_text("Show monitored anime releases")
        releases_button.connect("clicked", lambda _button: self._show_release_results())
        toolbar.append(releases_button)

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

        self.release_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        release_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.release_search_entry = Gtk.SearchEntry()
        self.release_search_entry.set_placeholder_text("Filter releases…")
        self.release_search_entry.set_hexpand(True)
        self.release_search_entry.connect(
            "search-changed", lambda _entry: self._render_release_results()
        )
        release_controls.append(self.release_search_entry)
        self.release_sort_dropdown = Gtk.DropDown.new_from_strings(
            ["Best match", "Newest", "Most seeders", "Title"]
        )
        self.release_sort_dropdown.set_tooltip_text("Sort release results")
        self.release_sort_dropdown.connect(
            "notify::selected", lambda *_args: self._render_release_results()
        )
        release_controls.append(self.release_sort_dropdown)
        self.release_eligible_only_check = Gtk.CheckButton(label="Eligible only")
        self.release_eligible_only_check.set_tooltip_text(
            "Hide releases rejected by preferences or below the minimum score."
        )
        self.release_eligible_only_check.connect(
            "toggled", lambda _button: self._render_release_results()
        )
        release_controls.append(self.release_eligible_only_check)
        release_spacer = Gtk.Box()
        release_spacer.set_hexpand(True)
        release_controls.append(release_spacer)
        refresh_releases_button = Gtk.Button(label="Refresh")
        refresh_releases_button.connect(
            "clicked", lambda _button: self._refresh_release_feeds()
        )
        release_controls.append(refresh_releases_button)
        manage_releases_button = Gtk.Button(label="Manage Feeds")
        manage_releases_button.connect(
            "clicked", lambda _button: self._show_release_feed_manager()
        )
        release_controls.append(manage_releases_button)
        manage_rules_button = Gtk.Button(label="Manage Rules")
        manage_rules_button.connect(
            "clicked", lambda _button: self._show_release_rule_manager()
        )
        release_controls.append(manage_rules_button)
        configure_qbittorrent_button = Gtk.Button(label="qBittorrent")
        configure_qbittorrent_button.set_tooltip_text("Configure your qBittorrent WebUI connection")
        configure_qbittorrent_button.connect(
            "clicked", lambda _button: self._show_qbittorrent_settings_dialog()
        )
        release_controls.append(configure_qbittorrent_button)
        queue_button = Gtk.Button(label="Download Queue")
        queue_button.connect("clicked", lambda _button: self._show_download_queue())
        release_controls.append(queue_button)
        self.release_page.append(release_controls)
        self.release_list_box = Gtk.ListBox()
        self.release_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.release_list_box.add_css_class("boxed-list")
        self.release_scroll = Gtk.ScrolledWindow()
        self.release_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.release_scroll.set_child(self.release_list_box)
        self.release_page.append(self.release_scroll)
        self.stack.add_named(self.release_page, "releases")

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
        self._refresh_airing_schedule()
        GLib.timeout_add_seconds(60, self._update_airing_countdowns)
        GLib.timeout_add_seconds(1800, self._periodic_airing_refresh)
        if self.player_detection_settings.enabled:
            self._start_player_detection()
        self._refresh_release_feeds()
        GLib.timeout_add_seconds(1800, self._periodic_release_refresh)


    def _show_release_scoring_dialog(self):
        try:
            saved = self.release_scoring_store.load()
            saved_minimum = self.release_scoring_store.load_minimum_score()
        except (OSError, ValueError) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not load release-scoring weights: {error}")
            )
            saved = dict(DEFAULT_WEIGHTS)
            saved_minimum = DEFAULT_MINIMUM_SCORE

        dialog = Adw.AlertDialog(
            heading="Release Scoring Weights",
            body=(
                "Adjust how much each available release attribute contributes to its "
                "quality score. Missing metadata is omitted from the weighted average."
            ),
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        editors = {}
        for row, (name, default) in enumerate(DEFAULT_WEIGHTS.items()):
            label = Gtk.Label(label=name.replace("_", " ").title(), xalign=0)
            weight = Gtk.SpinButton.new_with_range(0, 100, 1)
            weight.set_value(saved.get(name, default) * 100)
            weight.set_numeric(True)
            suffix = Gtk.Label(label="%")
            grid.attach(label, 0, row, 1, 1)
            grid.attach(weight, 1, row, 1, 1)
            grid.attach(suffix, 2, row, 1, 1)
            editors[name] = weight
        content.append(grid)

        cutoff_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        cutoff_label = Gtk.Label(label="Minimum acceptable score", xalign=0)
        cutoff_label.set_hexpand(True)
        cutoff_row.append(cutoff_label)
        minimum_score = Gtk.SpinButton.new_with_range(0, 100, 1)
        minimum_score.set_value(saved_minimum)
        minimum_score.set_numeric(True)
        minimum_score.set_tooltip_text(
            "Releases below this score are marked ineligible in the release monitor."
        )
        cutoff_row.append(minimum_score)
        cutoff_row.append(Gtk.Label(label="/ 100"))
        content.append(cutoff_row)

        help_label = Gtk.Label(
            label="Weights are relative: they do not need to add up to 100%.",
            xalign=0,
            wrap=True,
        )
        help_label.add_css_class("dim-label")
        content.append(help_label)

        save_button = Gtk.Button(label="Save Weights")
        save_button.add_css_class("suggested-action")
        content.append(save_button)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)

        def save_weights(_button):
            weights = {
                name: editor.get_value_as_int() / 100
                for name, editor in editors.items()
            }
            try:
                self.release_scoring_store.save(
                    weights, minimum_score=minimum_score.get_value()
                )
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not save scoring weights: {error}")
                )
                return
            self.toast_overlay.add_toast(Adw.Toast.new("Release scoring weights saved."))
            self._refresh_release_feeds()

        save_button.connect("clicked", save_weights)

    def _show_release_preferences_dialog(self):
        try:
            saved = self.release_preference_store.load()
        except (OSError, ReleasePreferenceError) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not load release preferences: {error}")
            )
            saved = ()

        by_attribute = {item.attribute: item for item in saved}
        dialog = Adw.AlertDialog(
            heading="Release Preferences",
            body=(
                "Set preferred and rejected release attributes. Preferred values "
                "improve ranking; rejected values exclude a release from eligible results."
            ),
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        help_label = Gtk.Label(
            label="Enter comma-separated values. Lower priority numbers are evaluated first.",
            xalign=0,
            wrap=True,
        )
        help_label.add_css_class("dim-label")
        content.append(help_label)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        for column, heading in enumerate(("Attribute", "Preferred", "Rejected", "Priority")):
            label = Gtk.Label(label=heading, xalign=0)
            label.add_css_class("heading")
            grid.attach(label, column, 0, 1, 1)

        editors = {}
        for row, attribute in enumerate(PREFERENCE_ATTRIBUTES, start=1):
            preference = by_attribute.get(attribute)
            name = Gtk.Label(label=attribute.replace("_", " ").title(), xalign=0)
            preferred = Gtk.Entry()
            preferred.set_placeholder_text("e.g. 1080p, 2160p")
            preferred.set_hexpand(True)
            rejected = Gtk.Entry()
            rejected.set_placeholder_text("e.g. 480p")
            rejected.set_hexpand(True)
            priority = Gtk.SpinButton.new_with_range(0, 100, 1)
            priority.set_value(preference.priority if preference else row - 1)
            preferred.set_text(", ".join(preference.preferred) if preference else "")
            rejected.set_text(", ".join(preference.rejected) if preference else "")
            grid.attach(name, 0, row, 1, 1)
            grid.attach(preferred, 1, row, 1, 1)
            grid.attach(rejected, 2, row, 1, 1)
            grid.attach(priority, 3, row, 1, 1)
            editors[attribute] = (preferred, rejected, priority)

        grid_scroll = Gtk.ScrolledWindow()
        grid_scroll.set_min_content_height(230)
        grid_scroll.set_max_content_height(340)
        grid_scroll.set_child(grid)
        content.append(grid_scroll)

        decision_preview = Gtk.Label(xalign=0, wrap=True)
        decision_preview.add_css_class("caption")
        content.append(decision_preview)

        def current_payload():
            payload = {}
            for attribute, (preferred, rejected, priority) in editors.items():
                payload[attribute] = {
                    "preferred": [
                        value.strip() for value in preferred.get_text().split(",")
                        if value.strip()
                    ],
                    "rejected": [
                        value.strip() for value in rejected.get_text().split(",")
                        if value.strip()
                    ],
                    "priority": priority.get_value_as_int(),
                }
            return payload

        def update_decision_preview(*_args):
            try:
                decision = evaluate_release_preferences(
                    {
                        "resolution": "1080p",
                        "source": "WEB-DL",
                        "audio": "AAC",
                        "subtitles": "English",
                        "release_group": "ExampleGroup",
                    },
                    current_payload(),
                )
            except ReleasePreferenceError as error:
                decision_preview.set_label(f"Example decision unavailable: {error}")
                decision_preview.add_css_class("error")
                return
            decision_preview.remove_css_class("error")
            state = "Eligible" if decision.accepted else "Rejected"
            details = "; ".join(decision.explanations) or "No preference matched."
            decision_preview.set_label(f"Example release: {state}. {details}")

        for preferred, rejected, priority in editors.values():
            preferred.connect("changed", update_decision_preview)
            rejected.connect("changed", update_decision_preview)
            priority.connect("value-changed", update_decision_preview)

        save_button = Gtk.Button(label="Save Preferences")
        save_button.add_css_class("suggested-action")
        content.append(save_button)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)

        def save_preferences(_button):
            payload = current_payload()
            try:
                self.release_preference_store.save(payload)
            except (OSError, ReleasePreferenceError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not save release preferences: {error}")
                )
                return
            self.toast_overlay.add_toast(Adw.Toast.new("Release preferences saved."))
            self._refresh_release_feeds()

        save_button.connect("clicked", save_preferences)
        update_decision_preview()

    def _show_external_links(self, entry: AnimeEntry, anchor):
        try:
            custom_links = self.external_link_store.list_templates()
            links = links_for_entry(entry, custom_links)
        except (OSError, ExternalLinkError) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not load external links: {error}")
            )
            return
        if not links:
            self.toast_overlay.add_toast(Adw.Toast.new("No external links are available."))
            return
        popover = Gtk.Popover()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        content.set_margin_start(8)
        content.set_margin_end(8)
        for label, url in links:
            link = Gtk.LinkButton.new_with_label(url, label)
            link.set_halign(Gtk.Align.FILL)
            content.append(link)
        popover.set_child(content)
        popover.set_parent(anchor)
        popover.connect("closed", lambda current: current.unparent())
        popover.popup()

    def _show_external_links_manager(self):
        try:
            templates = list(self.external_link_store.list_templates())
        except (OSError, ExternalLinkError) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not load external links: {error}")
            )
            templates = []

        dialog = Adw.AlertDialog(
            heading="Manage External Links",
            body=(
                "Built-in AniList, MyAnimeList, and Kitsu links are available automatically. "
                "Add optional HTTP(S) URL templates using {title}, {provider}, or {provider_id}."
            ),
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        link_list = Gtk.ListBox()
        link_list.set_selection_mode(Gtk.SelectionMode.NONE)
        link_list.add_css_class("boxed-list")
        content.append(link_list)

        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Link name (e.g. Official site)")
        content.append(name_entry)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://example.com/anime/{provider_id}")
        url_entry.set_input_purpose(Gtk.InputPurpose.URL)
        content.append(url_entry)
        add_button = Gtk.Button(label="Save Custom Link")
        editing_index = [None]
        add_button.add_css_class("suggested-action")
        content.append(add_button)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)

        def refresh():
            child = link_list.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                link_list.remove(child)
                child = following
            for index, item in enumerate(templates):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                label = Gtk.Label(label=f"{item['name']} — {item['url']}", xalign=0)
                label.set_ellipsize(3)
                label.set_hexpand(True)
                row.append(label)
                edit = Gtk.Button.new_from_icon_name("document-edit-symbolic")
                edit.set_tooltip_text(f"Edit {item['name']}")
                edit.connect("clicked", lambda _button, position=index: edit_template(position))
                row.append(edit)
                remove = Gtk.Button.new_from_icon_name("user-trash-symbolic")
                remove.set_tooltip_text(f"Remove {item['name']}")
                remove.connect("clicked", lambda _button, position=index: remove_template(position))
                row.append(remove)
                link_list.append(row)

        def edit_template(index):
            if index < 0 or index >= len(templates):
                return
            item = templates[index]
            name_entry.set_text(item["name"])
            url_entry.set_text(item["url"])
            editing_index[0] = index
            add_button.set_label("Update Custom Link")

        def remove_template(index):
            if index < 0 or index >= len(templates):
                return
            templates.pop(index)
            try:
                self.external_link_store.save_templates(templates)
            except (OSError, ExternalLinkError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save links: {error}"))
                return
            refresh()
            self.toast_overlay.add_toast(Adw.Toast.new("Custom link removed."))

        def add_template(_button):
            item = {"name": name_entry.get_text().strip(), "url": url_entry.get_text().strip()}
            candidate = list(templates)
            if editing_index[0] is None:
                candidate.append(item)
            else:
                candidate[editing_index[0]] = item
            try:
                self.external_link_store.save_templates(candidate)
            except (OSError, ExternalLinkError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save link: {error}"))
                return
            templates[:] = candidate
            editing_index[0] = None
            add_button.set_label("Save Custom Link")
            name_entry.set_text("")
            url_entry.set_text("")
            refresh()
            self.toast_overlay.add_toast(Adw.Toast.new("Custom link saved."))

        add_button.connect("clicked", add_template)
        refresh()

    def _show_library_layout_dialog(self):
        """Edit and persist the list/grid layout preferences."""
        try:
            saved = self.library_layout_store.load_all()
        except (OSError, LibraryLayoutError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Could not load library layout: {error}"))
            return
        dialog = Adw.AlertDialog(
            heading="Customize Library Layout",
            body="Choose visible metadata fields, their order, and widths. The title remains visible.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(300)
        scroll.set_max_content_height(480)
        sections = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll.set_child(sections)
        content.append(scroll)
        controls = {}
        reset_buttons = {}
        for view, heading in (("list", "List view"), ("grid", "Grid view")):
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            section_title = Gtk.Label(label=heading, xalign=0)
            section_title.add_css_class("heading")
            section.append(section_title)
            controls[view] = {}
            for column in saved[view]["order"]:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                visible = Gtk.CheckButton(label=column.title())
                visible.set_active(column in saved[view]["visible"])
                if column == "title":
                    visible.set_active(True)
                    visible.set_sensitive(False)
                row.append(visible)
                row.append(Gtk.Label(label="Order"))
                order = Gtk.SpinButton.new_with_range(1, len(saved[view]["order"]), 1)
                order.set_value(saved[view]["order"].index(column) + 1)
                order.set_width_chars(3)
                if column == "title":
                    order.set_sensitive(False)
                row.append(order)
                controls[view][column] = {"visible": visible, "order": order}
                if view == "list":
                    row.append(Gtk.Label(label="Width"))
                    width = Gtk.SpinButton.new_with_range(80, 500, 10)
                    width.set_value(saved[view]["widths"][column])
                    width.set_width_chars(4)
                    row.append(width)
                    controls[view][column]["width"] = width
                section.append(row)
            if view == "grid":
                width_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                width_row.append(Gtk.Label(label="Card width (px)"))
                card_width = Gtk.SpinButton.new_with_range(160, 360, 10)
                card_width.set_value(saved[view]["widths"]["card_width"])
                width_row.append(card_width)
                controls[view]["card_width"] = card_width
                section.append(width_row)
            reset_button = Gtk.Button(label=f"Reset {view.title()} Defaults")
            reset_button.set_halign(Gtk.Align.START)
            reset_buttons[view] = reset_button
            section.append(reset_button)
            sections.append(section)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_button = Gtk.Button(label="Save Layout")
        save_button.add_css_class("suggested-action")
        actions.append(save_button)
        content.append(actions)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)

        def collect(view):
            layout = {
                "order": sorted(saved[view]["order"], key=lambda column: controls[view][column]["order"].get_value_as_int()),
                "visible": [column for column in saved[view]["order"] if controls[view][column]["visible"].get_active()],
                "widths": dict(saved[view]["widths"]),
            }
            if view == "list":
                layout["widths"] = {column: controls[view][column]["width"].get_value_as_int() for column in saved[view]["order"]}
            else:
                layout["widths"]["card_width"] = controls[view]["card_width"].get_value_as_int()
            return layout

        def save_layout(_button):
            try:
                candidate = {view: collect(view) for view in ("list", "grid")}
                self.library_layout_store.save("list", candidate["list"])
                self.library_layout_store.save("grid", candidate["grid"])
                self.library_layouts = self.library_layout_store.load_all()
            except (OSError, LibraryLayoutError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save library layout: {error}"))
                return
            self._render_library()
            self.toast_overlay.add_toast(Adw.Toast.new("Library layout saved."))

        def reset_layout(view):
            try:
                self.library_layout_store.reset(view)
                self.library_layouts = self.library_layout_store.load_all()
            except (OSError, LibraryLayoutError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not reset {view} layout: {error}"))
                return
            self._render_library()
            dialog.close()
            self.toast_overlay.add_toast(Adw.Toast.new(f"{view.title()} layout restored to defaults."))

        save_button.connect("clicked", save_layout)
        for view, reset_button in reset_buttons.items():
            reset_button.connect("clicked", lambda _button, current_view=view: reset_layout(current_view))

    def _show_share_format_dialog(self):
        try:
            saved_template = self.share_template_store.load()
        except (OSError, ShareTemplateError) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not load share format: {error}")
            )
            saved_template = DEFAULT_SHARE_TEMPLATE

        dialog = Adw.AlertDialog(
            heading="Share Message Format",
            body="Customize the text used by future sharing actions and preview it with a library entry.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        help_text = Gtk.Label(
            label=(
                "Variables: {title}, {episode}, {total_episodes}, {progress}, "
                "{status}, {timestamp}. Use [[if field]]…[[/if]] for optional "
                "sections, or [[upper:title]], [[lower:status]], [[title:status]], "
                "and [[default:total_episodes:TBA]] for basic formatting."
            ),
            xalign=0,
            wrap=True,
        )
        help_text.add_css_class("dim-label")
        content.append(help_text)

        editor = Gtk.TextView()
        editor.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        editor.get_buffer().set_text(saved_template)
        editor_scroll = Gtk.ScrolledWindow()
        editor_scroll.set_min_content_height(130)
        editor_scroll.set_max_content_height(220)
        editor_scroll.set_child(editor)
        content.append(editor_scroll)

        preview_title = Gtk.Label(label="Preview", xalign=0)
        preview_title.add_css_class("heading")
        content.append(preview_title)
        preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
        preview.add_css_class("card")
        preview.set_margin_top(6)
        preview.set_margin_bottom(6)
        preview.set_margin_start(8)
        preview.set_margin_end(8)
        content.append(preview)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        reset_button = Gtk.Button(label="Restore Default")
        save_button = Gtk.Button(label="Save Format")
        save_button.add_css_class("suggested-action")
        actions.append(reset_button)
        actions.append(save_button)
        content.append(actions)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)

        sample_entry = (
            self.entries[0]
            if self.entries
            else AnimeEntry(
                title="Example Anime",
                episodes_total=12,
                episodes_watched=5,
                status=WatchStatus.WATCHING,
            )
        )

        def update_preview(_buffer=None):
            buffer = editor.get_buffer()
            start, end = buffer.get_bounds()
            template = buffer.get_text(start, end, True)
            try:
                rendered = render_share_template(
                    template, share_context_for_entry(sample_entry)
                )
            except ShareTemplateError as error:
                preview.set_label(f"Invalid template: {error}")
                preview.add_css_class("error")
                save_button.set_sensitive(False)
                return
            preview.remove_css_class("error")
            preview.set_label(rendered or "(empty output)")
            save_button.set_sensitive(True)

        def save_template(_button):
            buffer = editor.get_buffer()
            start, end = buffer.get_bounds()
            template = buffer.get_text(start, end, True)
            try:
                self.share_template_store.save(template)
            except (OSError, ShareTemplateError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not save share format: {error}")
                )
                return
            self.toast_overlay.add_toast(Adw.Toast.new("Share format saved."))

        def reset_template(_button):
            editor.get_buffer().set_text(DEFAULT_SHARE_TEMPLATE)

        editor.get_buffer().connect("changed", update_preview)
        save_button.connect("clicked", save_template)
        reset_button.connect("clicked", reset_template)
        update_preview()

    def _show_scan_folders_dialog(self):
        dialog = Adw.AlertDialog(
            heading="Local Anime Folders",
            body="Choose folders to scan for video files. Scans run in the background.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        folder_list = Gtk.ListBox()
        folder_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        folder_list.add_css_class("boxed-list")
        folder_scroll = Gtk.ScrolledWindow()
        folder_scroll.set_min_content_height(150)
        folder_scroll.set_max_content_height(260)
        folder_scroll.set_child(folder_list)
        content.append(folder_scroll)

        def refresh_folders():
            child = folder_list.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                folder_list.remove(child)
                child = following
            try:
                locations = self.scan_location_store.list_locations()
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not read scan folders: {error}")
                )
                return
            for location in locations:
                row = Gtk.ListBoxRow()
                label = Gtk.Label(label=str(location), xalign=0, wrap=True)
                label.set_margin_top(8)
                label.set_margin_bottom(8)
                label.set_margin_start(10)
                label.set_margin_end(10)
                row.set_child(label)
                folder_list.append(row)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_button = Gtk.Button(label="Add Folder")
        remove_button = Gtk.Button(label="Remove Selected")
        scan_button = Gtk.Button(label="Scan Now")
        scan_button.add_css_class("suggested-action")
        cancel_button = Gtk.Button(label="Cancel Scan")
        cancel_button.set_sensitive(False)
        actions.append(add_button)
        actions.append(remove_button)
        exclusions_button = Gtk.Button(label='Manage Exclusions')
        exclusions_button.connect('clicked', lambda _button: self._show_recognition_exclusions_dialog())
        actions.append(exclusions_button)
        actions.append(scan_button)
        actions.append(cancel_button)
        content.append(actions)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)
        refresh_folders()

        def add_folder(_button):
            chooser = Gtk.FileChooserNative.new(
                "Choose an anime folder",
                self,
                Gtk.FileChooserAction.SELECT_FOLDER,
                "Add Folder",
                "Cancel",
            )
            def folder_selected(current, response):
                if response == Gtk.ResponseType.ACCEPT:
                    self._scan_generation += 1
                    if self._scan_cancel_event is not None:
                        self._scan_cancel_event.set()
                self._on_scan_folder_selected(current, response, refresh_folders)

            chooser.connect("response", folder_selected)
            chooser.show()

        def remove_folder(_button):
            selected = folder_list.get_selected_row()
            if selected is None:
                self.toast_overlay.add_toast(
                    Adw.Toast.new("Select a folder to remove.")
                )
                return
            try:
                locations = self.scan_location_store.list_locations()
                index = selected.get_index()
                if index < 0 or index >= len(locations):
                    return
                removed = self.scan_location_store.remove_location(locations[index])
                if removed:
                    self._scan_generation += 1
                    if self._scan_cancel_event is not None:
                        self._scan_cancel_event.set()
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not remove scan folder: {error}")
                )
                return
            refresh_folders()

        add_button.connect("clicked", add_folder)
        remove_button.connect("clicked", remove_folder)
        scan_button.connect(
            "clicked",
            lambda _button: self._start_configured_library_scan(
                scan_button, cancel_button
            ),
        )
        cancel_button.connect("clicked", self._cancel_configured_library_scan)

    def _show_recognition_exclusions_dialog(self):
        try:
            rules = list(self.recognition_exclusion_store.list_rules())
        except (OSError, RecognitionExclusionError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new('Could not load exclusions: ' + str(error)))
            rules = []
        dialog = Adw.AlertDialog(
            heading='Recognition Exclusions',
            body='Exclude folders, filename patterns, anime titles, or release groups. Use * and ? wildcards for text patterns.',
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        listing = Gtk.ListBox()
        listing.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listing.add_css_class('boxed-list')
        content.append(listing)
        kind = Gtk.DropDown.new_from_strings(['Folder path', 'Filename pattern', 'Anime title', 'Release group'])
        content.append(kind)
        pattern = Gtk.Entry()
        pattern.set_placeholder_text('/absolute/folder or *pattern*')
        content.append(pattern)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add = Gtk.Button(label='Add Exclusion')
        edit = Gtk.Button(label='Edit Selected')
        remove = Gtk.Button(label='Remove Selected')
        actions.append(add)
        actions.append(edit)
        actions.append(remove)
        editing_index = [None]
        content.append(actions)
        dialog.set_extra_child(content)
        dialog.add_response('close', 'Close')
        dialog.set_default_response('close')
        dialog.present(self)
        kinds = ('folder', 'filename', 'title', 'release_group')
        def refresh():
            child = listing.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                listing.remove(child)
                child = following
            for item in rules:
                row = Gtk.ListBoxRow()
                row.set_child(Gtk.Label(label=item['kind'].replace('_', ' ').title() + ': ' + item['pattern'], xalign=0))
                listing.append(row)
        def add_rule(_button):
            selected = kind.get_selected()
            if selected >= len(kinds):
                return
            item = {'kind': kinds[selected], 'pattern': pattern.get_text().strip()}
            updated = list(rules)
            if editing_index[0] is None:
                updated.append(item)
            else:
                updated[editing_index[0]] = item
            try:
                self.recognition_exclusion_store.save_rules(updated)
            except (OSError, RecognitionExclusionError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new('Could not save exclusion: ' + str(error)))
                return
            rules[:] = updated
            editing_index[0] = None
            add.set_label('Add Exclusion')
            pattern.set_text('')
            refresh()
            self.toast_overlay.add_toast(Adw.Toast.new('Recognition exclusion saved.'))
        def edit_rule(_button):
            selected = listing.get_selected_row()
            if selected is None:
                self.toast_overlay.add_toast(Adw.Toast.new('Select an exclusion to edit.'))
                return
            index = selected.get_index()
            if index < 0 or index >= len(rules):
                return
            item = rules[index]
            kind.set_selected(kinds.index(item['kind']))
            pattern.set_text(item['pattern'])
            editing_index[0] = index
            add.set_label('Update Exclusion')
        def remove_rule(_button):
            selected = listing.get_selected_row()
            if selected is None:
                self.toast_overlay.add_toast(Adw.Toast.new('Select an exclusion to remove.'))
                return
            index = selected.get_index()
            updated = list(rules)
            updated.pop(index)
            try:
                self.recognition_exclusion_store.save_rules(updated)
            except (OSError, RecognitionExclusionError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new('Could not save exclusions: ' + str(error)))
                return
            rules[:] = updated
            if editing_index[0] == index:
                editing_index[0] = None
                add.set_label('Add Exclusion')
                pattern.set_text('')
            elif editing_index[0] is not None and editing_index[0] > index:
                editing_index[0] -= 1
            refresh()
        add.connect('clicked', add_rule)
        edit.connect('clicked', edit_rule)
        remove.connect('clicked', remove_rule)
        refresh()
    def _on_scan_folder_selected(self, chooser, response, refresh_folders):
        if response != Gtk.ResponseType.ACCEPT:
            chooser.destroy()
            return
        selected = chooser.get_file()
        path = selected.get_path() if selected is not None else None
        chooser.destroy()
        if not path:
            self.toast_overlay.add_toast(
                Adw.Toast.new("Choose a local folder to add.")
            )
            return
        try:
            added = self.scan_location_store.add_location(path)
        except (OSError, ValueError) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not add scan folder: {error}")
            )
            return
        refresh_folders()
        self.toast_overlay.add_toast(
            Adw.Toast.new("Folder added." if added else "Folder is already configured.")
        )

    def _start_configured_library_scan(self, scan_button, cancel_button):
        if self._scan_cancel_event is not None:
            return
        try:
            locations = self.scan_location_store.list_locations()
        except (OSError, ValueError) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not read scan folders: {error}")
            )
            return
        if not locations:
            self.toast_overlay.add_toast(
                Adw.Toast.new("Add at least one local folder before scanning.")
            )
            return

        try:
            exclusions = self.recognition_exclusion_store.list_rules()
        except (OSError, RecognitionExclusionError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Could not read exclusions: {error}"))
            return

        event = threading.Event()
        self._scan_cancel_event = event
        generation = self._scan_generation
        scan_button.set_sensitive(False)
        scan_button.set_label("Scanning…")
        cancel_button.set_sensitive(True)
        entries = tuple(self.entries)
        candidates = [
            {"id": int(entry.provider_id), "title": entry.title}
            for entry in entries
            if entry.provider == "anilist"
            and entry.provider_id
            and str(entry.provider_id).isdigit()
        ]

        def worker():
            result = None
            error = None
            try:
                watched_episodes = {}
                for entry in entries:
                    if entry.provider != "anilist" or not entry.provider_id:
                        continue
                    progress = (
                        self.storage.list_episode_progress(entry.storage_id)
                        if entry.storage_id is not None else {}
                    )
                    watched_episodes[str(entry.provider_id)] = (
                        {number for number, watched in progress.items() if watched}
                        if progress else set(range(1, entry.episodes_watched + 1))
                    )
                result = scan_configured_library(
                    self.scan_location_store,
                    candidates,
                    entries,
                    exclusions=exclusions,
                    watched_episodes=watched_episodes,
                    configured_locations=locations,
                    is_cancelled=event.is_set,
                )
            except Exception as caught:
                LOGGER.exception("Local library scan failed")
                error = str(caught)
            GLib.idle_add(
                self._finish_configured_library_scan,
                result,
                error,
                event,
                scan_button,
                cancel_button,
                generation,
                entries,
            )

        threading.Thread(target=worker, daemon=True).start()

    def _cancel_configured_library_scan(self, _button):
        if self._scan_cancel_event is not None:
            self._scan_cancel_event.set()
            self.toast_overlay.add_toast(Adw.Toast.new("Cancelling local scan…"))

    def _finish_configured_library_scan(
        self, result, error, event, scan_button, cancel_button, generation, entries
    ):
        if self._scan_cancel_event is event:
            self._scan_cancel_event = None
        scan_button.set_sensitive(True)
        scan_button.set_label("Scan Now")
        cancel_button.set_sensitive(False)
        if generation != self._scan_generation or tuple(self.entries) != entries:
            self.toast_overlay.add_toast(
                Adw.Toast.new("Scan results discarded because folders or the library changed. Scan again.")
            )
            return GLib.SOURCE_REMOVE
        if error is not None:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Local scan failed: {error}"))
            return GLib.SOURCE_REMOVE
        if result is None:
            return GLib.SOURCE_REMOVE

        def format_size(size_bytes):
            value = float(size_bytes)
            for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
                if value < 1024 or unit == "TiB":
                    return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
                value /= 1024
            return f"{value:.1f} TiB"

        lines = [
            f"Scanned {len(result.matches)} video path(s) across "
            f"{len(result.locations)} configured folder(s)."
        ]
        if event.is_set():
            lines.append("The scan was cancelled; the results below may be partial.")
        if result.size_complete:
            lines.append(
                f"Total video size: {format_size(result.total_size_bytes)} "
                "(distinct files; hard links counted once by inode)."
            )
        elif result.total_size_bytes:
            lines.append(
                f"Known video size: at least {format_size(result.total_size_bytes)} "
                "(partial scan; some files or roots were unavailable)."
            )
        else:
            lines.append("Total video size is unavailable because the scan was incomplete.")

        if result.unavailable_locations:
            lines.append("\nUnavailable or partially unreadable scan roots:")
            lines.extend(str(path) for path in result.unavailable_locations)
            lines.append(
                "Missing-episode and next-unwatched results are withheld where an "
                "unavailable root could hide files."
            )
        if not result.inventory:
            lines.append("No AniList-backed library entries are available to summarize.")
        excluded = [item for item in result.matches if item.excluded_reason]
        if excluded:
            lines.append(f"\\nExcluded files ({len(excluded)}):")
            lines.extend(f"{item.path.name}: {item.excluded_reason}" for item in excluded)
        ambiguous = [
            item for item in result.matches
            if item.excluded_reason is None and item.result.status == "ambiguous"
        ]
        unparsed = [
            item for item in result.matches
            if item.excluded_reason is None and item.result.status == "unparsed"
        ]
        unmatched = [
            item for item in result.matches
            if item.excluded_reason is None and item.result.status == "no_match"
        ]
        for label, items in (
            ("Ambiguous matches", ambiguous),
            ("Unparsed or unknown-episode paths", unparsed),
            ("Unmatched paths", unmatched),
        ):
            if items:
                names = [item.path.name for item in items[:8]]
                if len(items) > 8:
                    names.append(f"and {len(items) - 8} more")
                lines.append(f"\\n{label} ({len(items)}; not assigned to episode totals):")
                lines.extend(names)
        if ambiguous or unparsed or unmatched:
            lines.append(
                "Missing-episode counts use confidently matched files only; "
                "unclassified paths may contain episodes that could not be identified."
            )

        folder_actions = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6
        )
        for item in result.inventory:
            available = ", ".join(map(str, item.available_episodes)) or "none"
            if item.missing_complete:
                missing = ", ".join(map(str, item.missing_episodes)) or "none"
            else:
                missing = "unknown (incomplete scan or episode numbering/total)"
            next_episode = (
                str(item.next_episode) if item.next_episode is not None else "unknown"
            )
            next_episode_label = (
                "Next expected episode"
                if item.entry.episodes_total is None
                else "Next missing episode"
            )
            if item.next_unwatched_episode is not None:
                next_unwatched = str(item.next_unwatched_episode)
            elif not result.scan_complete:
                next_unwatched = "unknown (scan incomplete)"
            elif item.seasoned_episodes:
                next_unwatched = "unknown (season numbering is not comparable)"
            else:
                next_unwatched = "none found in scanned files"
            if item.size_complete:
                size = format_size(item.size_bytes)
            elif item.size_bytes:
                size = f"at least {format_size(item.size_bytes)} (partial)"
            else:
                size = "unavailable"
            source = (
                str(item.source_paths[0])
                if item.source_paths else "no confidently matched file path"
            )
            if len(item.source_paths) > 1:
                source += f" (+{len(item.source_paths) - 1} more)"
            lines.append(
                f"\n{item.entry.title}\n"
                f"Available: {available}\nMissing: {missing}\n"
                f"Next missing episode: {next_episode}\n"
                f"Next available unwatched: {next_unwatched}\n"
                f"Local size: {size}\nSource: {source}"
            )
            if item.seasoned_episodes:
                seasons = "; ".join(
                    f"Season {season}: {', '.join(map(str, episodes))}"
                    for season, episodes in item.seasoned_episodes
                )
                lines.append(f"Season-tagged files: {seasons}")
            if item.source_paths:
                button = Gtk.Button(label=f"Open {item.entry.title} folder")
                button.set_halign(Gtk.Align.START)
                button.connect(
                    "clicked",
                    lambda _button, folder=item.source_paths[0].parent:
                        self._open_local_folder(folder),
                )
                folder_actions.append(button)

        dialog = Adw.AlertDialog(
            heading="Local Scan Results",
            body="\n".join(lines),
        )
        if folder_actions.get_first_child() is not None:
            folder_scroll = Gtk.ScrolledWindow()
            folder_scroll.set_min_content_height(80)
            folder_scroll.set_max_content_height(180)
            folder_scroll.set_child(folder_actions)
            dialog.set_extra_child(folder_scroll)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)
        return GLib.SOURCE_REMOVE

    def _open_local_folder(self, folder):
        try:
            resolved = Path(folder).resolve(strict=True)
            if not resolved.is_dir():
                raise ValueError("The source folder is no longer available.")
            if not Gio.AppInfo.launch_default_for_uri(resolved.as_uri(), None):
                raise OSError("No file manager is available for this folder.")
        except (OSError, RuntimeError, ValueError, GLib.Error) as error:
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Could not open local folder: {error}")
            )

    def _show_backup_dialog(self):
        chooser = Gtk.FileChooserNative.new(
            "Create Aniyori backup",
            self,
            Gtk.FileChooserAction.SAVE,
            "Create Backup",
            "Cancel",
        )
        chooser.set_current_name("aniyori-backup.zip")
        chooser.connect("response", self._on_backup_file_chosen)
        chooser.show()

    def _on_backup_file_chosen(self, chooser, response):
        if response != Gtk.ResponseType.ACCEPT:
            chooser.destroy()
            return
        selected_file = chooser.get_file()
        path = selected_file.get_path() if selected_file is not None else None
        chooser.destroy()
        if not path:
            self.toast_overlay.add_toast(Adw.Toast.new("Choose a local backup destination."))
            return
        try:
            create_backup(self.storage.path, default_config_dir(), path)
        except (BackupError, OSError, sqlite3.Error) as error:
            LOGGER.exception("Could not create full Aniyori backup")
            self._record_notification("backup", "error", "Backup failed", str(error), "backup-failed:" + str(error))
            self.toast_overlay.add_toast(Adw.Toast.new(f"Backup failed: {error}"))
            return
        self._record_notification("backup", "info", "Backup created", Path(path).name)
        self.toast_overlay.add_toast(Adw.Toast.new("Full Aniyori backup created."))

    def _show_restore_backup_dialog(self):
        chooser = Gtk.FileChooserNative.new(
            "Restore Aniyori backup",
            self,
            Gtk.FileChooserAction.OPEN,
            "Choose Backup",
            "Cancel",
        )
        chooser.connect("response", self._on_restore_backup_file_chosen)
        chooser.show()

    def _on_restore_backup_file_chosen(self, chooser, response):
        if response != Gtk.ResponseType.ACCEPT:
            chooser.destroy()
            return
        selected_file = chooser.get_file()
        path = selected_file.get_path() if selected_file is not None else None
        chooser.destroy()
        if not path:
            self.toast_overlay.add_toast(Adw.Toast.new("Choose a local Aniyori backup file."))
            return
        dialog = Adw.AlertDialog(
            heading="Replace local Aniyori data?",
            body=(
                "Restoring this backup replaces the current library database and all "
                "Aniyori configuration files (including feeds, rules, and preferences). "
                "This cannot be undone. Create a backup of the current data first if needed."
            ),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("restore", "Restore Backup")
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_restore_backup_confirmed, path)

    def _on_restore_backup_confirmed(self, dialog, result, path: str):
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            LOGGER.warning("Could not finish backup restore confirmation", exc_info=True)
            return
        if response != "restore":
            return
        try:
            restore_backup(path, self.storage.path, default_config_dir())
            self.entries = self.storage.list_entries()
        except (BackupError, OSError, sqlite3.Error, ValueError) as error:
            LOGGER.exception("Could not restore Aniyori backup")
            self._record_notification("backup", "error", "Backup restore failed", str(error), "restore-failed:" + str(error))
            self.toast_overlay.add_toast(Adw.Toast.new(f"Restore failed: {error}"))
            return
        self._record_notification("backup", "info", "Backup restored", Path(path).name)
        self._selected_entry_ids.clear()
        self.release_results = ()
        self._render_library()
        self._refresh_airing_schedule()
        self.toast_overlay.add_toast(Adw.Toast.new("Aniyori backup restored successfully."))

    def _show_export_dialog(self, file_format: str):
        chooser = Gtk.FileChooserNative.new(
            f"Export library as {file_format.upper()}",
            self,
            Gtk.FileChooserAction.SAVE,
            "Export",
            "Cancel",
        )
        chooser.set_current_name(f"aniyori-library.{file_format}")
        chooser.connect("response", self._on_export_file_chosen, file_format)
        chooser.show()

    def _on_export_file_chosen(self, chooser, response, file_format: str):
        if response != Gtk.ResponseType.ACCEPT:
            chooser.destroy()
            return
        selected_file = chooser.get_file()
        path = selected_file.get_path() if selected_file is not None else None
        chooser.destroy()
        if not path:
            self.toast_overlay.add_toast(Adw.Toast.new("Choose a local file to export."))
            return
        try:
            content = (
                export_json(self.entries)
                if file_format == "json"
                else export_csv(self.entries)
            )
            Path(path).write_text(content, encoding="utf-8", newline="")
        except OSError as error:
            LOGGER.warning("Could not export library", exc_info=True)
            self.toast_overlay.add_toast(Adw.Toast.new(f"Export failed: {error}"))
            return
        self.toast_overlay.add_toast(Adw.Toast.new("Library exported successfully."))

    def _show_import_dialog(self):
        chooser = Gtk.FileChooserNative.new(
            "Import library",
            self,
            Gtk.FileChooserAction.OPEN,
            "Import",
            "Cancel",
        )
        chooser.connect("response", self._on_import_file_chosen)
        chooser.show()

    def _on_import_file_chosen(self, chooser, response):
        if response != Gtk.ResponseType.ACCEPT:
            chooser.destroy()
            return
        selected_file = chooser.get_file()
        path = selected_file.get_path() if selected_file is not None else None
        chooser.destroy()
        if not path:
            self.toast_overlay.add_toast(Adw.Toast.new("Choose a local JSON or CSV file."))
            return
        try:
            source = Path(path)
            content = source.read_text(encoding="utf-8")
            if source.suffix.casefold() == ".csv":
                entries = import_csv(content)
            elif source.suffix.casefold() == ".json":
                entries = import_json(content)
            else:
                raise ValueError("Choose a .json or .csv library export.")
        except (OSError, UnicodeDecodeError, ValueError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Import failed: {error}"))
            return

        dialog = Adw.AlertDialog(
            heading="Replace current library?",
            body=(
                f"Import {len(entries)} anime entries and replace all "
                "entries currently in your library? This cannot be undone."
            ),
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("replace", "Replace Library")
        dialog.set_response_appearance("replace", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_import_confirmed, entries)

    def _on_import_confirmed(self, dialog, result, entries: list[AnimeEntry]):
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            LOGGER.warning("Could not finish the import confirmation dialog", exc_info=True)
            return
        if response != "replace":
            return
        try:
            self.storage.replace_all(entries)
        except (ValueError, sqlite3.Error, OSError) as error:
            LOGGER.exception("Could not replace library from imported backup")
            self.toast_overlay.add_toast(Adw.Toast.new(f"Import failed: {error}"))
            return
        self.entries = self.storage.list_entries()
        self._render_library()
        self._refresh_airing_schedule()
        self.toast_overlay.add_toast(
            Adw.Toast.new(f"Imported {len(entries)} anime entries.")
        )





    def _show_profiles_dialog(self):
        try:
            profiles = list(self.profile_store.list_profiles())
            active = self.profile_store.active_profile()
        except (OSError, ProfileError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new("Could not load profiles: " + str(error)))
            return
        dialog = Adw.AlertDialog(
            heading="Settings Profiles",
            body="Each profile has its own library database, configuration, and cache. Switching profiles takes effect after you close and reopen Aniyori.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        profile_dropdown = Gtk.DropDown.new_from_strings([item.name for item in profiles])
        profile_dropdown.set_selected(next(
            index for index, item in enumerate(profiles)
            if item.profile_id == active.profile_id
        ))
        content.append(Gtk.Label(label="Active profile", xalign=0))
        content.append(profile_dropdown)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("New profile name")
        content.append(name_entry)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        create_button = Gtk.Button(label="Create")
        switch_button = Gtk.Button(label="Switch Profile")
        remove_button = Gtk.Button(label="Remove Selected")
        buttons.append(create_button)
        buttons.append(switch_button)
        buttons.append(remove_button)
        content.append(buttons)
        portable = os.environ.get("ANIYORI_PORTABLE_MODE") == "1"
        if portable:
            portable_text = "Portable mode is active. Data is stored beside the application in: " + str(
                os.environ.get("ANIYORI_PORTABLE_DIR") or (Path(__file__).resolve().parents[1] / "portable-data")
            )
        else:
            portable_text = (
                "Portable mode is off. To enable it, place an empty .aniyori-portable marker "
                "beside main.py and restart. The application directory must be writable."
            )
        portable_label = Gtk.Label(label=portable_text, xalign=0, wrap=True)
        portable_label.add_css_class("dim-label")
        content.append(portable_label)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)
        def refresh(selected_id=None):
            nonlocal profiles
            try:
                profiles = list(self.profile_store.list_profiles())
                current = self.profile_store.active_profile()
            except (OSError, ProfileError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not refresh profiles: " + str(error)))
                return
            profile_dropdown.set_model(Gtk.StringList.new([item.name for item in profiles]))
            target = selected_id or current.profile_id
            profile_dropdown.set_selected(next(
                (index for index, item in enumerate(profiles) if item.profile_id == target),
                next(index for index, item in enumerate(profiles) if item.profile_id == current.profile_id),
            ))
        def create_profile(_button):
            try:
                created = self.profile_store.create(name_entry.get_text())
            except (OSError, ProfileError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not create profile: " + str(error)))
                return
            name_entry.set_text("")
            refresh(created.profile_id)
            self.toast_overlay.add_toast(Adw.Toast.new("Profile created. Select it and choose Switch Profile to use it after restarting."))
        def switch_profile(_button):
            index = profile_dropdown.get_selected()
            if index >= len(profiles):
                return
            selected = profiles[index]
            try:
                self.profile_store.switch(selected.profile_id)
            except (OSError, ProfileError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not switch profile: " + str(error)))
                return
            self.toast_overlay.add_toast(Adw.Toast.new("Profile selected. Close and reopen Aniyori to load its separate data."))
        def confirm_remove(_dialog, result, selected):
            try:
                response = _dialog.choose_finish(result)
            except GLib.Error:
                LOGGER.warning("Could not finish profile removal confirmation", exc_info=True)
                return
            if response != "remove":
                return
            try:
                self.profile_store.remove(selected.profile_id)
            except (OSError, ProfileError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not remove profile: " + str(error)))
                return
            refresh()
            self.toast_overlay.add_toast(Adw.Toast.new("Profile and its isolated data were removed."))
        def remove_profile(_button):
            index = profile_dropdown.get_selected()
            if index >= len(profiles):
                return
            selected = profiles[index]
            if selected.profile_id == "default":
                self.toast_overlay.add_toast(Adw.Toast.new("The Default profile cannot be removed."))
                return
            if selected.profile_id == self.profile_store.active_profile().profile_id:
                self.toast_overlay.add_toast(
                    Adw.Toast.new("Switch to another profile, restart Aniyori, then remove this profile.")
                )
                return
            confirm = Adw.AlertDialog(
                heading="Remove profile?",
                body="This permanently deletes the selected profile's library, settings, and cache. This cannot be undone.",
            )
            confirm.add_response("cancel", "Cancel")
            confirm.add_response("remove", "Remove Profile")
            confirm.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
            confirm.set_default_response("cancel")
            confirm.set_close_response("cancel")
            confirm.choose(self, None, confirm_remove, selected)
        create_button.connect("clicked", create_profile)
        switch_button.connect("clicked", switch_profile)
        remove_button.connect("clicked", remove_profile)

    def _show_network_settings_dialog(self):
        try:
            saved = self.network_settings_store.load()
        except (OSError, NetworkSettingsError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new("Could not load network settings: " + str(error)))
            return
        dialog = Adw.AlertDialog(
            heading="Network Settings",
            body="Configure an optional HTTP(S) proxy, request timeout, safe retry count, and an optional custom CA bundle. TLS certificate validation is always enabled; Aniyori does not offer an insecure verification bypass.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        proxy = Gtk.Entry()
        proxy.set_placeholder_text("Proxy URL (optional), e.g. http://127.0.0.1:8080")
        proxy.set_text(saved.proxy_url or "")
        content.append(proxy)
        timeout = Gtk.SpinButton.new_with_range(1, 120, 1)
        timeout.set_value(saved.timeout_seconds)
        content.append(Gtk.Label(label="Request timeout (seconds)", xalign=0))
        content.append(timeout)
        retries = Gtk.SpinButton.new_with_range(0, 5, 1)
        retries.set_value(saved.retries)
        content.append(Gtk.Label(label="Retries for safe read-only requests", xalign=0))
        content.append(retries)
        ca_bundle = Gtk.Entry()
        ca_bundle.set_placeholder_text("Custom CA bundle path (optional)")
        ca_bundle.set_text(saved.ca_bundle_path or "")
        content.append(ca_bundle)
        content.append(Gtk.Label(
            label="A custom CA bundle is useful for enterprise/self-hosted HTTPS. Certificate checks remain mandatory. Passwords in proxy URLs are not supported.",
            xalign=0, wrap=True,
        ))
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        def response(_dialog, result):
            try:
                selected = _dialog.choose_finish(result)
            except GLib.Error:
                LOGGER.warning("Could not finish network settings dialog", exc_info=True)
                return
            if selected != "save":
                return
            settings = NetworkSettings(
                proxy.get_text().strip() or None,
                timeout.get_value_as_int(),
                retries.get_value_as_int(),
                ca_bundle.get_text().strip() or None,
            )
            try:
                self.network_settings_store.save(settings)
            except (OSError, NetworkSettingsError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not save network settings: " + str(error)))
                return
            self.toast_overlay.add_toast(Adw.Toast.new("Network settings saved. They apply to new requests."))
        dialog.choose(self, None, response)

    def _record_notification(
        self, event_type, severity, title, message, dedupe_key=None
    ):
        try:
            item = self.notification_store.add(
                event_type, severity, title, message, dedupe_key=dedupe_key
            )
            preferences = self.notification_store.preferences()
        except (OSError, NotificationError) as error:
            LOGGER.warning("Could not store notification: %s", error)
            return GLib.SOURCE_REMOVE
        if item is not None and preferences.desktop_notifications:
            application = self.get_application()
            if application is not None:
                notification = Gio.Notification.new(item.title)
                notification.set_body(item.message)
                application.send_notification(item.notification_id, notification)
        return GLib.SOURCE_REMOVE

    def _show_notification_center(self):
        dialog = Adw.AlertDialog(
            heading="Notifications",
            body="Recent matched releases, new episode reminders, download failures, webhook errors, and backup events.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        listing = Gtk.ListBox()
        listing.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listing.add_css_class("boxed-list")
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(280)
        scroll.set_max_content_height(480)
        scroll.set_child(listing)
        content.append(scroll)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dismiss = Gtk.Button(label="Dismiss Selected")
        clear = Gtk.Button(label="Clear Dismissed")
        actions.append(dismiss)
        actions.append(clear)
        content.append(actions)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)
        rows = {}
        def refresh():
            rows.clear()
            child = listing.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                listing.remove(child)
                child = following
            try:
                items = self.notification_store.list(limit=200)
            except (OSError, NotificationError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not load notifications: " + str(error)))
                return
            if not items:
                listing.append(Gtk.ListBoxRow(child=Gtk.Label(label="No notifications yet.", xalign=0)))
                return
            for item in items:
                row = Gtk.ListBoxRow()
                state = "Dismissed" if item.dismissed else item.severity.upper()
                label = Gtk.Label(
                    label=item.created_at + " · " + state + " · " + item.title + "\n" + item.message,
                    xalign=0, wrap=True,
                )
                label.set_margin_top(8)
                label.set_margin_bottom(8)
                label.set_margin_start(8)
                label.set_margin_end(8)
                row.set_child(label)
                rows[row] = item
                listing.append(row)
        def dismiss_selected(_button):
            row = listing.get_selected_row()
            item = rows.get(row) if row is not None else None
            if item is None:
                self.toast_overlay.add_toast(Adw.Toast.new("Select a notification to dismiss."))
                return
            try:
                self.notification_store.dismiss([item.notification_id])
            except (OSError, NotificationError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not dismiss notification: " + str(error)))
                return
            refresh()
        def clear_dismissed(_button):
            try:
                removed = self.notification_store.clear_dismissed()
            except (OSError, NotificationError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not clear dismissed notifications: " + str(error)))
                return
            refresh()
            self.toast_overlay.add_toast(Adw.Toast.new("Cleared " + str(removed) + " dismissed notification(s)."))
        dismiss.connect("clicked", dismiss_selected)
        clear.connect("clicked", clear_dismissed)
        refresh()

    def _show_notification_preferences(self):
        try:
            saved = self.notification_store.preferences()
        except (OSError, NotificationError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new("Could not load notification preferences: " + str(error)))
            return
        dialog = Adw.AlertDialog(
            heading="Notification Preferences",
            body="Choose which event types are saved. Desktop notifications are optional and depend on your desktop environment.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        labels = {
            "release_match": "New matched releases",
            "download_failure": "Download failures",
            "webhook_error": "Webhook delivery errors",
            "backup": "Backup and restore events",
            "new_episode": "New episode airing reminders (off by default)",
        }
        checks = {}
        for event_type in EVENT_TYPES:
            check = Gtk.CheckButton(label=labels[event_type])
            check.set_active(event_type in saved.enabled_events)
            checks[event_type] = check
            content.append(check)
        desktop = Gtk.CheckButton(label="Show desktop notifications")
        desktop.set_active(saved.desktop_notifications)
        content.append(desktop)
        severity_label = Gtk.Label(label="Minimum notification severity", xalign=0)
        content.append(severity_label)
        severity_dropdown = Gtk.DropDown.new_from_strings([
            "All notifications", "Warnings and errors", "Errors only",
        ])
        severity_dropdown.set_selected(("info", "warning", "error").index(saved.minimum_severity))
        content.append(severity_dropdown)
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        def response(_dialog, result):
            try:
                selected = _dialog.choose_finish(result)
            except GLib.Error:
                LOGGER.warning("Could not finish notification preferences dialog", exc_info=True)
                return
            if selected != "save":
                return
            preferences = NotificationPreferences(
                tuple(event for event, check in checks.items() if check.get_active()),
                desktop.get_active(),
                ("info", "warning", "error")[severity_dropdown.get_selected()],
            )
            try:
                self.notification_store.save_preferences(preferences)
            except (OSError, NotificationError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not save notification preferences: " + str(error)))
                return
            self.toast_overlay.add_toast(Adw.Toast.new("Notification preferences saved."))
        dialog.choose(self, None, response)

    def _show_player_detection_preferences(self):
        enabled = Gtk.CheckButton(label="Detect playback in mpv and VLC")
        enabled.set_active(self.player_detection_settings.enabled)
        description = Gtk.Label(
            label=(
                "When enabled, Aniyori checks supported MPRIS players in the background. "
                "A confidently matched local video updates progress after at least 90% "
                "of its duration. Unrecognized or ambiguous files are ignored."
            ),
            xalign=0,
            wrap=True,
        )
        dialog = Adw.AlertDialog(
            heading="Local Player Detection",
            body="Playback detection is optional and disabled by default.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.append(enabled)
        content.append(description)
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def response(_dialog, result):
            try:
                selected = _dialog.choose_finish(result)
            except GLib.Error:
                LOGGER.warning("Could not finish player detection preferences dialog", exc_info=True)
                return
            if selected != "save":
                return
            settings = PlayerDetectionSettings(enabled.get_active())
            try:
                self.player_detection_store.save(settings)
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new("Could not save player detection settings: " + str(error))
                )
                return
            self.player_detection_settings = settings
            if settings.enabled:
                self._start_player_detection()
                self.toast_overlay.add_toast(Adw.Toast.new("Local player detection enabled."))
            else:
                self._stop_player_detection()
                self.toast_overlay.add_toast(Adw.Toast.new("Local player detection disabled."))

        dialog.choose(self, None, response)

    def _start_player_detection(self):
        if self._player_poll_source is None:
            self._player_poll_source = GLib.timeout_add_seconds(10, self._poll_player_playback)

    def _stop_player_detection(self):
        if self._player_poll_source is not None:
            GLib.source_remove(self._player_poll_source)
            self._player_poll_source = None

    def _poll_player_playback(self):
        if not self.player_detection_settings.enabled or self._player_poll_running:
            return GLib.SOURCE_CONTINUE
        self._player_poll_running = True

        def unpack(value):
            return value.unpack() if hasattr(value, "unpack") else value

        def worker():
            states = []
            try:
                connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
                names_reply = connection.call_sync(
                    "org.freedesktop.DBus",
                    "/org/freedesktop/DBus",
                    "org.freedesktop.DBus",
                    "ListNames",
                    None,
                    GLib.VariantType.new("(as)"),
                    Gio.DBusCallFlags.NONE,
                    1500,
                    None,
                )
                names = names_reply.unpack()[0]
                for bus_name in supported_player_names(names):
                    try:
                        reply = connection.call_sync(
                            bus_name,
                            "/org/mpris/MediaPlayer2",
                            "org.freedesktop.DBus.Properties",
                            "GetAll",
                            GLib.Variant("(s)", ("org.mpris.MediaPlayer2.Player",)),
                            GLib.VariantType.new("(a{sv})"),
                            Gio.DBusCallFlags.NONE,
                            1500,
                            None,
                        )
                        properties = reply.unpack()[0]
                        metadata = unpack(properties.get("Metadata") or {})
                        uri = unpack(metadata.get("xesam:url"))
                        status = unpack(properties.get("PlaybackStatus"))
                        position = unpack(properties.get("Position", 0))
                        duration = unpack(metadata.get("mpris:length", 0))
                        if isinstance(uri, str) and status in {"Playing", "Paused", "Stopped"}:
                            states.append((bus_name, uri, status, position, duration))
                    except GLib.Error:
                        LOGGER.debug("Could not query MPRIS player %s", bus_name, exc_info=True)
            except (GLib.Error, OSError):
                LOGGER.debug("Session bus or MPRIS player discovery is unavailable", exc_info=True)
            GLib.idle_add(self._apply_player_playback, states)

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def _apply_player_playback(self, states):
        self._player_poll_running = False
        if not self.player_detection_settings.enabled:
            return GLib.SOURCE_REMOVE
        for bus_name, uri, status, position, duration in states:
            if not playback_finished(position, duration):
                continue
            match = match_playback_file(uri, self.entries)
            if match is None:
                continue
            storage_id, episode = match
            entry = next(
                (item for item in self.entries if item.storage_id == storage_id),
                None,
            )
            if entry is None or episode <= entry.episodes_watched:
                continue
            try:
                changed = self.storage.update_progress(
                    storage_id,
                    episode,
                    source="player:" + bus_name.rsplit(".", 1)[-1],
                )
            except (OSError, ValueError) as error:
                LOGGER.debug("Could not update player-detected progress: %s", error)
                continue
            if changed:
                self.entries = self.storage.list_entries()
                updated = next(
                    (item for item in self.entries if item.storage_id == storage_id),
                    None,
                )
                if updated is not None:
                    self._dispatch_webhook_event(updated, "progress")
                self._render_library()
        return GLib.SOURCE_REMOVE

    def _dispatch_webhook_event(self, entry: AnimeEntry, event_type: str):
        """Deliver a watch-status event off the GTK thread; isolate endpoint failures."""
        try:
            webhooks = self.webhook_store.load()
        except (OSError, WebhookError) as error:
            LOGGER.warning("Could not load configured webhooks: %s", error)
            return
        if not any(item.enabled for item in webhooks):
            return
        from datetime import datetime, timezone
        event = {
            "event": event_type,
            "anime_title": entry.title,
            "episode": entry.episodes_watched if event_type == "progress" else None,
            "progress": entry.episodes_watched,
            "total_episodes": entry.episodes_total,
            "status": entry.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        def worker():
            try:
                outcomes = deliver_webhooks(webhooks, event)
                for outcome in outcomes:
                    if not outcome.success:
                        LOGGER.warning("Webhook '%s' delivery failed: %s", outcome.name, outcome.message)
                        GLib.idle_add(
                            self._record_notification, "webhook_error", "warning",
                            "Webhook delivery failed",
                            outcome.name + ": " + outcome.message,
                            "webhook:" + outcome.webhook_id + ":" + outcome.message,
                        )
            except Exception:
                LOGGER.exception("Webhook event delivery failed unexpectedly")
        threading.Thread(target=worker, daemon=True).start()

    def _show_webhook_manager(self):
        try:
            webhooks = list(self.webhook_store.load())
        except (OSError, WebhookError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new("Could not load webhooks: " + str(error)))
            webhooks = []
        dialog = Adw.AlertDialog(
            heading="HTTP Webhooks",
            body="Enabled webhooks receive JSON watch-progress and status events. Requests run in the background; failures are logged and never block library updates.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        listing = Gtk.ListBox()
        listing.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listing.add_css_class("boxed-list")
        content.append(listing)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Webhook name")
        content.append(name_entry)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://example.org/webhook")
        url_entry.set_input_purpose(Gtk.InputPurpose.URL)
        content.append(url_entry)
        headers_entry = Gtk.Entry()
        headers_entry.set_placeholder_text('Optional headers as JSON, e.g. {"X-Api-Key":"…"}')
        content.append(headers_entry)
        enabled_check = Gtk.CheckButton(label="Enabled")
        enabled_check.set_active(True)
        content.append(enabled_check)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        save_button = Gtk.Button(label="Add Webhook")
        edit_button = Gtk.Button(label="Edit Selected")
        remove_button = Gtk.Button(label="Remove Selected")
        buttons.append(save_button)
        buttons.append(edit_button)
        buttons.append(remove_button)
        content.append(buttons)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)
        editing_id = {"value": None}
        rows = {}
        def refresh():
            rows.clear()
            child = listing.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                listing.remove(child)
                child = following
            for webhook in webhooks:
                row = Gtk.ListBoxRow()
                label = Gtk.Label(
                    label=webhook.name + " · " + webhook.url + " · " + ("Enabled" if webhook.enabled else "Disabled"),
                    xalign=0, wrap=True,
                )
                label.set_margin_top(6)
                label.set_margin_bottom(6)
                label.set_margin_start(8)
                label.set_margin_end(8)
                row.set_child(label)
                rows[row] = webhook
                listing.append(row)
        def selected_webhook():
            row = listing.get_selected_row()
            return rows.get(row) if row is not None else None
        def edit_selected(_button):
            webhook = selected_webhook()
            if webhook is None:
                self.toast_overlay.add_toast(Adw.Toast.new("Select a webhook to edit."))
                return
            editing_id["value"] = webhook.webhook_id
            name_entry.set_text(webhook.name)
            url_entry.set_text(webhook.url)
            headers_entry.set_text(json.dumps(dict(webhook.headers or {})))
            enabled_check.set_active(webhook.enabled)
            save_button.set_label("Save Changes")
        def remove_selected(_button):
            webhook = selected_webhook()
            if webhook is None:
                self.toast_overlay.add_toast(Adw.Toast.new("Select a webhook to remove."))
                return
            try:
                webhooks[:] = self.webhook_store.remove(webhook.webhook_id)
            except (OSError, WebhookError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not remove webhook: " + str(error)))
                return
            if editing_id["value"] == webhook.webhook_id:
                editing_id["value"] = None
                save_button.set_label("Add Webhook")
                name_entry.set_text("")
                url_entry.set_text("")
                headers_entry.set_text("")
            refresh()
        def save_webhook(_button):
            try:
                headers = json.loads(headers_entry.get_text() or "{}")
                if not isinstance(headers, dict):
                    raise WebhookError("Webhook headers must be a JSON object.")
                if editing_id["value"]:
                    webhooks[:] = self.webhook_store.update(
                        editing_id["value"], name=name_entry.get_text(),
                        url=url_entry.get_text(), enabled=enabled_check.get_active(),
                        headers=headers,
                    )
                else:
                    webhooks[:] = self.webhook_store.add(name_entry.get_text(), url_entry.get_text(), headers)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new("Could not save webhook: " + str(error)))
                return
            editing_id["value"] = None
            save_button.set_label("Add Webhook")
            name_entry.set_text("")
            url_entry.set_text("")
            headers_entry.set_text("")
            enabled_check.set_active(True)
            refresh()
            self.toast_overlay.add_toast(Adw.Toast.new("Webhook saved."))
        save_button.connect("clicked", save_webhook)
        edit_button.connect("clicked", edit_selected)
        remove_button.connect("clicked", remove_selected)
        refresh()

    def _show_watch_history_dialog(self):
        dialog = Adw.AlertDialog(
            heading='Watch History',
            body='Review episode, progress, and status events recorded by Aniyori. Player integrations can record events with their own source label.',
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        anime_filter = Gtk.Entry()
        anime_filter.set_placeholder_text('Filter anime title')
        anime_filter.set_hexpand(True)
        filters.append(anime_filter)
        date_filter = Gtk.Entry()
        date_filter.set_placeholder_text('YYYY-MM-DD')
        date_filter.set_width_chars(12)
        filters.append(date_filter)
        action_filter = Gtk.DropDown.new_from_strings(['All actions', 'Episode', 'Progress', 'Status'])
        filters.append(action_filter)
        content.append(filters)
        listing = Gtk.ListBox()
        listing.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listing.add_css_class('boxed-list')
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(260)
        scroll.set_max_content_height(420)
        scroll.set_child(listing)
        content.append(scroll)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_button = Gtk.Button(label='Filter')
        remove_button = Gtk.Button(label='Remove Selected')
        prune_button = Gtk.Button(label='Prune Before Date')
        actions.append(filter_button)
        actions.append(remove_button)
        actions.append(prune_button)
        content.append(actions)
        dialog.set_extra_child(content)
        dialog.add_response('close', 'Close')
        dialog.set_default_response('close')
        dialog.present(self)
        action_values = ('all', 'episode', 'progress', 'status')
        event_ids = {}
        def refresh():
            event_ids.clear()
            child = listing.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                listing.remove(child)
                child = following
            try:
                events = self.storage.list_watch_history(
                    anime=anime_filter.get_text().strip() or None,
                    date_filter=date_filter.get_text().strip() or None,
                    action=action_values[action_filter.get_selected()],
                )
            except ValueError as error:
                self.toast_overlay.add_toast(Adw.Toast.new(str(error)))
                return
            if not events:
                row = Gtk.ListBoxRow()
                row.set_child(Gtk.Label(label='No watch-history events match these filters.', xalign=0))
                listing.append(row)
                return
            for event in events:
                episode = (' · Episode ' + str(event['episode'])) if event['episode'] is not None else ''
                details = (' · ' + event['details']) if event['details'] else ''
                label = (
                    str(event['created_at']) + ' · ' + str(event['anime_title']) + episode
                    + ' · ' + str(event['action']).title() + ' (' + str(event['source']) + ')' + details
                )
                row = Gtk.ListBoxRow()
                event_ids[row] = event['id']
                row.set_child(Gtk.Label(label=label, xalign=0, wrap=True))
                listing.append(row)
        def remove_selected(_button):
            selected = listing.get_selected_row()
            event_id = event_ids.get(selected) if selected is not None else None
            if event_id is None:
                self.toast_overlay.add_toast(Adw.Toast.new('Select a history event to remove.'))
                return
            try:
                self.storage.remove_watch_history([event_id])
            except (ValueError, sqlite3.Error, OSError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new('Could not remove history: ' + str(error)))
                return
            refresh()
        def prune_history(_button):
            cutoff = date_filter.get_text().strip()
            if not cutoff:
                self.toast_overlay.add_toast(Adw.Toast.new('Enter a date to prune older events.'))
                return
            try:
                removed = self.storage.prune_watch_history(cutoff)
            except (ValueError, sqlite3.Error, OSError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new('Could not prune history: ' + str(error)))
                return
            refresh()
            self.toast_overlay.add_toast(Adw.Toast.new('Pruned ' + str(removed) + ' history event(s).'))
        filter_button.connect('clicked', lambda _button: refresh())
        remove_button.connect('clicked', remove_selected)
        prune_button.connect('clicked', prune_history)
        refresh()
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

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        panel.set_margin_top(12)
        panel.set_margin_bottom(4)
        year_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        year_label = Gtk.Label(label="Viewing year", xalign=0)
        year_label.set_hexpand(True)
        current_year = datetime.now().astimezone().year
        year_spin = Gtk.SpinButton.new_with_range(1900, current_year, 1)
        year_spin.set_value(current_year)
        year_row.append(year_label)
        year_row.append(year_spin)
        panel.append(year_row)

        month_names = (
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        )
        month_bars = []
        month_grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        for index, month_name in enumerate(month_names):
            label = Gtk.Label(label=month_name, xalign=0)
            label.set_width_chars(4)
            bar = Gtk.ProgressBar()
            bar.set_hexpand(True)
            bar.set_show_text(True)
            bar.set_text("Loading…")
            month_grid.attach(label, 0, index, 1, 1)
            month_grid.attach(bar, 1, index, 1, 1)
            month_bars.append(bar)
        panel.append(month_grid)

        summary = Gtk.Label(label="Loading watch history…", xalign=0, wrap=True)
        completed_label = Gtk.Label(xalign=0, wrap=True)
        estimate_label = Gtk.Label(xalign=0, wrap=True)
        for label in (summary, completed_label, estimate_label):
            label.set_selectable(True)
            panel.append(label)

        local_timezone = datetime.now().astimezone().tzinfo
        history_request = {"generation": 0}

        def apply_history_year(generation, year, insights, error):
            if generation != history_request["generation"]:
                return GLib.SOURCE_REMOVE
            if error:
                summary.set_label(f"Could not load watch history for {year}: {error}")
                completed_label.set_label("")
                estimate_label.set_label("")
                for bar in month_bars:
                    bar.set_fraction(0)
                    bar.set_text("Unavailable")
                return GLib.SOURCE_REMOVE

            maximum = max(
                (month["event_count"] for month in insights["months"]),
                default=0,
            )
            for bar, month in zip(month_bars, insights["months"]):
                count = month["event_count"]
                bar.set_fraction(count / maximum if maximum else 0)
                bar.set_text(f"{count} events")
                bar.set_tooltip_text(
                    f"{month['episode_events']} episode events; "
                    f"{month['rewatch_events']} rewatches; "
                    f"{month['progress_changes']} progress changes; "
                    f"{month['status_changes']} status changes"
                )

            if insights["event_count"]:
                summary.set_label(
                    f"Recorded episode events: {insights['episode_events']} "
                    f"({insights['first_watch_events']} identified first watches, "
                    f"{insights['rewatch_events']} rewatches); "
                    f"progress changes: {insights['progress_changes']}; "
                    f"status changes: {insights['status_changes']}; "
                    f"active days: {insights['active_days']}."
                )
            else:
                summary.set_label(
                    f"No recorded watch-history events for {year}. "
                    "This does not mean no episodes were watched; imported or older "
                    "progress may predate history tracking."
                )
            titles = [item["title"] for item in insights["completed_anime"]]
            completed_label.set_label(
                f"Anime marked completed: {insights['completed_anime_count']}"
                + (f" — {', '.join(titles)}" if titles else "")
            )
            hours = insights["estimated_minutes"] / 60
            estimate_label.set_label(
                f"Estimated time: {hours:.1f} hours "
                f"({insights['minutes_per_episode']} minutes per recorded episode event; "
                "an estimate, not measured playback)."
            )
            return GLib.SOURCE_REMOVE

        def update_history_year(_spin=None):
            history_request["generation"] += 1
            generation = history_request["generation"]
            year = year_spin.get_value_as_int()
            summary.set_label(f"Loading watch history for {year}…")
            completed_label.set_label("")
            estimate_label.set_label("")
            for bar in month_bars:
                bar.set_fraction(0)
                bar.set_text("Loading…")

            def worker():
                try:
                    events = self.storage.list_watch_history_for_year(
                        year, local_timezone=local_timezone
                    )
                    insights = calculate_history_insights(
                        events, year, local_timezone=local_timezone
                    )
                    error = None
                except (OSError, ValueError, sqlite3.Error) as exception:
                    insights = None
                    error = str(exception)
                GLib.idle_add(
                    apply_history_year, generation, year, insights, error
                )

            threading.Thread(target=worker, daemon=True).start()

        year_spin.connect("value-changed", update_history_year)
        dialog.set_extra_child(panel)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present(self)
        update_history_year()

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

    def _on_library_sort_changed(self, dropdown, _property):
        selected = dropdown.get_selected()
        if selected < len(SORT_MODES):
            self.library_sort_mode = SORT_MODES[selected]
            self._render_library()

    def _on_view_toggled(self, button, key):
        if not button.get_active():
            return
        self.stack.set_visible_child_name(key)


    def _show_release_results(self):
        self.stack.set_visible_child_name("releases")
        self._render_release_results()
        return GLib.SOURCE_REMOVE

    def _render_release_results(self):
        child = self.release_list_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.release_list_box.remove(child)
            child = next_child

        if not self.release_results:
            label = Gtk.Label(
                label="No release results yet. Add feeds and refresh to look for new episodes.",
                wrap=True,
                justify=Gtk.Justification.CENTER,
            )
            label.set_margin_top(24)
            label.set_margin_bottom(24)
            label.add_css_class("dim-label")
            self.release_list_box.append(label)
            return

        rendered = 0
        sort_modes = ("quality", "newest", "seeders", "title")
        selected_sort = self.release_sort_dropdown.get_selected()
        sort_by = sort_modes[selected_sort] if selected_sort < len(sort_modes) else "quality"
        visible_results = filter_release_results(
            self.release_results,
            query=self.release_search_entry.get_text(),
            eligible_only=self.release_eligible_only_check.get_active(),
            sort_by=sort_by,
        )
        for result in visible_results:
            if result.error:
                row_label = Gtk.Label(
                    label=f"{result.feed.name} — refresh failed: {result.error}",
                    xalign=0,
                    wrap=True,
                )
                row_label.add_css_class("error")
                row_label.set_margin_top(8)
                row_label.set_margin_bottom(8)
                row_label.set_margin_start(12)
                row_label.set_margin_end(12)
                self.release_list_box.append(row_label)
                rendered += 1
                continue

            for release in result.releases:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                row.set_margin_top(10)
                row.set_margin_bottom(10)
                row.set_margin_start(12)
                row.set_margin_end(12)
                details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                details.set_hexpand(True)
                title = Gtk.Label(label=release.entry.title, xalign=0, wrap=True)
                title.add_css_class("heading")
                details.append(title)
                if release.match_status == "matched":
                    match_text = f"Matched: {release.matched_title}"
                    if release.season is not None:
                        match_text += f" · S{release.season:02d}E{release.episode:02d}"
                    else:
                        match_text += f" · Episode {release.episode}"
                else:
                    match_text = f"Catalogue match: {release.match_status.replace('_', ' ')}"
                decision = (
                    "Discarded by rule" if release.rule_status == "discarded" else
                    "Eligible" if release.eligible else
                    release.anime_preference_reason if release.anime_preference_reason else
                    "Rejected by preferences" if not release.score.accepted else
                    "Below score threshold"
                )
                if release.rule_status in {"wanted", "preferred"}:
                    decision += f" · {release.rule_status.title()} rule"
                facts = []
                for key, label in (("size", "Size"), ("seeders", "Seeders"),
                                   ("leechers", "Leechers"), ("downloads", "Downloads")):
                    value = release.metadata.get(key)
                    if value is not None:
                        facts.append(f"{label}: {value}")
                subtitle = Gtk.Label(
                    label=(
                        f"{release.feed_name} · {match_text} · "
                        + (" · ".join(facts) + " · " if facts else "")
                        + f"Quality {release.score.score:.1f}/100 · {decision}"
                    ),
                    xalign=0,
                    wrap=True,
                )
                subtitle.add_css_class("dim-label")
                subtitle.set_tooltip_text(release.decision_explanation)
                details.append(subtitle)
                row.append(details)
                if release.entry.magnet_uri:
                    send_button = Gtk.Button(label="Send to qBittorrent")
                    send_button.set_tooltip_text(
                        "Explicitly submit this release to your configured qBittorrent WebUI."
                    )
                    send_button.set_valign(Gtk.Align.CENTER)
                    send_button.set_sensitive(release.eligible)
                    if not release.eligible:
                        send_button.set_tooltip_text(
                            release.anime_preference_reason or release.decision_explanation
                        )
                    send_button.connect(
                        "clicked",
                        lambda _button, magnet=release.entry.magnet_uri:
                            self._send_release_to_qbittorrent(magnet),
                    )
                    row.append(send_button)
                    link = Gtk.LinkButton.new_with_label(
                        release.entry.magnet_uri, "Open in default app"
                    )
                    link.set_tooltip_text(
                        "Open this magnet link in your desktop's registered torrent application."
                        if release.eligible else
                        release.anime_preference_reason or release.decision_explanation
                    )
                    link.set_sensitive(release.eligible)
                    link.set_valign(Gtk.Align.CENTER)
                    row.append(link)
                elif release.entry.link:
                    link = Gtk.LinkButton.new_with_label(release.entry.link, "Open source")
                    link.set_valign(Gtk.Align.CENTER)
                    row.append(link)
                self.release_list_box.append(row)
                rendered += 1

        if rendered == 0:
            label = Gtk.Label(
                label=(
                    "No eligible releases match the current preferences and score cutoff."
                    if self.release_eligible_only_check.get_active()
                    else "No release entries were found in the configured feeds."
                ),
                wrap=True,
                justify=Gtk.Justification.CENTER,
            )
            label.set_margin_top(24)
            label.set_margin_bottom(24)
            label.add_css_class("dim-label")
            self.release_list_box.append(label)

    def _show_download_queue(self):
        """Show and manage the configured qBittorrent queue without blocking GTK."""
        try:
            settings = self.qbittorrent_settings_store.load()
            if settings is None:
                self.toast_overlay.add_toast(Adw.Toast.new("Configure qBittorrent first."))
                self._show_qbittorrent_settings_dialog()
                return
            credentials = SecretServiceCredentialStore()
        except (QBittorrentError, CredentialStoreError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(str(error)))
            return

        dialog = Gtk.Window(transient_for=self, modal=True, title="Download Queue")
        dialog.set_default_size(760, 520)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{side}")(16)
        heading = Gtk.Label(label="qBittorrent Downloads", xalign=0)
        heading.add_css_class("title-2")
        content.append(heading)
        status = Gtk.Label(label="Loading queue…", xalign=0)
        status.add_css_class("dim-label")
        content.append(status)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        refresh_button = Gtk.Button(label="Refresh")
        toolbar.append(refresh_button)
        toolbar.append(Gtk.Label(label="Refreshes automatically every 10 seconds", xalign=0))
        content.append(toolbar)
        queue_list = Gtk.ListBox()
        queue_list.set_selection_mode(Gtk.SelectionMode.NONE)
        queue_list.add_css_class("boxed-list")
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(queue_list)
        content.append(scroll)
        dialog.set_child(content)

        busy = [False]
        timer_id = [0]

        def format_size(value):
            amount = float(value)
            for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
                if amount < 1024 or unit == "TiB":
                    return f"{amount:.1f} {unit}"
                amount /= 1024
            return f"{amount:.1f} TiB"

        def format_eta(value):
            if value is None:
                return "ETA unknown"
            hours, remainder = divmod(value, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"ETA {hours}h {minutes}m" if hours else f"ETA {minutes}m {seconds}s"

        def clear_rows():
            child = queue_list.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                queue_list.remove(child)
                child = following

        def render_queue(torrents, error=None):
            busy[0] = False
            refresh_button.set_sensitive(True)
            clear_rows()
            if error:
                status.set_label(f"Queue refresh failed: {error}")
                return GLib.SOURCE_REMOVE
            status.set_label(f"{len(torrents)} torrent(s) · last refreshed just now")
            if not torrents:
                queue_list.append(Gtk.Label(label="The qBittorrent queue is empty.", margin_top=24, margin_bottom=24))
                return GLib.SOURCE_REMOVE
            for torrent in torrents:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                details.set_hexpand(True)
                name = Gtk.Label(label=torrent["name"], xalign=0)
                name.set_ellipsize(3)
                name.set_max_width_chars(64)
                name.add_css_class("heading")
                details.append(name)
                downloaded = format_size(torrent["downloaded"])
                total = format_size(torrent["size"])
                speed = format_size(torrent["download_speed"]) + "/s"
                progress_bar = Gtk.ProgressBar()
                progress_bar.set_fraction(torrent["progress"])
                progress_bar.set_show_text(True)
                progress_bar.set_text(f"{torrent['progress'] * 100:.1f}%")
                details.append(progress_bar)
                upload_speed = format_size(torrent["upload_speed"]) + "/s up"
                details.append(Gtk.Label(
                    label=f"{torrent['state']} · {downloaded} / {total} · {speed} down · {upload_speed} · {format_eta(torrent['eta'])}",
                    xalign=0,
                ))
                row.append(details)
                state = torrent["state"].casefold()
                if state in {"error", "missingfiles"}:
                    recheck = Gtk.Button(label="Recheck")
                    recheck.set_tooltip_text("Verify the existing downloaded data")
                    recheck.connect(
                        "clicked",
                        lambda _button, info_hash=torrent["hash"]: run_action("recheck", info_hash),
                    )
                    row.append(recheck)
                else:
                    paused = "paused" in state or "stopped" in state
                    toggle = Gtk.Button(label="Resume" if paused else "Pause")
                    toggle.connect(
                        "clicked",
                        lambda _button, info_hash=torrent["hash"], action="resume" if paused else "pause": run_action(action, info_hash),
                    )
                    row.append(toggle)
                remove = Gtk.Button(label="Remove")
                remove.set_tooltip_text("Remove from qBittorrent without deleting downloaded files")
                remove.connect("clicked", lambda _button, item=torrent: confirm_remove(item))
                row.append(remove)
                queue_list.append(row)
            return GLib.SOURCE_REMOVE

        def refresh(_button=None):
            if busy[0]:
                return GLib.SOURCE_CONTINUE
            busy[0] = True
            refresh_button.set_sensitive(False)
            status.set_label("Refreshing qBittorrent queue…")

            def worker():
                try:
                    password = credentials.lookup("aniyori", self._qbittorrent_credential_account(settings))
                    if not password:
                        raise CredentialStoreError("Saved qBittorrent credentials are missing; configure the connection again.")
                    torrents = QBittorrentClient(settings.server_url, settings.username, password).list_torrents()
                    GLib.idle_add(render_queue, torrents, None)
                except (QBittorrentError, CredentialStoreError, ValueError) as error:
                    GLib.idle_add(render_queue, (), str(error))
            threading.Thread(target=worker, daemon=True).start()
            return GLib.SOURCE_CONTINUE

        def run_action(action, info_hash):
            if busy[0]:
                return
            busy[0] = True
            status.set_label({"pause": "Pausing torrent…", "resume": "Resuming torrent…", "recheck": "Rechecking torrent data…", "remove": "Removing torrent…"}[action])

            def worker():
                try:
                    password = credentials.lookup("aniyori", self._qbittorrent_credential_account(settings))
                    if not password:
                        raise CredentialStoreError("Saved qBittorrent credentials are missing; configure the connection again.")
                    client = QBittorrentClient(settings.server_url, settings.username, password)
                    if action == "pause":
                        client.pause_torrent(info_hash)
                    elif action == "resume":
                        client.resume_torrent(info_hash)
                    elif action == "recheck":
                        client.recheck_torrent(info_hash)
                    elif action == "remove":
                        client.remove_torrent(info_hash, delete_files=False)
                    GLib.idle_add(refresh_after_action)
                except (QBittorrentError, CredentialStoreError, ValueError) as error:
                    GLib.idle_add(render_queue, (), str(error))
            threading.Thread(target=worker, daemon=True).start()

        def refresh_after_action():
            busy[0] = False
            refresh()
            return GLib.SOURCE_REMOVE

        def confirm_remove(torrent):
            confirmation = Adw.AlertDialog(
                heading="Remove download?",
                body=f"Remove ‘{torrent['name']}’ from qBittorrent? Downloaded files will be kept.",
            )
            confirmation.add_response("cancel", "Cancel")
            confirmation.add_response("remove", "Remove")
            confirmation.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
            confirmation.set_default_response("cancel")
            confirmation.choose(dialog, None, on_remove_response, torrent["hash"])

        def on_remove_response(alert, result, info_hash):
            try:
                response = alert.choose_finish(result)
            except GLib.Error:
                LOGGER.warning("Could not finish download removal confirmation", exc_info=True)
                return
            if response == "remove":
                run_action("remove", info_hash)

        def on_close(_window):
            if timer_id[0]:
                GLib.source_remove(timer_id[0])
                timer_id[0] = 0
            return False

        refresh_button.connect("clicked", refresh)
        dialog.connect("close-request", on_close)
        timer_id[0] = GLib.timeout_add_seconds(10, refresh)
        dialog.present()
        refresh()

    def _show_qbittorrent_settings_dialog(self):
        try:
            settings = self.qbittorrent_settings_store.load()
        except QBittorrentError as error:
            self.toast_overlay.add_toast(Adw.Toast.new(str(error)))
            settings = None
        dialog = Adw.AlertDialog(
            heading="qBittorrent WebUI",
            body=(
                "Configure a secure qBittorrent connection. Passwords are stored only "
                "in the desktop Secret Service, never in Aniyori's settings file. "
                "Remote WebUI servers must use HTTPS."
            ),
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        server = Gtk.Entry()
        server.set_placeholder_text("http://localhost:8080")
        server.set_input_purpose(Gtk.InputPurpose.URL)
        server.set_text(settings.server_url if settings else "http://localhost:8080")
        username = Gtk.Entry()
        username.set_placeholder_text("WebUI username")
        if settings:
            username.set_text(settings.username)
        password = Gtk.PasswordEntry()
        password.set_placeholder_text("Password (blank keeps saved password)")
        password.set_show_peek_icon(True)
        category = Gtk.Entry()
        category.set_placeholder_text("Category (optional)")
        if settings:
            category.set_text(settings.category)
        paused = Gtk.CheckButton(label="Add releases paused")
        paused.set_active(settings.paused if settings else False)
        for widget in (server, username, password, category, paused):
            content.append(widget)
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove connection")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("save", "Test & Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_qbittorrent_settings_response,
                      (server, username, password, category, paused, settings))

    def _on_qbittorrent_settings_response(self, dialog, result, widgets):
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            LOGGER.warning("Could not finish qBittorrent settings dialog", exc_info=True)
            return
        server, username, password_entry, category, paused, previous = widgets
        if response == "remove":
            def remove_worker():
                try:
                    if previous:
                        SecretServiceCredentialStore().remove(
                            "aniyori", self._qbittorrent_credential_account(previous)
                        )
                    self.qbittorrent_settings_store.clear()
                    GLib.idle_add(self._finish_qbittorrent_settings, "removed")
                except (CredentialStoreError, OSError) as error:
                    GLib.idle_add(self._finish_qbittorrent_settings, str(error))
            threading.Thread(target=remove_worker, daemon=True).start()
            return
        if response != "save":
            return
        try:
            settings = self.qbittorrent_settings_store.normalize(QBittorrentSettings(
                server.get_text(), username.get_text(), category.get_text(), paused.get_active()
            ))
            credentials = SecretServiceCredentialStore()
            account = self._qbittorrent_credential_account(settings)
            entered_password = password_entry.get_text()
        except (ValueError, CredentialStoreError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(str(error)))
            return

        def worker():
            try:
                secret = entered_password or credentials.lookup("aniyori", account)
                if not secret:
                    raise CredentialStoreError("Enter the qBittorrent WebUI password.")
                QBittorrentClient(settings.server_url, settings.username, secret).test_connection()
                if entered_password:
                    credentials.store("aniyori", account, secret)
                self.qbittorrent_settings_store.save(settings)
                previous_account = (
                    self._qbittorrent_credential_account(previous)
                    if previous is not None else None
                )
                if previous_account and previous_account != account:
                    try:
                        credentials.remove("aniyori", previous_account)
                    except CredentialStoreError:
                        LOGGER.warning(
                            "Could not remove superseded qBittorrent credentials",
                            exc_info=True,
                        )
                GLib.idle_add(self._finish_qbittorrent_settings, None)
            except (QBittorrentError, CredentialStoreError, OSError, ValueError) as error:
                GLib.idle_add(self._finish_qbittorrent_settings, str(error))

        threading.Thread(target=worker, daemon=True).start()
        self.toast_overlay.add_toast(Adw.Toast.new("Testing qBittorrent connection…"))

    def _finish_qbittorrent_settings(self, error):
        if error == "removed":
            message = "qBittorrent connection removed."
        elif error:
            message = f"qBittorrent setup failed: {error}"
        else:
            message = "qBittorrent connection verified and settings saved."
        self.toast_overlay.add_toast(Adw.Toast.new(message))
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _qbittorrent_credential_account(settings):
        return f"qbittorrent:{settings.server_url}:{settings.username}"

    def _send_release_to_qbittorrent(self, magnet_uri):
        try:
            settings = self.qbittorrent_settings_store.load()
            if settings is None:
                self.toast_overlay.add_toast(Adw.Toast.new("Configure qBittorrent first."))
                self._show_qbittorrent_settings_dialog()
                return
            credentials = SecretServiceCredentialStore()
        except (QBittorrentError, CredentialStoreError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(str(error)))
            return

        def worker():
            try:
                password = credentials.lookup(
                    "aniyori", self._qbittorrent_credential_account(settings)
                )
                if not password:
                    GLib.idle_add(self._prompt_qbittorrent_reconfiguration)
                    return
                QBittorrentClient(settings.server_url, settings.username, password).add_magnet(
                    magnet_uri, category=settings.category or None, paused=settings.paused
                )
                GLib.idle_add(self._finish_qbittorrent_submission, None)
            except (QBittorrentError, CredentialStoreError, ValueError) as error:
                GLib.idle_add(self._finish_qbittorrent_submission, str(error))

        threading.Thread(target=worker, daemon=True).start()
        self.toast_overlay.add_toast(Adw.Toast.new("Sending release to qBittorrent…"))

    def _prompt_qbittorrent_reconfiguration(self):
        self.toast_overlay.add_toast(
            Adw.Toast.new("Saved qBittorrent credentials are missing; configure the connection again.")
        )
        self._show_qbittorrent_settings_dialog()
        return GLib.SOURCE_REMOVE

    def _finish_qbittorrent_submission(self, error):
        message = (
            f"qBittorrent submission failed: {error}"
            if error else "Release submitted to qBittorrent."
        )
        self.toast_overlay.add_toast(Adw.Toast.new(message))
        if error:
            self._record_notification(
                "download_failure", "error", "qBittorrent submission failed",
                str(error), "qbittorrent:" + str(error),
            )
        return GLib.SOURCE_REMOVE

    def _show_release_rule_manager(self):
        dialog = Adw.AlertDialog(
            heading="Smart Release Rules",
            body=(
                "Rules are checked from top to bottom. The first matching enabled rule "
                "classifies a release as preferred, wanted, or discarded. Rules never "
                "start downloads automatically."
            ),
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        rule_list = Gtk.ListBox()
        rule_list.set_selection_mode(Gtk.SelectionMode.NONE)
        rule_list.add_css_class("boxed-list")
        rule_scroll = Gtk.ScrolledWindow()
        rule_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        rule_scroll.set_min_content_height(180)
        rule_scroll.set_max_content_height(280)
        rule_scroll.set_child(rule_list)
        content.append(rule_scroll)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Rule name")
        content.append(name_entry)
        field_names = ("Anime title", "Release group", "Resolution", "Source", "Episode", "Keywords")
        field_values = ("title", "release_group", "resolution", "source", "episode", "keywords")
        field_dropdown = Gtk.DropDown.new_from_strings(list(field_names))
        field_dropdown.set_tooltip_text("Release attribute to match")
        content.append(field_dropdown)
        value_entry = Gtk.Entry()
        value_entry.set_placeholder_text("Match value (case-insensitive)")
        content.append(value_entry)
        action_names = ("Prefer", "Include / wanted", "Exclude / discard")
        action_values = ("prefer", "include", "exclude")
        action_dropdown = Gtk.DropDown.new_from_strings(list(action_names))
        action_dropdown.set_tooltip_text("Classification applied when this rule matches")
        content.append(action_dropdown)
        editing = {"id": None}
        save_button = Gtk.Button(label="Add Rule")
        save_button.add_css_class("suggested-action")
        content.append(save_button)
        test_button = Gtk.Button(label="Test Against Current Releases")
        content.append(test_button)
        test_result = Gtk.Label(
            label="Refresh release feeds to test rules against current results.",
            xalign=0, wrap=True,
        )
        test_result.add_css_class("dim-label")
        content.append(test_result)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")

        def clear_editor():
            editing["id"] = None
            name_entry.set_text("")
            value_entry.set_text("")
            field_dropdown.set_selected(0)
            action_dropdown.set_selected(0)
            save_button.set_label("Add Rule")

        def reload_rules():
            child = rule_list.get_first_child()
            while child is not None:
                next_child = child.get_next_sibling()
                rule_list.remove(child)
                child = next_child
            try:
                rules = self.release_rule_store.load()
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not load rules: {error}"))
                return ()
            for index, rule in enumerate(rules):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                toggle = Gtk.CheckButton()
                toggle.set_active(rule.enabled)
                toggle.set_tooltip_text("Enable or disable this rule")
                toggle.connect(
                    "toggled",
                    lambda button, item=rule: update_rule(item.rule_id, enabled=button.get_active()),
                )
                row.append(toggle)
                summary = Gtk.Label(
                    label=f"{index + 1}. {rule.name} · {rule.action.title()} · {rule.field}: {rule.value}",
                    xalign=0, wrap=True,
                )
                summary.set_hexpand(True)
                if not rule.enabled:
                    summary.add_css_class("dim-label")
                row.append(summary)
                up_button = Gtk.Button.new_from_icon_name("go-up-symbolic")
                up_button.set_tooltip_text("Move rule up")
                up_button.set_sensitive(index > 0)
                up_button.connect("clicked", lambda _button, item=rule: move_rule(item.rule_id, -1))
                row.append(up_button)
                down_button = Gtk.Button.new_from_icon_name("go-down-symbolic")
                down_button.set_tooltip_text("Move rule down")
                down_button.set_sensitive(index < len(rules) - 1)
                down_button.connect("clicked", lambda _button, item=rule: move_rule(item.rule_id, 1))
                row.append(down_button)
                edit_button = Gtk.Button(label="Edit")
                edit_button.connect("clicked", lambda _button, item=rule: edit_rule(item))
                row.append(edit_button)
                remove_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
                remove_button.set_tooltip_text("Remove rule")
                remove_button.connect("clicked", lambda _button, item=rule: remove_rule(item.rule_id))
                row.append(remove_button)
                rule_list.append(row)
            return rules

        def update_rule(rule_id, **changes):
            try:
                self.release_rule_store.update(rule_id, **changes)
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not update rule: {error}"))
                return
            reload_rules()
            self._refresh_release_feeds()

        def edit_rule(rule):
            editing["id"] = rule.rule_id
            name_entry.set_text(rule.name)
            value_entry.set_text(rule.value)
            field_dropdown.set_selected(field_values.index(rule.field))
            action_dropdown.set_selected(action_values.index(rule.action))
            save_button.set_label("Save Changes")

        def move_rule(rule_id, offset):
            try:
                rules = self.release_rule_store.load()
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not load rules: {error}"))
                return
            identifiers = [rule.rule_id for rule in rules]
            index = identifiers.index(rule_id)
            target = index + offset
            if not 0 <= target < len(identifiers):
                return
            identifiers[index], identifiers[target] = identifiers[target], identifiers[index]
            try:
                self.release_rule_store.reorder(identifiers)
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not reorder rules: {error}"))
                return
            reload_rules()
            self._refresh_release_feeds()

        def remove_rule(rule_id):
            try:
                self.release_rule_store.remove(rule_id)
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not remove rule: {error}"))
                return
            if editing["id"] == rule_id:
                clear_editor()
            reload_rules()
            self._refresh_release_feeds()

        def save_rule(_button):
            name = name_entry.get_text().strip()
            value = value_entry.get_text().strip()
            field = field_values[field_dropdown.get_selected()]
            action = action_values[action_dropdown.get_selected()]
            try:
                if editing["id"]:
                    self.release_rule_store.update(
                        editing["id"], name=name, field=field, value=value, action=action,
                    )
                else:
                    self.release_rule_store.add(name, field, value, action)
            except (OSError, ValueError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save rule: {error}"))
                return
            clear_editor()
            reload_rules()
            self._refresh_release_feeds()

        def test_rules(_button):
            try:
                rules = self.release_rule_store.load()
            except (OSError, ValueError) as error:
                test_result.set_label(f"Could not load rules: {error}")
                return
            total = 0
            matches = []
            for result in self.release_results:
                if result.error:
                    continue
                for release in result.releases:
                    total += 1
                    context = {
                        "title": release.entry.title,
                        "release_group": release.metadata.get("release_group"),
                        "resolution": release.metadata.get("resolution"),
                        "source": release.metadata.get("source"),
                        "episode": release.episode,
                        "summary": release.entry.summary,
                        "categories": release.entry.categories,
                    }
                    decision = evaluate_release_rules(context, rules)
                    if decision.status != "unmatched":
                        matches.append((release.entry.title, decision.status, decision.reason))
            if not total:
                test_result.set_label("No current release entries. Refresh your feeds first.")
            elif not matches:
                test_result.set_label(f"No rules matched any of the {total} current releases.")
            else:
                examples = "\n".join(
                    f"• {status.title()}: {title} — {reason}"
                    for title, status, reason in matches[:3]
                )
                test_result.set_label(f"{len(matches)} of {total} releases matched rules.\n{examples}")

        save_button.connect("clicked", save_rule)
        test_button.connect("clicked", test_rules)
        reload_rules()
        dialog.present(self)

    def _show_release_feed_manager(self):
        dialog = Adw.AlertDialog(
            heading="Release Feeds",
            body="Add, edit, enable, or remove RSS and Atom sources. Refresh runs in the background.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        feed_list = Gtk.ListBox()
        feed_list.set_selection_mode(Gtk.SelectionMode.NONE)
        feed_list.add_css_class("boxed-list")
        content.append(feed_list)
        nyaa_search_entry = Gtk.Entry()
        nyaa_search_entry.set_placeholder_text("Search Nyaa releases (e.g. Frieren)")
        content.append(nyaa_search_entry)
        history_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        history_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new(["No recent or saved torrent searches"])
        )
        history_dropdown.set_hexpand(True)
        history_dropdown.set_sensitive(False)
        history_row.append(history_dropdown)
        use_history_button = Gtk.Button(label="Use")
        history_row.append(use_history_button)
        save_history_button = Gtk.Button(label="Save")
        history_row.append(save_history_button)
        remove_history_button = Gtk.Button(label="Remove")
        history_row.append(remove_history_button)
        clear_history_button = Gtk.Button(label="Clear")
        history_row.append(clear_history_button)
        content.append(history_row)
        history_items = []

        def refresh_torrent_search_history():
            history_items.clear()
            try:
                history_items.extend(
                    ("history", query, query)
                    for query in self.search_history_store.list_history("torrent")
                )
                history_items.extend(
                    ("saved", item["name"], item["query"])
                    for item in self.search_history_store.list_saved_searches("torrent")
                )
            except (OSError, SearchHistoryError) as error:
                LOGGER.warning("Could not load torrent search history", exc_info=True)
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Torrent search history unavailable: {error}")
                )
            labels = [
                ("Recent · " if kind == "history" else "Saved · ") + name
                for kind, name, _query in history_items
            ] or ["No recent or saved torrent searches"]
            history_dropdown.set_model(Gtk.StringList.new(labels))
            history_dropdown.set_sensitive(bool(history_items))
            if history_items:
                history_dropdown.set_selected(0)

        refresh_torrent_search_history()
        nyaa_search_button = Gtk.Button(label="Add Nyaa Search Feed")
        nyaa_search_button.set_tooltip_text(
            "Add an English-translated anime RSS search from Nyaa.si."
        )
        content.append(nyaa_search_button)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Feed name")
        content.append(name_entry)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://example.org/releases.xml")
        url_entry.set_input_purpose(Gtk.InputPurpose.URL)
        content.append(url_entry)
        editing = {"url": None}
        save_button = Gtk.Button(label="Add Feed")
        save_button.add_css_class("suggested-action")
        content.append(save_button)
        refresh_button = Gtk.Button(label="Refresh Releases")
        content.append(refresh_button)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")

        def reload_feeds():
            child = feed_list.get_first_child()
            while child is not None:
                next_child = child.get_next_sibling()
                feed_list.remove(child)
                child = next_child
            try:
                feeds = self.rss_feed_store.load()
            except (OSError, FeedParseError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not load feeds: {error}"))
                return
            for feed in feeds:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                label = Gtk.Label(label=feed.name, xalign=0)
                label.set_hexpand(True)
                label.set_ellipsize(3)
                row.append(label)
                state = Gtk.Label(label="Enabled" if feed.enabled else "Disabled")
                state.add_css_class("dim-label")
                row.append(state)
                toggle_button = Gtk.Button(label="Disable" if feed.enabled else "Enable")
                toggle_button.connect(
                    "clicked",
                    lambda _button, item=feed: toggle_feed(item),
                )
                row.append(toggle_button)
                edit_button = Gtk.Button(label="Edit")
                edit_button.connect("clicked", lambda _button, item=feed: begin_edit(item))
                row.append(edit_button)
                remove_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
                remove_button.set_tooltip_text("Remove feed")
                remove_button.connect(
                    "clicked",
                    lambda _button, item=feed: remove_feed(item.url),
                )
                row.append(remove_button)
                feed_list.append(row)

        def add_nyaa_search(_button):
            query = nyaa_search_entry.get_text().strip()
            try:
                url = build_nyaa_search_url(query)
                self.rss_feed_store.add(url, f"Nyaa: {query}")
            except (OSError, ValueError, FeedParseError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not add Nyaa search: {error}"))
                return
            try:
                self.search_history_store.record_query("torrent", query)
                refresh_torrent_search_history()
            except (OSError, SearchHistoryError) as error:
                LOGGER.warning("Could not record torrent search", exc_info=True)
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not save search history: {error}")
                )
            nyaa_search_entry.set_text("")
            reload_feeds()

        def use_torrent_search_history(_button):
            index = history_dropdown.get_selected()
            if index >= len(history_items):
                return
            nyaa_search_entry.set_text(history_items[index][2])
            add_nyaa_search(None)

        def save_torrent_search(_button):
            query = nyaa_search_entry.get_text().strip()
            if not query:
                self.toast_overlay.add_toast(
                    Adw.Toast.new("Enter a Nyaa search query to save first.")
                )
                return
            try:
                saved = self.search_history_store.save_search("torrent", query, query)
            except (OSError, SearchHistoryError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not save search: {error}")
                )
                return
            refresh_torrent_search_history()
            self.toast_overlay.add_toast(
                Adw.Toast.new("Search saved." if saved else "That search is already saved.")
            )

        def remove_torrent_search_history(_button):
            index = history_dropdown.get_selected()
            if index >= len(history_items):
                return
            kind, name, query = history_items[index]
            try:
                removed = (
                    self.search_history_store.remove_history("torrent", query)
                    if kind == "history"
                    else self.search_history_store.remove_saved_search("torrent", name)
                )
            except (OSError, SearchHistoryError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not remove search: {error}")
                )
                return
            refresh_torrent_search_history()
            if removed:
                self.toast_overlay.add_toast(Adw.Toast.new("Search removed."))

        def clear_torrent_search_history(_button):
            try:
                count = self.search_history_store.clear_history("torrent")
            except (OSError, SearchHistoryError) as error:
                self.toast_overlay.add_toast(
                    Adw.Toast.new(f"Could not clear history: {error}")
                )
                return
            refresh_torrent_search_history()
            self.toast_overlay.add_toast(
                Adw.Toast.new(f"Cleared {count} recent searches.")
            )

        use_history_button.connect("clicked", use_torrent_search_history)
        save_history_button.connect("clicked", save_torrent_search)
        remove_history_button.connect("clicked", remove_torrent_search_history)
        clear_history_button.connect("clicked", clear_torrent_search_history)

        def toggle_feed(feed):
            try:
                self.rss_feed_store.update(feed.url, enabled=not feed.enabled)
            except (OSError, FeedParseError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not update feed: {error}"))
                return
            reload_feeds()

        def begin_edit(feed):
            editing["url"] = feed.url
            name_entry.set_text(feed.name)
            url_entry.set_text(feed.url)
            save_button.set_label("Save Changes")

        def remove_feed(url):
            try:
                self.rss_feed_store.remove(url)
            except (OSError, FeedParseError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not remove feed: {error}"))
                return
            if editing["url"] == url:
                editing["url"] = None
                name_entry.set_text("")
                url_entry.set_text("")
                save_button.set_label("Add Feed")
            reload_feeds()

        def save_feed(_button):
            name = name_entry.get_text().strip()
            url = url_entry.get_text().strip()
            try:
                if editing["url"]:
                    self.rss_feed_store.update(editing["url"], name=name, new_url=url)
                else:
                    self.rss_feed_store.add(url, name)
            except (OSError, FeedParseError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save feed: {error}"))
                return
            editing["url"] = None
            name_entry.set_text("")
            url_entry.set_text("")
            save_button.set_label("Add Feed")
            reload_feeds()

        def refresh_now(_button):
            dialog.response("close")
            self._show_release_results()
            self._refresh_release_feeds()

        save_button.connect("clicked", save_feed)
        nyaa_search_button.connect("clicked", add_nyaa_search)
        refresh_button.connect("clicked", refresh_now)
        reload_feeds()
        dialog.present(self)

    def _refresh_release_feeds(self):
        if self._release_refresh_running:
            return GLib.SOURCE_REMOVE
        try:
            feeds = self.rss_feed_store.load()
            if not feeds:
                return GLib.SOURCE_REMOVE
            preferences = self.release_preference_store.load()
            weights = self.release_scoring_store.load()
            minimum_score = self.release_scoring_store.load_minimum_score()
            rules = self.release_rule_store.load()
            anime_preferences = self.anime_release_preference_store.load()
        except (OSError, ValueError) as error:
            LOGGER.warning("Could not prepare release feed refresh: %s", error)
            self.toast_overlay.add_toast(Adw.Toast.new(f"Release refresh unavailable: {error}"))
            return GLib.SOURCE_REMOVE

        candidates = []
        for index, entry in enumerate(self.entries):
            candidates.append({
                "id": entry.storage_id if entry.storage_id is not None else f"library-{index}",
                "title": entry.title,
            })
        self._release_refresh_running = True

        def worker():
            try:
                results = refresh_release_feeds(
                    feeds,
                    candidates,
                    preferences=preferences,
                    weights=weights,
                    minimum_score=minimum_score,
                    rules=rules,
                    anime_preferences=anime_preferences,
                )
                error = None
            except Exception as refresh_error:
                LOGGER.exception("Release feed refresh failed")
                results = ()
                error = str(refresh_error)
            GLib.idle_add(self._finish_release_feed_refresh, results, error)

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _finish_release_feed_refresh(self, results, error):
        self._release_refresh_running = False
        if error:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Release refresh failed: {error}"))
            return GLib.SOURCE_REMOVE
        self.release_results = results
        self._render_release_results()
        for result in results:
            for release in result.releases:
                if release.match_status == "matched" and release.eligible:
                    identity = release.entry.identifier or release.entry.link or release.entry.title
                    key = hashlib.sha256(
                        (result.feed.url + "\0" + str(identity)).encode("utf-8")
                    ).hexdigest()
                    self._record_notification(
                        "release_match", "info", "New matched release",
                        result.feed.name + ": " + release.entry.title, "release:" + key,
                    )
        failed = sum(1 for result in results if result.error)
        count = sum(len(result.releases) for result in results)
        message = f"Found {count} release entries"
        if failed:
            message += f"; {failed} feed(s) failed"
        self.toast_overlay.add_toast(Adw.Toast.new(message + "."))
        return GLib.SOURCE_REMOVE

    def _periodic_release_refresh(self):
        self._refresh_release_feeds()
        return GLib.SOURCE_CONTINUE

    def _refresh_airing_schedule(self):
        """Fetch next-airing metadata in a worker; never block GTK."""
        if self._airing_refresh_running:
            return GLib.SOURCE_REMOVE
        candidates = [
            (entry.storage_id, entry.provider_id)
            for entry in self.entries
            if entry.provider == "anilist"
            and entry.provider_id
            and entry.storage_id is not None
            and str(entry.provider_id).isdigit()
        ]
        current_ids = {storage_id for storage_id, _provider_id in candidates}
        for storage_id in set(self._airing_by_id) - current_ids:
            self._airing_by_id.pop(storage_id, None)
            timer = self._airing_notification_timers.pop(storage_id, None)
            if timer is not None:
                GLib.source_remove(timer[2])
        if not candidates:
            return GLib.SOURCE_REMOVE

        self._airing_refresh_running = True

        def worker():
            client = AniListClient()
            try:
                schedules = client.get_airing_schedules(
                    [int(provider_id) for _storage_id, provider_id in candidates]
                )
                for storage_id, provider_id in candidates:
                    GLib.idle_add(
                        self._set_airing_info,
                        storage_id,
                        schedules.get(int(provider_id)),
                    )
            except (AniListError, ValueError):
                LOGGER.debug("Could not refresh AniList airing schedules", exc_info=True)
            finally:
                GLib.idle_add(self._finish_airing_refresh)

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _periodic_airing_refresh(self):
        self._refresh_airing_schedule()
        return GLib.SOURCE_CONTINUE

    def _finish_airing_refresh(self):
        self._airing_refresh_running = False
        return GLib.SOURCE_REMOVE

    def _set_airing_info(self, storage_id, airing):
        if airing is None:
            changed = self._airing_by_id.pop(storage_id, None) is not None
            timer = self._airing_notification_timers.pop(storage_id, None)
            if timer is not None:
                GLib.source_remove(timer[2])
        else:
            changed = self._airing_by_id.get(storage_id) != airing
            self._airing_by_id[storage_id] = airing
            self._schedule_airing_notification(storage_id, airing)
        if changed:
            self._render_library()
        return GLib.SOURCE_REMOVE

    def _schedule_airing_notification(self, storage_id, airing):
        """Schedule an opt-in reminder without polling or blocking the GTK thread."""
        episode, airing_at = airing
        if (
            isinstance(episode, bool) or not isinstance(episode, int) or episode <= 0
            or isinstance(airing_at, bool) or not isinstance(airing_at, int) or airing_at <= 0
        ):
            return
        previous = self._airing_notification_timers.get(storage_id)
        if previous is not None and previous[:2] == airing:
            return
        if previous is not None:
            GLib.source_remove(previous[2])
        remaining = airing_at - int(time.time())
        if remaining <= 0:
            self._airing_notification_timers.pop(storage_id, None)
            return
        source_id = GLib.timeout_add_seconds(
            min(remaining, 86_400),
            self._on_airing_notification_timer,
            storage_id,
            episode,
            airing_at,
        )
        self._airing_notification_timers[storage_id] = (episode, airing_at, source_id)

    def _on_airing_notification_timer(self, storage_id, episode, airing_at):
        """Fire a reminder at the scheduled time, rearming long waits safely."""
        current = self._airing_by_id.get(storage_id)
        if current != (episode, airing_at):
            self._airing_notification_timers.pop(storage_id, None)
            return GLib.SOURCE_REMOVE
        remaining = airing_at - int(time.time())
        if remaining > 0:
            self._airing_notification_timers.pop(storage_id, None)
            self._schedule_airing_notification(storage_id, current)
            return GLib.SOURCE_REMOVE
        self._airing_notification_timers.pop(storage_id, None)
        entry = next((item for item in self.entries if item.storage_id == storage_id), None)
        if entry is not None:
            self._record_notification(
                "new_episode",
                "info",
                "New episode airing",
                f"{entry.title} episode {episode} is scheduled to air now.",
                f"airing:{storage_id}:{episode}",
            )
        return GLib.SOURCE_REMOVE

    def _update_airing_countdowns(self):
        for key, row in getattr(self, "_row_widgets", {}).items():
            if row.airing_label is not None and key in self._airing_by_id:
                row.airing_label.set_label(
                    format_airing_countdown(*self._airing_by_id[key]) or ""
                )
        for key, card in getattr(self, "_card_widgets", {}).items():
            if card.airing_label is not None and key in self._airing_by_id:
                card.airing_label.set_label(
                    format_airing_countdown(*self._airing_by_id[key]) or ""
                )
        return GLib.SOURCE_CONTINUE

    def _toggle_entry_selection(self, entry: AnimeEntry, selected: bool):
        storage_id = entry.storage_id
        if storage_id is None:
            return
        if selected:
            self._selected_entry_ids.add(storage_id)
        else:
            self._selected_entry_ids.discard(storage_id)
        for widgets in (self._row_widgets, self._card_widgets):
            widget = widgets.get(storage_id)
            if widget is not None and widget.selection_check.get_active() != selected:
                widget.selection_check.set_active(selected)
        self._widget_entries[storage_id] = (
            entry, self._airing_by_id.get(storage_id), selected
        )
        self._update_bulk_bar()

    def _update_bulk_bar(self):
        count = len(self._selected_entry_ids)
        self.bulk_count_label.set_label(f"{count} selected")
        self.bulk_bar.set_visible(count > 0)

    def _clear_bulk_selection(self):
        self._selected_entry_ids.clear()
        for widgets in (self._row_widgets, self._card_widgets):
            for widget in widgets.values():
                if widget.selection_check.get_active():
                    widget.selection_check.set_active(False)
        self._update_bulk_bar()

    def _selected_entries(self):
        return [
            entry for entry in self.entries
            if entry.storage_id is not None
            and entry.storage_id in self._selected_entry_ids
        ]

    def _apply_bulk_status(self, _button):
        entries = self._selected_entries()
        if not entries:
            return
        statuses = [
            WatchStatus.PLANNING, WatchStatus.WATCHING, WatchStatus.COMPLETED,
            WatchStatus.PAUSED, WatchStatus.DROPPED,
        ]
        index = self.bulk_status_dropdown.get_selected()
        if index >= len(statuses):
            return
        status = statuses[index]
        updates = [
            AnimeEntry(
                title=entry.title,
                episodes_total=entry.episodes_total,
                episodes_watched=(
                    entry.episodes_total
                    if status == WatchStatus.COMPLETED and entry.episodes_total is not None
                    else entry.episodes_watched
                ),
                status=status,
                provider=entry.provider,
                provider_id=entry.provider_id,
                cover_image=entry.cover_image,
                storage_id=entry.storage_id,
            )
            for entry in entries
        ]
        try:
            changed = self.storage.update_entries(updates)
        except (ValueError, sqlite3.Error, OSError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Bulk status update failed: {error}"))
            return
        self.entries = self.storage.list_entries()
        for original, updated in zip(entries, updates):
            if original.status != updated.status or original.episodes_watched != updated.episodes_watched:
                self._dispatch_webhook_event(updated, "status")
        self._clear_bulk_selection()
        self._render_library()
        self.toast_overlay.add_toast(Adw.Toast.new(f"Updated status for {changed} anime."))

    def _apply_bulk_progress(self, _button):
        entries = self._selected_entries()
        if not entries:
            return
        try:
            progress = parse_episode_count(
                self.bulk_progress_entry.get_text(),
                field_name="Watched episode count",
            )
            for entry in entries:
                if entry.episodes_total is not None and progress > entry.episodes_total:
                    raise ValueError(
                        f"{entry.title}: watched episodes cannot exceed its total ({entry.episodes_total})."
                    )
            changed = self.storage.update_progress_many(
                {entry.storage_id: progress for entry in entries}
            )
        except (ValueError, sqlite3.Error, OSError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Bulk progress update failed: {error}"))
            return
        self.entries = self.storage.list_entries()
        for entry in entries:
            updated_entry = next((item for item in self.entries if item.storage_id == entry.storage_id), None)
            if updated_entry is not None and updated_entry.episodes_watched != entry.episodes_watched:
                self._dispatch_webhook_event(updated_entry, "progress")
        self._clear_bulk_selection()
        self._render_library()
        self.toast_overlay.add_toast(Adw.Toast.new(f"Updated progress for {changed} anime."))

    def _confirm_bulk_delete(self, _button):
        entries = self._selected_entries()
        if not entries:
            return
        dialog = Adw.AlertDialog(
            heading=f"Delete {len(entries)} anime?",
            body="This permanently removes the selected entries from your local library.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete Selected")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_bulk_delete_response, entries)

    def _on_bulk_delete_response(self, dialog, result, entries):
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            LOGGER.warning("Could not finish bulk-delete confirmation", exc_info=True)
            return
        if response != "delete":
            return
        try:
            removed = self.storage.remove_many(
                entry.storage_id for entry in entries if entry.storage_id is not None
            )
        except (ValueError, sqlite3.Error, OSError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Bulk delete failed: {error}"))
            return
        self.entries = self.storage.list_entries()
        self._selected_entry_ids.clear()
        self._render_library()
        self._update_bulk_bar()
        self.toast_overlay.add_toast(Adw.Toast.new(f"Deleted {removed} anime."))

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
        self._selected_entry_ids.intersection_update(
            key for key in current_keys if isinstance(key, int)
        )
        for key in set(self._airing_by_id) - current_keys:
            self._airing_by_id.pop(key, None)
        for key in set(self._row_widgets) - current_keys:
            row = self._row_widgets.pop(key)
            card = self._card_widgets.pop(key)
            self._widget_entries.pop(key, None)
            if row.get_parent() is not None:
                self.list_box.remove(row.get_parent())
            if card.get_parent() is not None:
                self.grid_flow.remove(card.get_parent())

        query = self.search.get_text().strip().casefold() if hasattr(self, "search") else ""
        visible_count = 0
        ordered_entries = sort_library_entries(
            self.entries,
            sort_by=self.library_sort_mode,
            airing_by_id=self._airing_by_id,
            updated_at_by_id=self.storage.get_updated_at_map(),
        )
        for position, entry in enumerate(ordered_entries):
            key = entry.storage_id if entry.storage_id is not None else ("transient", id(entry))
            row = self._row_widgets.get(key)
            card = self._card_widgets.get(key)

            airing = self._airing_by_id.get(key)
            selected = entry.storage_id in self._selected_entry_ids
            widget_signature = (entry, airing, selected, repr(self.library_layouts))
            if row is None or self._widget_entries.get(key) != widget_signature:
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
                    airing,
                    selected,
                    self._toggle_entry_selection,
                    self._show_external_links,
                    self._show_episode_editor,
                    self.library_layouts["list"],
                )
                card = AnimeCard(
                    entry,
                    self._increment_progress,
                    self._confirm_remove_entry,
                    self._show_edit_dialog,
                    airing,
                    selected,
                    self._toggle_entry_selection,
                    self._show_external_links,
                    self._show_episode_editor,
                    self.library_layouts["grid"],
                )
                card.set_size_request(self.library_layouts["grid"]["widths"]["card_width"], 180)
                self.list_box.insert(row, position)
                self.grid_flow.insert(card, position)
                self._row_widgets[key] = row
                self._card_widgets[key] = card
                self._widget_entries[key] = widget_signature
            else:
                list_child = row.get_parent()
                grid_child = card.get_parent()
                if list_child is not None and list_child.get_index() != position:
                    self.list_box.reorder_child(list_child, position)
                if grid_child is not None and grid_child.get_index() != position:
                    self.grid_flow.reorder_child(grid_child, position)

            is_visible = (
                (self.current_filter == "all" or entry.status.value == self.current_filter)
                and query in entry.title.casefold()
            )
            row.get_parent().set_visible(is_visible)
            card.get_parent().set_visible(is_visible)
            if is_visible:
                visible_count += 1

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
            updated_entry = next((item for item in self.entries if item.storage_id == entry.storage_id), entry)
            self._dispatch_webhook_event(updated_entry, "progress")
            self.toast_overlay.add_toast(Adw.Toast.new(f"Progress updated: {entry.title}"))
        else:
            self.toast_overlay.add_toast(
                Adw.Toast.new("That anime could not be updated. Try again.")
            )

    def _show_anime_download_preferences_dialog(self, entry: AnimeEntry):
        if entry.storage_id is None:
            self.toast_overlay.add_toast(Adw.Toast.new('Save this anime before setting download preferences.'))
            return
        try:
            saved = self.anime_release_preference_store.load_for(entry.storage_id)
        except (OSError, AnimeReleasePreferenceError) as error:
            self.toast_overlay.add_toast(Adw.Toast.new('Could not load per-anime preferences: ' + str(error)))
            return
        dialog = Adw.AlertDialog(
            heading='Download Preferences — ' + entry.title,
            body='These settings override global release preferences for this anime. Empty attributes inherit global defaults.',
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        enabled = Gtk.CheckButton(label='Allow downloads for this anime')
        enabled.set_active(saved['enabled'])
        content.append(enabled)
        size_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        minimum = Gtk.Entry()
        minimum.set_placeholder_text('No minimum')
        minimum.set_text('' if saved['min_file_size_mb'] is None else str(saved['min_file_size_mb']))
        maximum = Gtk.Entry()
        maximum.set_placeholder_text('No maximum')
        maximum.set_text('' if saved['max_file_size_mb'] is None else str(saved['max_file_size_mb']))
        size_grid.attach(Gtk.Label(label='Minimum size (MiB)', xalign=0), 0, 0, 1, 1)
        size_grid.attach(minimum, 1, 0, 1, 1)
        size_grid.attach(Gtk.Label(label='Maximum size (MiB)', xalign=0), 0, 1, 1, 1)
        size_grid.attach(maximum, 1, 1, 1, 1)
        content.append(size_grid)
        attribute_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        for column, heading in enumerate(('Attribute', 'Preferred', 'Rejected')):
            label = Gtk.Label(label=heading, xalign=0)
            label.add_css_class('heading')
            attribute_grid.attach(label, column, 0, 1, 1)
        editors = {}
        saved_attributes = saved['preferences']
        for row, attribute in enumerate(PREFERENCE_ATTRIBUTES, start=1):
            current = saved_attributes.get(attribute, {})
            preferred = Gtk.Entry()
            preferred.set_placeholder_text('Inherit global')
            preferred.set_text(', '.join(current.get('preferred', [])))
            rejected = Gtk.Entry()
            rejected.set_placeholder_text('Inherit global')
            rejected.set_text(', '.join(current.get('rejected', [])))
            attribute_grid.attach(Gtk.Label(label=attribute.replace('_', ' ').title(), xalign=0), 0, row, 1, 1)
            attribute_grid.attach(preferred, 1, row, 1, 1)
            attribute_grid.attach(rejected, 2, row, 1, 1)
            editors[attribute] = (preferred, rejected)
        attribute_scroll = Gtk.ScrolledWindow()
        attribute_scroll.set_min_content_height(220)
        attribute_scroll.set_max_content_height(320)
        attribute_scroll.set_child(attribute_grid)
        content.append(attribute_scroll)
        save = Gtk.Button(label='Save Anime Preferences')
        save.add_css_class('suggested-action')
        reset = Gtk.Button(label='Reset to Global Defaults')
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(save)
        actions.append(reset)
        content.append(actions)
        dialog.set_extra_child(content)
        dialog.add_response('close', 'Close')
        dialog.set_default_response('close')
        dialog.present(self)
        def save_preferences(_button):
            try:
                def parse_size(widget, label):
                    raw = widget.get_text().strip()
                    if not raw:
                        return None
                    return float(raw)
                payload = {
                    'enabled': enabled.get_active(),
                    'min_file_size_mb': parse_size(minimum, 'Minimum'),
                    'max_file_size_mb': parse_size(maximum, 'Maximum'),
                    'preferences': {},
                }
                for attribute, (preferred, rejected) in editors.items():
                    preferred_values = [value.strip() for value in preferred.get_text().split(',') if value.strip()]
                    rejected_values = [value.strip() for value in rejected.get_text().split(',') if value.strip()]
                    if preferred_values or rejected_values:
                        payload['preferences'][attribute] = {'preferred': preferred_values, 'rejected': rejected_values}
                self.anime_release_preference_store.save_for(entry.storage_id, payload)
            except (ValueError, OSError, AnimeReleasePreferenceError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new('Could not save anime preferences: ' + str(error)))
                return
            self.toast_overlay.add_toast(Adw.Toast.new('Anime download preferences saved.'))
            self._refresh_release_feeds()
        def reset_preferences(_button):
            try:
                self.anime_release_preference_store.reset_for(entry.storage_id)
            except (OSError, AnimeReleasePreferenceError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new('Could not reset anime preferences: ' + str(error)))
                return
            self.toast_overlay.add_toast(Adw.Toast.new('Global download preferences restored for this anime.'))
            self._refresh_release_feeds()
            dialog.close()
        save.connect('clicked', save_preferences)
        reset.connect('clicked', reset_preferences)
    def _show_episode_editor(self, entry: AnimeEntry):
        if entry.storage_id is None:
            self.toast_overlay.add_toast(Adw.Toast.new("This library entry has no storage ID."))
            return
        try:
            episode_states = self.storage.list_episode_progress(entry.storage_id)
        except (ValueError, sqlite3.Error) as error:
            self.toast_overlay.add_toast(Adw.Toast.new(f"Could not load episode progress: {error}"))
            return

        legacy_progress = entry.episodes_watched if not episode_states else 0
        episode_limit = entry.episodes_total or MAX_EPISODE_COUNT
        dialog = Adw.AlertDialog(
            heading=f"Episodes — {entry.title}",
            body="Choose an episode and mark it watched or unwatched. Changes are saved immediately.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.append(Gtk.Label(label="Episode number", xalign=0))
        episode_number = Gtk.SpinButton.new_with_range(1, max(1, episode_limit), 1)
        episode_number.set_numeric(True)
        content.append(episode_number)
        watched_check = Gtk.CheckButton(label="Watched")
        content.append(watched_check)
        links_button = Gtk.Button(label="Anime Links")
        links_button.set_tooltip_text("Open AniList, MyAnimeList, Kitsu, and configured links for this anime")
        links_button.connect("clicked", lambda button: self._show_external_links(entry, button))
        content.append(links_button)
        summary = Gtk.Label(xalign=0)
        summary.add_css_class("dim-label")
        content.append(summary)
        dialog.set_extra_child(content)
        dialog.add_response("close", "Close")
        dialog.set_close_response("close")
        dialog.set_default_response("close")

        def current_watched(number: int) -> bool:
            if number in episode_states:
                return episode_states[number]
            return not episode_states and number <= legacy_progress

        def update_summary():
            watched_count = (
                sum(1 for watched in episode_states.values() if watched)
                if episode_states else legacy_progress
            )
            total_text = str(entry.episodes_total) if entry.episodes_total is not None else "unknown"
            summary.set_label(f"{watched_count} episodes watched · {total_text} total")

        def sync_selected_episode(*_args):
            number = episode_number.get_value_as_int()
            watched_check.handler_block(toggle_handler[0])
            watched_check.set_active(current_watched(number))
            watched_check.handler_unblock(toggle_handler[0])

        def on_watched_toggled(check):
            nonlocal legacy_progress, episode_states
            number = episode_number.get_value_as_int()
            try:
                self.storage.set_episode_watched(entry.storage_id, number, check.get_active())
                episode_states = self.storage.list_episode_progress(entry.storage_id)
                legacy_progress = 0
            except (ValueError, sqlite3.Error) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not update episode: {error}"))
                sync_selected_episode()
                return
            self.entries = self.storage.list_entries()
            self._render_library()
            update_summary()

        toggle_handler = [watched_check.connect("toggled", on_watched_toggled)]
        episode_number.connect("value-changed", sync_selected_episode)
        update_summary()
        sync_selected_episode()
        dialog.present(self)

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
        download_preferences_button = Gtk.Button(label='Per-anime Download Preferences')
        download_preferences_button.connect('clicked', lambda _button: self._show_anime_download_preferences_dialog(entry))
        content.append(download_preferences_button)
        trailer_button = Gtk.Button(label="Watch Trailer")
        trailer_button.set_halign(Gtk.Align.START)
        trailer_button.set_visible(False)
        content.append(trailer_button)
        if entry.provider == "anilist" and entry.provider_id and str(entry.provider_id).isdigit():
            def apply_trailer(url):
                if url:
                    trailer_button.set_visible(True)
                    trailer_button.connect(
                        "clicked",
                        lambda _button, trailer_url=url: self._launch_trailer_async(trailer_url),
                    )
                return GLib.SOURCE_REMOVE

            def load_trailer():
                try:
                    metadata = AniListClient().get_anime(int(entry.provider_id))
                    trailer_url = metadata.get("trailer_url")
                    GLib.idle_add(apply_trailer, trailer_url)
                except (AniListError, ValueError):
                    LOGGER.debug("Could not load trailer metadata for %s", entry.title, exc_info=True)

            threading.Thread(target=load_trailer, daemon=True).start()
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
        if edited.episodes_watched != original.episodes_watched or edited.status != original.status:
            self._dispatch_webhook_event(edited, "status" if edited.status != original.status else "progress")
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


    def _launch_trailer_async(self, url):
        """Launch a validated trailer in mpv or the desktop's default URI handler."""
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname not in {
                "youtube.com", "www.youtube.com", "dailymotion.com",
                "www.dailymotion.com", "vimeo.com",
            }:
                raise ValueError("This trailer URL is not supported.")
        except (TypeError, ValueError):
            self.toast_overlay.add_toast(Adw.Toast.new("This trailer URL is invalid."))
            return

        def open_default():
            try:
                Gio.AppInfo.launch_default_for_uri(url, None)
            except GLib.Error as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not open trailer: {error.message}"))
            return GLib.SOURCE_REMOVE

        def worker():
            player = shutil.which("mpv")
            if player:
                try:
                    subprocess.Popen(
                        [player, url],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    return
                except OSError:
                    LOGGER.warning("Could not start mpv; falling back to the desktop URI handler", exc_info=True)
            GLib.idle_add(open_default)

        threading.Thread(target=worker, daemon=True).start()

    def _show_season_discovery(self):
        """Browse AniList seasonal charts without blocking the GTK main thread."""
        dialog = Adw.AlertDialog(
            heading="Season Discovery",
            body="Browse seasonal anime, filter the catalogue, and add titles to your local library.",
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_size_request(720, 560)
        season_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        season_dropdown = Gtk.DropDown.new_from_strings(list(SEASONS))
        current_season, current_year = season_for_date()
        season_dropdown.set_selected(SEASONS.index(current_season))
        year_values = list(range(max(1970, current_year - 5), min(2100, current_year + 2) + 1))
        year_dropdown = Gtk.DropDown.new_from_strings([str(value) for value in year_values])
        year_dropdown.set_selected(year_values.index(current_year))
        load_button = Gtk.Button(label="Load season")
        load_button.add_css_class("suggested-action")
        for widget in (Gtk.Label(label="Season"), season_dropdown, Gtk.Label(label="Year"), year_dropdown, load_button):
            season_row.append(widget)
        content.append(season_row)

        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Search titles or genres")
        search_entry.set_hexpand(True)
        genre_dropdown = Gtk.DropDown.new_from_strings(["All genres"])
        format_dropdown = Gtk.DropDown.new_from_strings(["All formats", "TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA", "MUSIC"])
        status_dropdown = Gtk.DropDown.new_from_strings(["All statuses", "RELEASING", "NOT_YET_RELEASED", "FINISHED", "CANCELLED", "HIATUS"])
        sort_dropdown = Gtk.DropDown.new_from_strings(["Popularity", "Score", "Title", "Airing date"])
        filter_row.append(search_entry)
        filter_row.append(genre_dropdown)
        content.append(filter_row)
        second_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for widget in (format_dropdown, status_dropdown, Gtk.Label(label="Sort"), sort_dropdown):
            second_row.append(widget)
        content.append(second_row)

        status_label = Gtk.Label(label="Choose a season and load its chart.", xalign=0)
        status_label.add_css_class("dim-label")
        content.append(status_label)
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_min_children_per_line(2)
        flow.set_max_children_per_line(4)
        flow.set_row_spacing(10)
        flow.set_column_spacing(10)
        flow.set_valign(Gtk.Align.START)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(390)
        scroll.set_child(flow)
        content.append(scroll)
        dialog.set_extra_child(content)
        state = {"results": [], "loaded_for": None}
        generation = SearchGeneration()

        def render_results(*_args):
            child = flow.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                flow.remove(child)
                child = following
            formats = ["", "TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA", "MUSIC"]
            statuses = ["", "RELEASING", "NOT_YET_RELEASED", "FINISHED", "CANCELLED", "HIATUS"]
            sorts = ["popularity", "score", "title", "airing_date"]
            genre_values = [""] + sorted({
                str(value) for item in state["results"]
                for value in (item.get("genres") if isinstance(item.get("genres"), list) else [])
            }, key=str.casefold)
            gi, fi, si, oi = genre_dropdown.get_selected(), format_dropdown.get_selected(), status_dropdown.get_selected(), sort_dropdown.get_selected()
            visible = filter_season_results(
                state["results"], query=search_entry.get_text(),
                genre=genre_values[gi] if gi < len(genre_values) else "",
                format_name=formats[fi] if fi < len(formats) else "",
                status=statuses[si] if si < len(statuses) else "",
                sort_by=sorts[oi] if oi < len(sorts) else "popularity",
            )
            status_label.set_label(f"{len(visible)} of {len(state['results'])} anime")
            for item in visible:
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                card.add_css_class("card")
                for side in ("top", "bottom", "start", "end"):
                    getattr(card, "set_margin_" + side)(6)
                poster = Gtk.Picture()
                poster.set_size_request(112, 150)
                poster.set_content_fit(Gtk.ContentFit.COVER)
                poster.set_can_shrink(True)
                poster.set_halign(Gtk.Align.CENTER)
                _load_cover_async(poster, item.get("cover_image"))
                card.append(poster)
                title = Gtk.Label(label=item.get("title") or "Untitled anime", wrap=True)
                title.add_css_class("heading")
                title.set_justify(Gtk.Justification.CENTER)
                card.append(title)
                details = [str(item.get("format") or "Unknown format"), str(item.get("status") or "Unknown status").replace("_", " ").title()]
                if item.get("episodes"):
                    details.append(f"{item['episodes']} episodes")
                if item.get("average_score") is not None:
                    details.append(f"Score {item['average_score']}/100")
                if item.get("genres"):
                    details.append(", ".join(str(value) for value in item["genres"][:3]))
                detail_label = Gtk.Label(label=" · ".join(details), wrap=True, justify=Gtk.Justification.CENTER)
                detail_label.add_css_class("dim-label")
                detail_label.add_css_class("caption")
                card.append(detail_label)
                actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                if item.get("site_url"):
                    actions.append(Gtk.LinkButton.new_with_label(item["site_url"], "AniList"))
                if item.get("trailer_url"):
                    trailer_button = Gtk.Button(label="Watch Trailer")
                    trailer_button.connect(
                        "clicked",
                        lambda _button, url=item["trailer_url"]: self._launch_trailer_async(url),
                    )
                    actions.append(trailer_button)
                add_button = Gtk.Button(label="Add to library")
                add_button.add_css_class("suggested-action")

                def add_result(_button, anime=item, target=add_button):
                    media_id = anime.get("id")
                    if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0:
                        self.toast_overlay.add_toast(Adw.Toast.new("AniList returned an invalid anime ID."))
                        return
                    if any(entry.provider == "anilist" and entry.provider_id == str(media_id) for entry in self.entries):
                        target.set_label("Already added")
                        target.set_sensitive(False)
                        return
                    try:
                        entry = AnimeEntry(
                            title=anime.get("title") or "Untitled anime",
                            episodes_total=anime.get("episodes"),
                            status=WatchStatus.PLANNING,
                            provider="anilist",
                            provider_id=str(media_id),
                            cover_image=anime.get("cover_image"),
                        )
                    except ValueError as error:
                        self.toast_overlay.add_toast(Adw.Toast.new(str(error)))
                        return
                    self._save_new_entry(entry)
                    if any(saved.provider == "anilist" and saved.provider_id == str(media_id) for saved in self.entries):
                        target.set_label("Added")
                        target.set_sensitive(False)

                add_button.connect("clicked", add_result)
                if any(entry.provider == "anilist" and entry.provider_id == str(item.get("id")) for entry in self.entries):
                    add_button.set_label("Already added")
                    add_button.set_sensitive(False)
                actions.append(add_button)
                card.append(actions)
                flow.append(card)

        def update_genres(results):
            genres = sorted({
                str(value) for item in results
                for value in (item.get("genres") if isinstance(item.get("genres"), list) else [])
            }, key=str.casefold)
            genre_dropdown.set_model(Gtk.StringList.new(["All genres", *genres]))
            genre_dropdown.set_selected(0)

        def apply_results(results, request_id, season_key):
            if not generation.is_current(request_id):
                return GLib.SOURCE_REMOVE
            state["results"] = results
            state["loaded_for"] = season_key
            update_genres(results)
            status_label.set_label(f"Loaded {len(results)} anime.")
            load_button.set_sensitive(True)
            load_button.set_label("Refresh season")
            render_results()
            return GLib.SOURCE_REMOVE

        def show_error(message, request_id):
            if not generation.is_current(request_id):
                return GLib.SOURCE_REMOVE
            state["results"] = []
            render_results()
            status_label.set_label("Could not load this season. " + message)
            load_button.set_sensitive(True)
            load_button.set_label("Retry")
            return GLib.SOURCE_REMOVE

        def load_season(_button=None):
            si, yi = season_dropdown.get_selected(), year_dropdown.get_selected()
            if si >= len(SEASONS) or yi >= len(year_values):
                return
            season, year = SEASONS[si], year_values[yi]
            season_key = (season, year)
            force_refresh = state["loaded_for"] == season_key
            request_id = generation.begin()
            load_button.set_sensitive(False)
            load_button.set_label("Loading…")
            status_label.set_label(f"Loading {season.title()} {year} from AniList…")
            def worker():
                try:
                    results = AniListClient().search_season(
                        season, year, refresh=force_refresh
                    )
                    GLib.idle_add(apply_results, results, request_id, season_key)
                except (AniListError, ValueError) as error:
                    GLib.idle_add(show_error, str(error), request_id)
            threading.Thread(target=worker, daemon=True).start()

        load_button.connect("clicked", load_season)
        for dropdown in (genre_dropdown, format_dropdown, status_dropdown, sort_dropdown):
            dropdown.connect("notify::selected", render_results)
        search_entry.connect("search-changed", render_results)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        dialog.present(self)
        load_season()

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

        history_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        history_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new(["No recent or saved searches"])
        )
        history_dropdown.set_hexpand(True)
        history_dropdown.set_sensitive(False)
        history_row.append(history_dropdown)
        use_history_button = Gtk.Button(label="Use")
        history_row.append(use_history_button)
        save_history_button = Gtk.Button(label="Save")
        history_row.append(save_history_button)
        remove_history_button = Gtk.Button(label="Remove")
        history_row.append(remove_history_button)
        clear_history_button = Gtk.Button(label="Clear")
        history_row.append(clear_history_button)
        search_page.append(history_row)
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
        trailer_button = Gtk.Button(label="Watch Trailer")
        trailer_button.set_halign(Gtk.Align.START)
        trailer_button.set_visible(False)
        details_page.append(trailer_button)

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
        trailer_button.connect(
            "clicked",
            lambda _button: self._launch_trailer_async(catalogue_state["selected"]["trailer_url"])
            if catalogue_state["selected"] and catalogue_state["selected"].get("trailer_url")
            else None,
        )
        search_generation = SearchGeneration()
        history_items = []

        def refresh_search_history():
            history_items.clear()
            try:
                for query in self.search_history_store.list_history("anilist"):
                    history_items.append(("history", query, query))
                for item in self.search_history_store.list_saved_searches("anilist"):
                    history_items.append(("saved", item["name"], item["query"]))
            except (OSError, SearchHistoryError) as error:
                LOGGER.warning("Could not load search history", exc_info=True)
                self.toast_overlay.add_toast(Adw.Toast.new(f"Search history unavailable: {error}"))
            labels = [
                ("Recent · " if kind == "history" else "Saved · ") + name
                for kind, name, _query in history_items
            ] or ["No recent or saved searches"]
            history_dropdown.set_model(Gtk.StringList.new(labels))
            history_dropdown.set_sensitive(bool(history_items))
            if history_items:
                history_dropdown.set_selected(0)

        refresh_search_history()

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
                trailer_button.set_visible(False)
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
            trailer_button.set_visible(bool(item.get("trailer_url")))
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
            try:
                self.search_history_store.record_query("anilist", query)
                refresh_search_history()
            except (OSError, SearchHistoryError) as error:
                LOGGER.warning("Could not record AniList search", exc_info=True)
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save search history: {error}"))
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

        def use_history_search(_button):
            index = history_dropdown.get_selected()
            if index >= len(history_items):
                return
            catalogue_search.set_text(history_items[index][2])
            start_catalogue_search(None)

        def save_current_search(_button):
            query = catalogue_search.get_text().strip()
            if not query:
                self.toast_overlay.add_toast(Adw.Toast.new("Enter a query to save first."))
                return
            try:
                saved = self.search_history_store.save_search("anilist", query, query)
            except (OSError, SearchHistoryError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not save search: {error}"))
                return
            refresh_search_history()
            self.toast_overlay.add_toast(
                Adw.Toast.new("Search saved." if saved else "That search is already saved.")
            )

        def remove_selected_search(_button):
            index = history_dropdown.get_selected()
            if index >= len(history_items):
                return
            kind, name, query = history_items[index]
            try:
                removed = (
                    self.search_history_store.remove_history("anilist", query)
                    if kind == "history"
                    else self.search_history_store.remove_saved_search("anilist", name)
                )
            except (OSError, SearchHistoryError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not remove search: {error}"))
                return
            refresh_search_history()
            if removed:
                self.toast_overlay.add_toast(Adw.Toast.new("Search removed."))

        def clear_search_history(_button):
            try:
                count = self.search_history_store.clear_history("anilist")
            except (OSError, SearchHistoryError) as error:
                self.toast_overlay.add_toast(Adw.Toast.new(f"Could not clear history: {error}"))
                return
            refresh_search_history()
            self.toast_overlay.add_toast(Adw.Toast.new(f"Cleared {count} recent searches."))

        use_history_button.connect("clicked", use_history_search)
        save_history_button.connect("clicked", save_current_search)
        remove_history_button.connect("clicked", remove_selected_search)
        clear_history_button.connect("clicked", clear_search_history)

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
        self._refresh_airing_schedule()
        self.current_filter = "all"
        self.filter_buttons["all"].set_active(True)
        self.search.set_text("")
        self._render_library()
        self.toast_overlay.add_toast(Adw.Toast.new(f"Added {entry.title} to your library."))

