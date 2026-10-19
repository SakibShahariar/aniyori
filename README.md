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

**Early development.** The GTK/libadwaita application shell, initial library list/grid UI, SQLite storage layer, and basic unit tests are in place. AniList integration is still planned and has not been implemented yet.

## Current library features

- Add an anime manually with an optional episode total and watch status.
- Search titles and filter by watch status.
- Switch between compact list and grid views.
- Mark one additional episode watched using the `+1` controls.
- Store local entries in SQLite under `$XDG_DATA_HOME/aniyori/library.sqlite3`, falling back to `~/.local/share/aniyori/library.sqlite3`.

The current library is local-only. It does not yet sync with AniList, and the interface has not yet been verified on a Linux desktop.

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
- [ ] Milestone 3: AniList authentication and API client
- [ ] Milestone 4: Search, library sync, and progress updates
- [ ] Milestone 5: Settings, preferences, and background tracking
- [ ] Milestone 6: Packaging and release workflow
