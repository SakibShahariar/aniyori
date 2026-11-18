"""GTK dialog for connecting and importing an AniList account."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from .services.anilist import AniListClient
from .services.anilist_account import (
    AniListAccountError,
    AniListAccountSettingsStore,
    build_authorization_url,
    parse_access_token,
    import_entry_from_anilist,
    build_sync_plan,
    local_entry_sync_payload,
    local_entry_from_remote,
    DEFAULT_CLIENT_ID,
)
from .services.credentials import CredentialStoreError, SecretServiceCredentialStore



def _remote_status_label(status: str) -> str:
    return {
        "CURRENT": "Watching",
        "PLANNING": "Planning",
        "COMPLETED": "Completed",
        "PAUSED": "Paused",
        "DROPPED": "Dropped",
        "REPEATING": "Repeating",
    }.get(status, "Unknown")


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

    dialog = Adw.PreferencesDialog()
    dialog.set_title("AniList Account")
    dialog.set_content_width(640)
    dialog.set_content_height(620)

    page = Adw.PreferencesPage(title="AniList Account", icon_name="user-symbolic")

    account_group = Adw.PreferencesGroup(title="Account")

    import_row = Adw.ActionRow(
        title="Import AniList Library",
        subtitle="Add anime from your list without replacing local entries.",
    )
    import_button = Gtk.Button(label="Import")
    import_button.add_css_class("suggested-action")
    import_button.set_valign(Gtk.Align.CENTER)
    import_button.set_sensitive(False)
    import_row.add_suffix(import_button)
    import_row.set_activatable_widget(import_button)
    account_group.add(import_row)

    sync_row = Adw.ActionRow(
        title="Review Sync",
        subtitle="Compare local and AniList progress before applying any change.",
    )
    sync_button = Gtk.Button(label="Review")
    sync_button.set_valign(Gtk.Align.CENTER)
    sync_button.set_sensitive(False)
    sync_row.add_suffix(sync_button)
    sync_row.set_activatable_widget(sync_button)
    account_group.add(sync_row)

    disconnect_row = Adw.ActionRow(
        title="Disconnect",
        subtitle="Remove the stored token. Your local library is not changed.",
    )
    disconnect_button = Gtk.Button(label="Disconnect")
    disconnect_button.add_css_class("destructive-action")
    disconnect_button.set_valign(Gtk.Align.CENTER)
    disconnect_button.set_sensitive(False)
    disconnect_row.add_suffix(disconnect_button)
    disconnect_row.set_activatable_widget(disconnect_button)
    account_group.add(disconnect_row)
    page.add(account_group)

    setup_group = Adw.PreferencesGroup(
        title="Authorization",
        description=(
            "Set the Redirect URL in AniList Developer Settings to "
            "https://anilist.co/api/v2/oauth/pin. No client secret is needed. "
            "AniList grants broad access; Aniyori only reads and updates your anime list."
        ),
    )
    client_row = Adw.EntryRow(title="Project AniList Client ID")
    client_row.set_text(settings.get("client_id") or DEFAULT_CLIENT_ID)
    client_row.set_input_purpose(Gtk.InputPurpose.DIGITS)
    setup_group.add(client_row)

    authorize_row = Adw.ActionRow(
        title="Open AniList Authorization",
        subtitle="Sign in on AniList, then copy the token from the Auth Pin page.",
    )
    authorize_button = Gtk.Button(label="Open")
    authorize_button.add_css_class("suggested-action")
    authorize_button.set_valign(Gtk.Align.CENTER)
    authorize_row.add_suffix(authorize_button)
    authorize_row.set_activatable_widget(authorize_button)
    setup_group.add(authorize_row)

    token_row = Adw.PasswordEntryRow(title="AniList access token")
    setup_group.add(token_row)

    connect_row = Adw.ActionRow(
        title="Connect Account",
        subtitle="Verify the token and store it in the desktop keyring.",
    )
    connect_button = Gtk.Button(label="Connect")
    connect_button.add_css_class("suggested-action")
    connect_button.set_valign(Gtk.Align.CENTER)
    connect_button.set_sensitive(credential_store is not None)
    connect_row.add_suffix(connect_button)
    connect_row.set_activatable_widget(connect_button)
    setup_group.add(connect_row)
    page.add(setup_group)

    status_group = Adw.PreferencesGroup(title="Status")
    page.add(status_group)

    dialog.add(page)

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
            if viewer_id is not None and credential_store is not None:
                account_group.set_description(f"AniList account: {viewer_name} (ID {viewer_id})")
                import_button.set_sensitive(True)
                sync_button.set_sensitive(True)
                disconnect_button.set_sensitive(True)
                status_group.set_description(
                    "The access token is retrieved from the desktop keyring when an account action starts."
                )
            elif viewer_id is not None:
                account_group.set_description("AniList account needs to be reconnected.")
                import_button.set_sensitive(False)
                sync_button.set_sensitive(False)
                disconnect_button.set_sensitive(False)
                status_group.set_description(initial_keyring_error or "The desktop keyring is unavailable.")
            else:
                account_group.set_description("Not connected to AniList")
                import_button.set_sensitive(False)
                sync_button.set_sensitive(False)
                disconnect_button.set_sensitive(False)
                status_group.set_description(
                    initial_keyring_error or "Your local library remains available offline."
                )
        except (AniListAccountError, CredentialStoreError) as error:
            account_group.set_description("AniList account status unavailable")
            import_button.set_sensitive(False)
            sync_button.set_sensitive(False)
            disconnect_button.set_sensitive(False)
            status_group.set_description(str(error))

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
                    status_group.set_description(str(error))
                else:
                    on_success(result)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(finish)

        threading.Thread(target=worker, daemon=True).start()

    def open_authorization(_button):
        try:
            client_id = client_row.get_text().strip()
            url = build_authorization_url(client_id)
            current = current_settings()
            settings_store.save(
                client_id=client_id,
                viewer_id=current.get("viewer_id"),
                viewer_name=current.get("viewer_name"),
            )
            Gio.AppInfo.launch_default_for_uri(url, None)
            status_group.set_description(
                "Authorize Aniyori in your browser, copy the token shown on the Auth Pin page, "
                "then paste it above."
            )
        except Exception as error:
            status_group.set_description(str(error))

    def connect_account(_button):
        try:
            client_id = client_row.get_text().strip()
            build_authorization_url(client_id)
            token = parse_access_token(token_row.get_text())
        except AniListAccountError as error:
            status_group.set_description(str(error))
            return

        def task():
            client = AniListClient(access_token=token)
            viewer = client.get_viewer()
            account_key = f"anilist:{viewer['id']}"
            if credential_store is None:
                raise CredentialStoreError(
                    initial_keyring_error or "The desktop Secret Service is unavailable."
                )
            previous_settings = settings_store.load()
            previous_id = previous_settings.get("viewer_id")
            previous_key = f"anilist:{previous_id}" if previous_id is not None else None
            previous_token = (
                credential_store.lookup("aniyori", previous_key)
                if previous_key is not None else None
            )
            credential_store.store("aniyori", account_key, token)
            try:
                settings_store.save(
                    client_id=client_id,
                    viewer_id=viewer["id"],
                    viewer_name=viewer["name"],
                )
            except Exception:
                if previous_id == viewer["id"] and previous_token:
                    credential_store.store("aniyori", account_key, previous_token)
                else:
                    credential_store.remove("aniyori", account_key)
                raise
            if previous_key is not None and previous_id != viewer["id"]:
                try:
                    credential_store.remove("aniyori", previous_key)
                except CredentialStoreError:
                    pass
            return viewer

        def connected(viewer):
            token_row.set_text("")
            account_group.set_description(f"Connected as {viewer['name']} (AniList ID {viewer['id']})")
            import_button.set_sensitive(True)
            disconnect_button.set_sensitive(True)
            status_group.set_description("Account connected. Your access token is stored in the desktop keyring.")

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
                media_id = str(remote["media_id"])
                if media_id in existing_ids:
                    skipped += 1
                    continue
                try:
                    entry = import_entry_from_anilist(remote)
                except AniListAccountError:
                    skipped += 1
                    continue
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
            status_group.set_description(
                f"Import complete: added {result['added']} anime; "
                f"left {result['skipped']} existing or unsupported entries unchanged."
            )

        run_background(import_button, "Importing…", task, imported)


    def review_sync(_button):
        def task():
            client, current = stored_client()
            remote_entries = client.get_user_library(current["viewer_id"])
            local_entries = parent.storage.list_entries()
            return build_sync_plan(local_entries, remote_entries)

        def show_plan(plan):
            review = Adw.Dialog()
            review.set_title("Review AniList Sync")
            review.set_content_width(640)
            review.set_content_height(620)
            review_toolbar = Adw.ToolbarView()
            review_header = Adw.HeaderBar()
            review_toolbar.add_top_bar(review_header)
            review_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            review_content.set_margin_top(16)
            review_content.set_margin_bottom(16)
            review_content.set_margin_start(16)
            review_content.set_margin_end(16)

            summary = Gtk.Label(
                label=(
                    f"{len(plan['imports'])} new AniList entries to import · "
                    f"{len(plan['conflicts'])} differences to resolve · "
                    f"{len(plan['local_only'])} local-only entries · "
                    f"{plan['unchanged']} unchanged"
                ),
                xalign=0,
                wrap=True,
            )
            summary.add_css_class("heading")
            review_content.append(summary)

            conflict_choices = []
            if plan["conflicts"]:
                heading = Gtk.Label(label="Different progress or status", xalign=0)
                heading.add_css_class("title-4")
                review_content.append(heading)
                for conflict in plan["conflicts"]:
                    local = conflict["local"]
                    remote = conflict["remote"]
                    remote_status = _remote_status_label(remote["status"])
                    row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                    row.set_margin_bottom(8)
                    label = Gtk.Label(
                        label=(
                            f"{local.title}\n"
                            f"Local: {local.status.value.title()} · {local.episodes_watched} watched\n"
                            f"AniList: {remote_status} · {remote['progress']} watched"
                        ),
                        xalign=0,
                        wrap=True,
                    )
                    row.append(label)
                    choice = Gtk.DropDown.new_from_strings([
                        "Choose how to resolve",
                        "Keep local and update AniList",
                        "Use AniList and update local",
                    ])
                    choice.set_selected(0)
                    row.append(choice)
                    review_content.append(row)
                    conflict_choices.append((conflict, choice))

            local_choices = []
            if plan["local_only"]:
                heading = Gtk.Label(label="Local entries missing from AniList", xalign=0)
                heading.add_css_class("title-4")
                review_content.append(heading)
                for local in plan["local_only"]:
                    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                    label = Gtk.Label(
                        label=f"{local.title} · {local.episodes_watched} watched",
                        xalign=0,
                        wrap=True,
                    )
                    label.set_hexpand(True)
                    row.append(label)
                    choice = Gtk.DropDown.new_from_strings([
                        "Leave local only",
                        "Add back to AniList",
                    ])
                    choice.set_selected(0)
                    row.append(choice)
                    review_content.append(row)
                    local_choices.append((local, choice))

            if plan["imports"]:
                preview_titles = [
                    item["media"].get("title") or "Untitled anime"
                    for item in plan["imports"][:12]
                ]
                remaining = len(plan["imports"]) - len(preview_titles)
                preview_text = ", ".join(preview_titles)
                if remaining:
                    preview_text += f", and {remaining} more"
                note = Gtk.Label(
                    label=(
                        "New entries to import: " + preview_text
                        + ". Existing local entries are never replaced by import."
                    ),
                    xalign=0,
                    wrap=True,
                )
                note.add_css_class("dim-label")
                review_content.append(note)

            review_status = Gtk.Label(xalign=0, wrap=True)
            review_content.append(review_status)
            buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            cancel = Gtk.Button(label="Cancel")
            buttons.append(cancel)
            apply_button = Gtk.Button(label="Apply Sync")
            apply_button.add_css_class("suggested-action")
            buttons.append(apply_button)
            review_content.append(buttons)
            review_scroll = Gtk.ScrolledWindow()
            review_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            review_scroll.set_min_content_height(380)
            review_scroll.set_child(review_content)
            review_toolbar.set_content(review_scroll)
            review.set_child(review_toolbar)

            def apply_sync(_apply_button):
                unresolved = [
                    choice for _conflict, choice in conflict_choices
                    if choice.get_selected() == 0
                ]
                if unresolved:
                    review_status.set_text("Choose a resolution for every differing entry.")
                    return

                resolutions = {
                    conflict["local"].storage_id: choice.get_selected()
                    for conflict, choice in conflict_choices
                }
                restore_remote = {
                    local.storage_id
                    for local, choice in local_choices
                    if choice.get_selected() == 1
                }

                def apply_task():
                    client, current = stored_client()
                    imported = 0
                    updated_local = 0
                    updated_remote = 0
                    skipped = 0
                    for remote in plan["imports"]:
                        try:
                            parent.storage.add(import_entry_from_anilist(remote))
                        except (AniListAccountError, ValueError):
                            skipped += 1
                        else:
                            imported += 1
                    for conflict in plan["conflicts"]:
                        local = conflict["local"]
                        remote = conflict["remote"]
                        if resolutions[local.storage_id] == 1:
                            payload = local_entry_sync_payload(local)
                            client.save_media_list_entry(
                                payload["media_id"], payload["status"], payload["progress"]
                            )
                            updated_remote += 1
                        else:
                            parent.storage.update_entry(
                                local_entry_from_remote(remote, local)
                            )
                            updated_local += 1
                    for local in plan["local_only"]:
                        if local.storage_id in restore_remote:
                            payload = local_entry_sync_payload(local)
                            client.save_media_list_entry(
                                payload["media_id"], payload["status"], payload["progress"]
                            )
                            updated_remote += 1
                    return {
                        "imported": imported,
                        "updated_local": updated_local,
                        "updated_remote": updated_remote,
                        "skipped": skipped,
                    }

                def sync_applied(result):
                    parent.entries = parent.storage.list_entries()
                    parent._render_library()
                    parent._refresh_airing_schedule()
                    review.close()
                    status_group.set_description(
                        f"Sync complete: imported {result['imported']}, "
                        f"updated local {result['updated_local']}, "
                        f"updated AniList {result['updated_remote']}, "
                        f"skipped {result['skipped']}."
                    )

                run_background(apply_button, "Syncing…", apply_task, sync_applied)

            cancel.connect("clicked", lambda _button: review.close())
            apply_button.connect("clicked", apply_sync)
            review.present(parent)

        run_background(sync_button, "Checking…", task, show_plan)

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
            status_group.set_description("AniList disconnected. Your local library was not changed.")

        run_background(disconnect_button, "Disconnecting…", task, disconnected)

    authorize_button.connect("clicked", open_authorization)
    connect_button.connect("clicked", connect_account)
    import_button.connect("clicked", import_library)
    sync_button.connect("clicked", review_sync)
    disconnect_button.connect("clicked", disconnect_account)
    refresh_account_state()
    dialog.present(parent)
