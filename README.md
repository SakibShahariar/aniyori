# Aniyori

A native Linux anime tracker built with Python, GTK 4, PyGObject, and libadwaita.

## Project goals

- Track an anime library with AniList as the first provider.
- Keep provider integrations behind a modular service layer.
- Offer compact-list and grid library views.
- Keep the application lightweight, native, accessible, and keyboard-friendly.

## Release notes

The initial `v0.1.0` release notes are being prepared in [CHANGELOG.md](CHANGELOG.md). Publication is intentionally blocked until the mandatory live GTK desktop validation is recorded; no tag or release has been created.

## Development status

See the [live desktop validation checklist](docs/qa/live-desktop-checklist.md) for the remaining GTK, accessibility, integration, and release-gate checks.

**Early development.** The GTK/libadwaita library UI, SQLite storage, offline unit tests, and public AniList catalogue client are in place. AniList account sign-in, user-list import, and synchronization are not implemented yet.

## Current features

- **Library:** manual and AniList-backed entries, aggregate and per-episode watched tracking, status filters, list/grid views, bulk status/progress/delete actions, and statistics.
- **AniList:** cached catalogue search, seasonal discovery charts for current/upcoming/past seasons, title/genre search, format/status filters, popularity/score/title/date sorting, AniList recent and saved search queries, next-episode countdowns, batched background airing refresh (up to 50 AniList IDs per request), and offline metadata fallback, and validated trailer actions in catalogue details and seasonal cards.
- **Local media:** configurable folders, recursive video discovery, filename recognition, available/missing/next episode summaries, and opt-in mpv/VLC playback progress detection.
- **Preferences:** saved share-format templates with live preview, release-attribute preferences, explainable release-quality scoring, and ordered smart release rules.
- **Release discovery:** Nyaa.si search and configurable RSS/Atom feeds, release metadata, library matching, filtering, sorting, and rule-based selection.
- **Download handoff:** validated magnet links through the desktop's default torrent application or explicit qBittorrent WebUI submission.
- **Download Queue:** qBittorrent queue status, progress, transfer rates, ETA, pause/resume, failed-torrent recheck, and removal that preserves downloaded files by default.
- **External links:** built-in AniList, MyAnimeList, and Kitsu links plus configurable HTTP(S) templates from library rows/cards and the episode editor.
- **Library:** sortable list/grid views with status filters, local SQLite watch history, JSON/CSV export, and full database/configuration backups.

Library entries remain local. The desktop interface still needs a launch and interaction test on a Linux session.

## Custom library layout

Choose **Customize Library Layout** from the main menu to configure list and grid views independently. Show or hide status, progress, source, and airing metadata; reorder those fields; and adjust list-column widths or grid-card width. The title remains visible at the start of each item. **Reset List Defaults** and **Reset Grid Defaults** restore only the selected view without changing the other view or the library data. Preferences are saved in `~/.config/aniyori/library-layout.json`.

## Season discovery

Open **Season Discovery** from the main menu to browse the current, upcoming, or past AniList seasons. Choose a season and year, then search titles/genres, filter by genre, format, or airing status, and sort by popularity, score, title, or next airing date. Each result includes available cover art and metadata, an AniList link, and an **Add to library** action. Seasonal catalogue requests run in the background and use the local metadata cache as an offline fallback. The Refresh season action bypasses a fresh cache entry. This uses AniList's public catalogue; it does not sign in or synchronize an AniList account list.

## Privacy and local data

Aniyori is currently a local library tracker. The library database and watch history are stored on your
device; AniList account sign-in and authenticated library synchronization are not
implemented. The public AniList catalogue client does not store OAuth tokens.

### Network requests

- **AniList:** catalogue searches send the search text to AniList's public GraphQL
  API. Opening or refreshing catalogue details sends the corresponding media ID.
  Available trailers can be launched with mpv (when installed) or the default URI handler.
- **External links:** MyAnimeList and Kitsu search links send the anime title to the
  selected website through your default browser. AniList links use the stored ID;
  custom link templates open only when explicitly selected.
- **Cover images:** when a cover is not already cached, Aniyori downloads it over
  HTTPS from an AniList-hosted image URL.
- **RSS/Atom:** Aniyori contacts the HTTP(S) feed URLs you configure when you
  refresh release feeds. Those feed providers receive the normal request metadata
  associated with an HTTP request.

Aniyori does not upload the local library database as part of these catalogue or
feed requests. Search history and feed configuration are stored locally.

- **Notifications:** matched releases, opt-in new-episode airing reminders (disabled by default), download failures, webhook delivery errors, and backup/restore events are saved locally in `~/.config/aniyori/notifications.json`. Event types, minimum severity, and optional desktop notifications are configurable. Repeated matched releases and identical failure reports are deduplicated.
- **Local player detection:** only when explicitly enabled, Aniyori reads mpv/VLC MPRIS metadata for local file playback. It matches filenames conservatively and updates progress only after at least 90% of the media duration; remote URLs and unrecognized or ambiguous files are ignored. Playback metadata is not uploaded.
- **Network settings:** optional HTTP(S) proxy, request timeout, bounded retry count for read-only requests, and custom CA bundle settings are stored in `~/.config/aniyori/network.json`. TLS certificate verification is always enabled; insecure verification bypasses are not supported. Proxy credentials are not accepted.
- **HTTP webhooks:** only when you explicitly configure and enable an endpoint, Aniyori sends JSON progress/status events to that URL. Webhook endpoints, custom headers, and their values are stored in `~/.config/aniyori/webhooks.json` with owner-only file permissions. Requests use the system's normal TLS certificate validation for HTTPS; redirects are not followed, and failed deliveries are logged without interrupting library updates.
- **Magnet handoff:** Aniyori opens a validated magnet URI only when you explicitly
  choose the desktop-handler action.
- **qBittorrent:** when you explicitly choose **Send to qBittorrent**, Aniyori sends
  the selected magnet to the WebUI address you configured. The WebUI receives the
  release URI and normal request metadata. Passwords are stored in the desktop
  Secret Service through `secret-tool`, never in Aniyori's plaintext settings.
  Non-secret connection preferences are saved in
  `~/.config/aniyori/qbittorrent.json`. Remote WebUI connections require HTTPS.
  If the Secret Service is unavailable, API submission is disabled; the generic
  desktop magnet handoff remains available.

Feed refresh, rule evaluation, and sorting never submit downloads automatically.

### Where data is stored

Paths follow the XDG Base Directory environment variables. If a variable is unset
or points to a relative path, Aniyori uses the standard home-directory default.

| Data | Default location |
| --- | --- |
| Library database | `~/.local/share/aniyori/library.sqlite3` |
| Preferences and saved data | `~/.config/aniyori/` |
| qBittorrent connection preferences (no password) | `~/.config/aniyori/qbittorrent.json` |
| Custom external-link templates | `~/.config/aniyori/external-links.json` |
| HTTP webhook endpoints and custom headers | `~/.config/aniyori/webhooks.json` |
| Proxy, timeout, retry, and CA bundle preferences | `~/.config/aniyori/network.json` |
| Profile registry | `~/.config/aniyori/profiles.json` |
| List/grid layout preferences | `~/.config/aniyori/library-layout.json` |
| Local recognition exclusions | `~/.config/aniyori/recognition-exclusions.json` |
| Local player detection preference | `~/.config/aniyori/player-detection.json` |
| Per-anime release preferences | `~/.config/aniyori/anime-release-preferences.json` |
| AniList metadata cache | `~/.cache/aniyori/metadata/` |
| Cover image cache | `~/.cache/aniyori/covers/` |

The configuration directory contains saved RSS feed URLs, search history, ordered
release rules, release preferences, release-scoring settings, share-template
settings, custom external links, recognition exclusions, per-anime release overrides, and qBittorrent connection preferences. Full
backups include the SQLite library and regular files in this configuration directory.
qBittorrent passwords are kept separately in the desktop Secret Service and are not
exported; configure qBittorrent credentials again when restoring on another desktop.
The metadata and cover directories contain
cached remote data and images; they can be cleared without deleting the library
database or preferences.

### Settings profiles and portable mode

By default, the **Default** profile continues to use the standard XDG data, config, and cache directories, preserving existing installations. Create named profiles from **Profiles & Portable Mode**; each named profile gets separate library, configuration, and cache roots under the corresponding XDG `aniyori/profiles/<profile-id>/` directories. Select a profile and restart Aniyori to activate it. Removing a profile deletes only that profile's isolated data; the Default profile cannot be removed.

To enable portable mode, place an empty `.aniyori-portable` marker file beside `main.py` before launching Aniyori. On startup, Aniyori then uses a `portable-data/` directory beside the application for its data, config, cache, and profile registry. The application directory must be writable; if it is not, startup fails with a clear error rather than silently writing data elsewhere. An alternate portable root can be selected with `ANIYORI_PORTABLE_DIR`. Portable mode does not automatically copy existing XDG data; create a full Aniyori backup first and restore it after the first portable-mode launch if you want to migrate your existing library and settings.

### Removing local data

Close Aniyori first. To remove all of its local data, delete its `aniyori`
subdirectory from each of the XDG data, config, and cache directories. With the
default XDG locations, these are:

```text
~/.local/share/aniyori/
~/.config/aniyori/
~/.cache/aniyori/
```

This permanently deletes the local library, saved preferences and history, and
cached metadata and images. Back up the library database first if you may want to
restore it later. To remove a saved qBittorrent password too, use **Configure
qBittorrent → Remove connection** before deleting these directories; removing the
configuration directory alone does not remove the keyring entry.

## Requirements

- Python 3.10+
- GTK 4.8 or newer
- PyGObject
- libadwaita 1.5 or newer (required for `Adw.AlertDialog`)
- Optional for qBittorrent WebUI integration: `secret-tool` and an unlocked
  freedesktop Secret Service provider (for example, GNOME Keyring or a compatible
  KWallet setup). Without these, use the desktop magnet-link handoff.

The system-package instructions below target current releases with libadwaita 1.5+:
Debian 13+, Ubuntu 26.04+, Fedora 43+, or Arch Linux rolling. Older Debian/Ubuntu
releases may ship libadwaita versions too old for Aniyori's dialogs.

Install system dependencies:

**Debian 13+ / Ubuntu 26.04+**
```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

**Fedora 43+**
```bash
sudo dnf install python3 python3-gobject gtk4 libadwaita
```

**Arch Linux (rolling)**
```bash
sudo pacman -S python python-gobject gtk4 libadwaita
```

For optional qBittorrent WebUI credential storage, also install the `secret-tool`
command and configure an unlocked Secret Service provider:

- Debian / Ubuntu: `sudo apt install libsecret-tools`
- Fedora: `sudo dnf install libsecret`
- Arch Linux: `sudo pacman -S libsecret`

Run the application from the repository root:

```bash
python3 main.py
```

## Design principles

- Use system/theme colors instead of hard-coded app-wide colors.
- Keep network and provider logic separate from UI code.
- Make features testable in small milestones.
- Do not stream or host anime content; this is a tracking application.

## License

Aniyori is licensed under the GNU General Public License v3.0 or, at your option,
any later version. The complete license text is available in [LICENSE](LICENSE).

SPDX-License-Identifier: GPL-3.0-or-later

Copyright (C) 2026 Sakib Shahariar

## Roadmap

- [ ] AniList authentication and account synchronization
- [x] RSS/Atom release monitoring, smart rules, and explicit qBittorrent download-client handoff (live desktop verification pending)
- [ ] Playback detection and watch-history integration
- [ ] Packaging and release workflow
