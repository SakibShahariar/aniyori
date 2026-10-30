# Aniyori

A native Linux anime tracker built with Python, GTK 4, PyGObject, and libadwaita.

## Project goals

- Track an anime library with AniList as the first provider.
- Keep provider integrations behind a modular service layer.
- Offer compact-list and grid library views.
- Support progress updates and optional background tracking.
- Follow the user's active GTK theme, including Matugen-generated colors.
- Keep the application lightweight, native, accessible, and keyboard-friendly.

## Development status

**Early development.** The GTK/libadwaita library UI, SQLite storage, offline unit tests, and a public AniList catalogue client are in place. The Add Anime dialog can search AniList and prefill the title and episode count. Authenticated account access and library sync are not implemented yet.

## Current library features

- Add an anime manually with an optional episode total and watch status.
- Search titles and filter by watch status.
- Show AniList cover art in list and grid views, loading images asynchronously and caching them locally.
- Cache AniList search results and details for 24 hours, use stale metadata when offline, and allow callers to force refresh or clear the metadata cache.
- Switch between compact list and grid views.
- Mark one additional episode watched using the `+1` controls.
- Automatically mark an entry Completed when progress reaches its known episode total; Paused and Dropped statuses are preserved when progress changes.
- Store local entries in SQLite under `$XDG_DATA_HOME/aniyori/library.sqlite3`, falling back to `~/.local/share/aniyori/library.sqlite3`.

Library entries are stored locally. Public catalogue search is available, but user-list import/sync is not implemented. The interface still needs a launch and interaction test on a Linux desktop.

## Requirements

- Python 3.10+
- GTK 4
- PyGObject
- libadwaita

On Debian/Ubuntu, system packages commonly include:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
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

- [ ] Milestone 1: GTK/libadwaita application shell
- [ ] Milestone 2: Navigation and library empty state
- [x] Milestone 3a: Public AniList catalogue client and Add Anime search
- [ ] Milestone 3b: AniList authentication and account access
- [ ] Milestone 4: Library import/sync and progress updates
- [ ] Milestone 5: Settings, preferences, and background tracking
- [ ] Milestone 6: Packaging and release workflow
