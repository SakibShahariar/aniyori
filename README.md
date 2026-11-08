# Aniyori

A native anime library and discovery app for Linux, built with Python, GTK 4, and libadwaita.

Aniyori brings your watchlist, seasonal discovery, local media collection, and release workflow together in a desktop app designed for the Linux desktop.

> **Early development · v0.1.0 not released**
>
> The local library, AniList public catalogue, media scanning, release discovery, and download handoff are implemented. AniList account sign-in and list synchronization are not yet available. A real Linux desktop validation is still required before the first release.

## Features

- **Anime library** — Track series and episodes, organize list and grid views, filter and sort entries, and review watch-history statistics.
- **Discover anime** — Search the public AniList catalogue, browse current and past seasons, view details, and add titles to your library.
- **Local media** — Scan folders, recognize episode filenames, inspect available files, and optionally detect progress from mpv or VLC.
- **Find releases** — Search Nyaa.si and configurable RSS/Atom feeds; match releases to your library and apply customizable rules.
- **Download handoff** — Send a selected magnet link to your desktop torrent app or a configured qBittorrent WebUI. Downloads are never submitted automatically.
- **Personalize and back up** — Customize library layouts, configure external links and notifications, export data, and create full backups.

## Installation

Aniyori currently runs from source. Requirements: Python 3.10+, GTK 4.8+, PyGObject, and libadwaita 1.5+.

Install system dependencies:

**Fedora**
```bash
sudo dnf install python3 python3-gobject gtk4 libadwaita
```

**Debian 13+ / Ubuntu 26.04+**
```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

**Arch Linux**
```bash
sudo pacman -S python python-gobject gtk4 libadwaita
```

Then run from the repository root:

```bash
git clone https://github.com/SakibShahariar/aniyori.git
cd aniyori
python3 main.py
```

For qBittorrent WebUI password storage, install `secret-tool` and configure a desktop Secret Service provider. This integration is optional; desktop magnet-link handoff does not require it.

## Documentation

- [Privacy and local data](docs/privacy.md)
- [Live desktop validation checklist](docs/qa/live-desktop-checklist.md)
- [Changelog and release notes](CHANGELOG.md)

## Project status

Aniyori is not yet a finished release. The first release is gated on real-session testing of startup, core workflows, accessibility, and data persistence. See the [validation checklist](docs/qa/live-desktop-checklist.md) for the exact checks. No release tag has been published.

## License

[GPL-3.0-or-later](LICENSE) · Copyright © 2026 Sakib Shahariar
