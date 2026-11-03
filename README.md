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
- **AniList:** cached catalogue search, AniList recent and saved search queries, next-episode countdowns, and offline metadata fallback.
- **Local media:** configurable folders, recursive video discovery, filename recognition, and available/missing/next episode summaries.
- **Preferences:** saved share-format templates with live preview, release-attribute preferences, and explainable release-quality scoring helpers.
- **Data:** local SQLite storage, JSON/CSV export, and validated library import.

Library entries remain local. The desktop interface still needs a launch and interaction test on a Linux session.

## Privacy and local data

Aniyori is currently a local library tracker. The library database is stored on your
device; AniList account sign-in and authenticated library synchronization are not
implemented. The public AniList catalogue client does not store OAuth tokens.

### Network requests

- **AniList:** catalogue searches send the search text to AniList's public GraphQL
  API. Opening or refreshing catalogue details sends the corresponding media ID.
- **Cover images:** when a cover is not already cached, Aniyori downloads it over
  HTTPS from an AniList-hosted image URL.
- **RSS/Atom:** Aniyori contacts the HTTP(S) feed URLs you configure when you
  refresh release feeds. Those feed providers receive the normal request metadata
  associated with an HTTP request.

Aniyori does not upload the local library database as part of these catalogue or
feed requests. Search history and feed configuration are stored locally.

### Where data is stored

Paths follow the XDG Base Directory environment variables. If a variable is unset
or points to a relative path, Aniyori uses the standard home-directory default.

| Data | Default location |
| --- | --- |
| Library database | `~/.local/share/aniyori/library.sqlite3` |
| Preferences and saved data | `~/.config/aniyori/` |
| AniList metadata cache | `~/.cache/aniyori/metadata/` |
| Cover image cache | `~/.cache/aniyori/covers/` |

The configuration directory contains saved RSS feed URLs, search history, ordered
release rules, release preferences, release-scoring settings, and the share-template setting. The metadata
and cover directories contain cached remote data and images; they can be cleared
without deleting the library database or preferences.

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
restore it later.

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

## License

Aniyori is licensed under the GNU General Public License v3.0 or, at your option,
any later version. The complete license text is available in [LICENSE](LICENSE).

SPDX-License-Identifier: GPL-3.0-or-later

Copyright (C) 2026 Sakib Shahariar

## Roadmap

- [ ] AniList authentication and account synchronization
- [ ] RSS feeds, torrent search, and download-client integration
- [ ] Playback detection and watch-history integration
- [ ] Packaging and release workflow
