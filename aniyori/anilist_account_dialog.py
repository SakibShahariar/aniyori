"""GTK dialog for connecting and importing an AniList account."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from .models import AnimeEntry, WatchStatus
from .services.anilist import AniListClient, AniListError
from .services.anilist_account import (
    AniListAccountError,
    AniListAccountSettingsStore,
    build_authorization_url,
    parse_access_token,
)
from .services.credentials import CredentialStoreError, SecretServiceCredentialStore


_STATUS_MAP = {
    "CURRENT": WatchStatus.WATCHING,
    "PLANNING": WatchStatus.PLANNING,
    "COMPLETED": WatchStatus.COMPLETED,
    "PAUSED": WatchStatus.PAUSED,
    "DROPPED": WatchStatus.DROPPED,
    "REPEATING": WatchStatus.WATCHING,
}


def show_anilist_account_dialog(parent) -> None:
    """Show account connection, token storage, and non-destructive import."""
    settings_store = AniListAccountSettingsStore()
    try:
        settings = settings_store.load()
    except AniListAccountError as error:
        parent.toast_overlay.add_toast(Adw.Toast.new(str(error)))
        settings = {"client_id": "", "viewer_id": None, "viewer_name": None}

    try:
        credential_store = SecretServiceCredentialStore()
    except CredentialStoreError as error:
        credential_store = None
        initial_keyring_error = str(error)
    else:
        initial_keyring_error = None

    dialog = Adw.Dialog()
    dialog.set_title("AniList Account")
    dialog.set_content_width(520)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    content.set_margin_top(18)
    content.set_margin_bottom(18)
    content.set_margin_start(18)
    content.set_margin_end(18)

    account_label = Gtk.Label(xalign=0, wrap=True)
    account_label.add_css_class("heading")
    content.append(account_label)

    client_id_label = Gtk.Label(
        label="Project AniList Client ID",
        xalign=0,
    )
    content.append(client_id_label)
    client_id_entry = Gtk.Entry()
    client_id_entry.set_text(settings.get("client_id", ""))
    client_id_entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
    client_id_entry.set_placeholder_text("Numeric public Client ID")
    content.append(client_id_entry)

    redirect_hint = Gtk.Label(
        label=(
            "In AniList Developer Settings, set this application's Redirect URL to "
            "https://anilist.co/api/v2/oauth/pin. The app uses the implicit flow; "
            "no client secret is needed."
        ),
        xalign=0,
        wrap=True,
    )
    redirect_hint.add_css_class("dim-label")
    content.append(redirect_hint)

    authorize_button = Gtk.Button(label="Open AniList Authorization")
    authorize_button.add_css_class("suggested-action")
    content.append(authorize_button)

    token_label = Gtk.Label(label="Paste the access token from AniList", xalign=0)
    content.append(token_label)
    token_entry = Gtk.Entry()
    token_entry.set_visibility(False)
    token_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    token_entry.set_placeholder_text("AniList access token")
    content.append(token_entry)

    connect_button = Gtk.Button(label="Connect Account")
    connect_button.add_css_class("suggested-action")
    content.append(connect_button)

    action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    import_button = Gtk.Button(label="Import AniList Library")
    import_button.set_sensitive(False)
    action_row.append(import_button)
    disconnect_button = Gtk.Button(label="Disconnect")
    disconnect_button.set_sensitive(False)
    action_row.append(disconnect_button)
    content.append(action_row)

    status_label = Gtk.Label(xalign=0, wrap=True)
    status_label.add_css_class("dim-label")
    content.append(status_label)

    close_button = Gtk.Button(label="Close")
    close_button.set_halign(Gtk.Align.END)
    content.append(close_button)

    dialog.set_child(content)

    def current_settings():
        return settings_store.load()

    def stored_client():
        if credential_store is None:
            raise CredentialStoreError(
                initial_keyring_error or "The desktop Secret Service is unavailable."
            )
        current = current_settings()
        viewer_id = current.get("viewer_id")
        if viewer_id is None:
            raise AniListAccountError("Connect an AniList account first.")
        token = credential_store.lookup("aniyori", f"anilist:{viewer_id}")
        if not token:
            raise AniListAccountError("The saved AniList token is unavailable. Connect again.")
        return AniListClient(access_token=token), current

    def refresh_account_state():
        try:
            current = current_settings()
            viewer_id = current.get("viewer_id")
            viewer_name = current.get("viewer_name")
            token_available = False
            if viewer_id is not None and credential_store is not None:
                token_available = bool(
                    credential_store.lookup("aniyori", f"anilist:{viewer_id}")
                )
            if token_available:
                account_label.set_text(f"Connected as {viewer_name} (AniList ID {viewer_id})")
                import_button.set_sensitive(True)
                disconnect_button.set_sensitive(True)
                status_label.set_text("Your AniList token is stored in the desktop keyring.")
            elif viewer_id is not None:
                account_label.set_text("AniList account needs to be reconnected.")
                import_button.set_sensitive(False)
                disconnect_button.set_sensitive(False)
                status_label.set_text("No usable token was found in the desktop keyring.")
            else:
                account_label.set_text("Not connected to AniList")
                import_button.set_sensitive(False)
                disconnect_button.set_sensitive(False)
                status_label.set_text(initial_keyring_error or "Your local library remains available offline.")
        except (AniListAccountError, CredentialStoreError) as error:
            account_label.set_text("AniList account status unavailable")
            import_button.set_sensitive(False)
            disconnect_button.set_sensitive(False)
            status_label.set_text(str(error))

    def run_background(button, working_label, task, on_success):
        original_label = button.get_label()
        button.set_sensitive(False)
        button.set_label(working_label)

        def worker():
            try:
                result = task()
                error = None
            except Exception as caught:
                result = None
                error = caught

            def finish():
                button.set_label(original_label)
                button.set_sensitive(True)
                if error is not None:
                    status_label.set_text(str(error))
                else:
                    on_success(result)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(finish)

        threading.Thread(target=worker, daemon=True).start()

    def open_authorization(_button):
        try:
            client_id = client_id_entry.get_text().strip()
            url = build_authorization_url(client_id)
            current = current_settings()
            settings_store.save(
                client_id=client_id,
                viewer_id=current.get("viewer_id"),
                viewer_name=current.get("viewer_name"),
            )
            Gio.AppInfo.launch_default_for_uri(url, None)
            status_label.set_text(
                "Authorize Aniyori in your browser, copy the token shown on the Auth Pin page, "
                "then paste it above."
            )
        except Exception as error:
            status_label.set_text(str(error))

    def connect_account(_button):
        try:
            client_id = client_id_entry.get_text().strip()
            build_authorization_url(client_id)
            token = parse_access_token(token_entry.get_text())
        except AniListAccountError as error:
            status_label.set_text(str(error))
            return

        def task():
            client = AniListClient(access_token=token)
            viewer = client.get_viewer()
            account_key = f"anilist:{viewer['id']}"
            if credential_store is None:
                raise CredentialStoreError(
                    initial_keyring_error or "The desktop Secret Service is unavailable."
                )
            credential_store.store("aniyori", account_key, token)
            try:
                settings_store.save(
                    client_id=client_id,
                    viewer_id=viewer["id"],
                    viewer_name=viewer["name"],
                )
            except Exception:
                credential_store.remove("aniyori", account_key)
                raise
            return viewer

        def connected(viewer):
            token_entry.set_text("")
            account_label.set_text(f"Connected as {viewer['name']} (AniList ID {viewer['id']})")
            import_button.set_sensitive(True)
            disconnect_button.set_sensitive(True)
            status_label.set_text("Account connected. Your access token is stored in the desktop keyring.")

        run_background(connect_button, "Connecting…", task, connected)

    def import_library(_button):
        def task():
            client, current = stored_client()
            remote_entries = client.get_user_library(current["viewer_id"])
            existing_ids = {
                str(entry.provider_id)
                for entry in parent.storage.list_entries()
                if entry.provider == "anilist" and entry.provider_id
            }
            added = 0
            skipped = 0
            for remote in remote_entries:
                media = remote["media"]
                media_id = str(remote["media_id"])
                if media_id in existing_ids:
                    skipped += 1
                    continue
                total = media.get("episodes")
                progress = remote["progress"]
                if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
                    total = None
                if total is not None and progress > total:
                    total = None
                if progress > 10_000:
                    skipped += 1
                    continue
                entry = AnimeEntry(
                    title=media["title"],
                    episodes_total=total,
                    episodes_watched=progress,
                    status=_STATUS_MAP[remote["status"]],
                    provider="anilist",
                    provider_id=media_id,
                    cover_image=media.get("cover_image"),
                )
                try:
                    parent.storage.add(entry)
                except ValueError:
                    skipped += 1
                else:
                    added += 1
                    existing_ids.add(media_id)
            return {"added": added, "skipped": skipped}

        def imported(result):
            parent.entries = parent.storage.list_entries()
            parent._render_library()
            parent._refresh_airing_schedule()
            status_label.set_text(
                f"Import complete: added {result['added']} anime; "
                f"left {result['skipped']} existing or unsupported entries unchanged."
            )

        run_background(import_button, "Importing…", task, imported)

    def disconnect_account(_button):
        def task():
            current = current_settings()
            viewer_id = current.get("viewer_id")
            if viewer_id is not None and credential_store is not None:
                credential_store.remove("aniyori", f"anilist:{viewer_id}")
            settings_store.save(
                client_id=current.get("client_id", ""),
                viewer_id=None,
                viewer_name=None,
            )
            return True

        def disconnected(_result):
            refresh_account_state()
            status_label.set_text("AniList disconnected. Your local library was not changed.")

        run_background(disconnect_button, "Disconnecting…", task, disconnected)

    authorize_button.connect("clicked", open_authorization)
    connect_button.connect("clicked", connect_account)
    import_button.connect("clicked", import_library)
    disconnect_button.connect("clicked", disconnect_account)
    close_button.connect("clicked", lambda _button: dialog.close())

    refresh_account_state()
    dialog.present(parent)
