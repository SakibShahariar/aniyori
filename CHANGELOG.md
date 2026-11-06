# Changelog

All notable user-facing changes for Aniyori are documented here.

## [0.1.0] — Draft, not released

> This is a release-candidate draft only. Do not publish a tag or GitHub release until the mandatory live Linux desktop validation in issue #81 has passed and is recorded.

### Added

- Local anime library backed by SQLite, with list and grid views, filtering, sorting, statistics, and watch history.
- Per-episode watched/unwatched tracking, rewatch history, and an episode editor while retaining aggregate progress compatibility.
- Public AniList catalogue search, media details, seasonal discovery charts, next-airing information, cover caching, and trailer launching.
- Local media-folder scanning and filename-based episode recognition.
- RSS/Atom release discovery, including Nyaa.si search feeds and user-configured feeds, with release metadata, library matching, filtering, and sorting.
- Ordered smart release rules, global and per-anime release preferences, and explainable release scoring.
- Explicit release handoff through the desktop torrent handler or a configured qBittorrent WebUI. Feed refresh and rule evaluation do not submit downloads automatically.
- Search history and saved searches, configurable external links, and share-message templates.
- JSON/CSV library export and import, full ZIP backup/restore, and profile/portable-mode support.
- Persistent notifications, optional desktop notifications, configurable HTTP webhooks, and shared proxy/TLS/timeout/retry settings.
- Configurable list/grid layouts, including metadata visibility/order, list-column widths, and grid-card width.

### Security and privacy

- Library data and preferences remain local unless a user explicitly configures an external integration or opens a link.
- qBittorrent passwords are stored through the freedesktop Secret Service; they are not written to Aniyori's plaintext settings or included in backups.
- Remote qBittorrent WebUI connections require HTTPS; redirects are rejected for credential-bearing requests.
- TLS certificate verification remains enabled for network requests.
- Release downloads are always explicitly user-selected; automatic RSS submission is not part of this draft.

### Requirements

- Python 3.10 or newer
- GTK 4
- PyGObject
- libadwaita
- Optional qBittorrent API credential storage: `secret-tool` and an unlocked freedesktop Secret Service provider

See the README for distribution package commands and launch instructions.

### Not included / known limitations

- AniList OAuth sign-in, account import, and bidirectional synchronization.
- Automatic local media-player or browser streaming playback detection.
- Automatic application updates and Flatpak packaging.
- Automatic scheduled backups.
- A live desktop compatibility/accessibility certification.

### Release gate

Before publishing `v0.1.0`, launch the app in a real supported Linux desktop session, exercise the main window and core library workflows, verify data persistence across restart, record the tested distribution/session and results, and confirm CI is green for the exact release candidate. Until then this changelog remains an unpublished draft.
