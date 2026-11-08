# Privacy and local data

Aniyori is a local anime library tracker. Your library database and watch history stay on your device. AniList catalogue search and other network features contact external services only when you use them; the local library database is not uploaded.

## Network activity

- **AniList:** catalogue searches send search text to its public GraphQL API. Opening or refreshing catalogue details sends the relevant media ID. Cover art is downloaded over HTTPS when it is not cached.
- **External links and trailers:** AniList, MyAnimeList, Kitsu, and custom links open through your browser or desktop URI handler. Trailer playback uses mpv when available or the default handler.
- **RSS/Atom:** configured feed URLs are contacted when you refresh release feeds.
- **Local player detection:** when explicitly enabled, Aniyori reads mpv/VLC MPRIS metadata for local playback. It updates progress only after at least 90% of the reported duration; remote URLs and ambiguous files are ignored.
- **qBittorrent:** only when you explicitly submit a release, Aniyori sends its magnet URI to the configured WebUI. Remote WebUI connections require HTTPS. Passwords are stored through the desktop Secret Service, not in plaintext settings or backups.
- **HTTP webhooks:** only when explicitly configured and enabled, progress/status events are sent to the endpoint you choose. HTTPS uses normal certificate validation and redirects are not followed.

Feed refresh, rule evaluation, and sorting never submit downloads automatically. TLS certificate verification remains enabled. Aniyori does not include telemetry.

## Local storage

Paths follow XDG Base Directory settings. With the standard defaults:

| Data | Location |
| --- | --- |
| Library database | `~/.local/share/aniyori/library.sqlite3` |
| Preferences, feeds, history, profiles, and integration settings | `~/.config/aniyori/` |
| Metadata and cover cache | `~/.cache/aniyori/` |

Some settings use separate JSON files inside the configuration directory, including network, webhooks, qBittorrent, layout, and release preferences. qBittorrent passwords are kept separately in the desktop Secret Service.

## Backups and portable mode

Full backups include the SQLite library and regular files in the configuration directory. Secret Service passwords are not exported; configure them again after restoring on another desktop. Cached metadata and covers can be cleared without deleting the library or preferences.

Named profiles use isolated data, config, and cache roots under the corresponding XDG `aniyori/profiles/<profile-id>/` directories. Portable mode can be enabled with an empty `.aniyori-portable` marker beside `main.py`; it stores data under `portable-data/` beside the application. Existing XDG data is not copied automatically.

## Removing local data

Close Aniyori, then remove its `aniyori` directories from the XDG data, config, and cache locations. This permanently deletes the local library, preferences, history, and cached files. Remove a saved qBittorrent password through **Configure qBittorrent → Remove connection** before deleting the configuration directory.
