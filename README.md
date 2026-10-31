# Aniyori

A native Linux anime tracker built with Python, GTK 4, PyGObject, and libadwaita.

## Project goals

- Track an anime library with AniList as the first provider.
- Keep provider integrations behind a modular service layer.
- Offer compact-list and grid library views.
- Keep the application lightweight, native, accessible, and keyboard-friendly.

## Development status

**Early development.** The GTK/libadwaita library UI, SQLite storage, offline unit tests, and public AniList catalogue client are in place. AniList account sign-in, user-list import, and synchronization are not implemented yet.

## Current features

- **Library:** manual and AniList-backed entries, progress tracking, status filters, list/grid views, bulk status/progress/delete actions, and statistics.
- **AniList:** cached catalogue search, recent and saved search queries, next-episode countdowns, and offline metadata fallback.
- **Local media:** configurable folders, recursive video discovery, filename recognition, and available/missing/next episode summaries.
- **Preferences:** saved share-format templates with live preview, release-attribute preferences, and explainable release-quality scoring helpers.
- **Data:** local SQLite storage, JSON/CSV export, and validated library import.

Library entries remain local. The desktop interface still needs a launch and interaction test on a Linux session.

## Requirements

- Python 3.10+
- GTK 4
- PyGObject
- libadwaita

Install system dependencies:

**Debian / Ubuntu**
```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

**Fedora**
```bash
sudo dnf install python3 python3-gobject gtk4 libadwaita
```

**Arch Linux**
```bash
sudo pacman -S python python-gobject gtk4 libadwaita
```

Run the application:

```bash
python3 main.py
```

## Design principles

- Use system/theme colors instead of hard-coded app-wide colors.
- Keep network and provider logic separate from UI code.
- Make features testable in small milestones.
- Do not stream or host anime content; this is a tracking application.

## Roadmap

- [ ] AniList authentication and account synchronization
- [ ] RSS feeds, torrent search, and download-client integration
- [ ] Playback detection and watch-history integration
- [ ] Packaging and release workflow
