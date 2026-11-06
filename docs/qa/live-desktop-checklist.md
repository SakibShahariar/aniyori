# Live desktop validation checklist

This checklist collects the manual checks that automated unit tests cannot establish. It is a test plan, **not evidence that any item has passed**. Record the actual environment and observed result before checking off an issue's acceptance criteria.

## Record the test environment

- Distribution and version:
- Desktop environment and version:
- Display server: Wayland / X11:
- GTK version (4.8+ required):
- libadwaita version (1.5+ required):
- Aniyori commit SHA:
- Date and tester:
- Optional services available: mpv, Secret Service provider, qBittorrent WebUI:

Use a disposable test profile or a backup of any library data you care about. Do not use a production qBittorrent queue for destructive tests.

## Startup and core library

- [ ] Launch with `python3 main.py`; confirm the main window appears without traceback, warning dialog, or missing-resource error.
- [ ] Add a manual anime, edit its title/status/progress, close the app, relaunch, and confirm the data persists.
- [ ] Search and filter the library; switch between list and grid views and confirm the same entries remain available.
- [ ] Exercise keyboard focus from the header through search, toolbar, library rows/cards, and menu; confirm focus remains visible and logical.
- [ ] Resize the window down to the supported minimum and back; confirm controls remain reachable and content does not overlap.

## Episode tracking and history — #24, #51

- [ ] Open the Episodes editor for an entry with no explicit episode records but a legacy aggregate progress value; confirm the prior watched count is represented without losing progress.
- [ ] Mark one episode watched, unwatch it, and mark it watched again; confirm aggregate progress and rewatch history are correct.
- [ ] Open Watch History; filter by title, date, and action; remove a selected event and prune older events.
- [ ] Restart and confirm history and per-episode state persist.

## Named library-view presets — #89

- [ ] Save presets from both list and grid modes with different supported filters and sort orders; confirm both list and grid layouts are captured.
- [ ] Apply each preset and switch between list/grid; confirm filters, sorting, column/card layout, and row ordering remain consistent.
- [ ] Confirm search text, selected anime, open dialogs, and saved AniList/Nyaa searches are not included in presets.
- [ ] Rename, duplicate, update, and delete presets; verify case-insensitive duplicate names and invalid/empty/long names show clear feedback.
- [ ] Set a default preset, restart Aniyori, and confirm it is applied; clear the default and confirm the normal library view returns on restart.
- [ ] Delete the active preset and confirm the configured default view is restored without changing library entries or progress.
- [ ] Add/remove anime and change status/progress while a preset is active; confirm the preset remains valid and filters use current library data.
- [ ] Reset list/grid layout settings and confirm saved presets remain intact.
- [ ] Test a preset containing an unsupported filter/sort value and a corrupt preset file; confirm safe fallback and that the library still opens without overwriting the corrupt file.

## Yearly watch-history insights — #88

- [ ] Open Library Statistics and confirm the existing library totals and status counts remain visible.
- [ ] Switch among years with recorded activity and an empty year; confirm the monthly chart and empty-history explanation update.
- [ ] Confirm monthly bars count all recorded history events and their tooltips distinguish episode, rewatch, progress, and status events.
- [ ] Confirm completed anime are listed from completion-status history events and repeated completion events do not duplicate an anime.
- [ ] Confirm estimated time states its per-episode assumption and is not presented as measured playback.
- [ ] Check events around local New Year and a daylight-saving transition; confirm they appear under the correct local calendar date/year.
- [ ] Open the statistics dialog with a large history; confirm the window remains responsive while yearly results load.

## Custom library layout — #65

- [ ] Open Customize Library Layout from the main menu.
- [ ] Hide and show status, progress, source, and airing metadata independently in list and grid views.
- [ ] Change metadata ordering; confirm the title remains visible and first.
- [ ] Change list-column widths and grid-card width; resize the window and confirm usable layout.
- [ ] Reset List Defaults; confirm the grid preferences are unchanged. Then reset Grid Defaults and confirm the list preferences are unchanged.
- [ ] Restart and confirm saved preferences persist.

## AniList discovery, trailers, and external links — #36, #37, #59

- [ ] Open Season Discovery and switch among current, upcoming, and past seasons.
- [ ] Search by title/genre, change filters and sort order, and use Refresh season.
- [ ] Add a seasonal result to the library and confirm duplicate handling is clear.
- [ ] For an anime with supported trailer metadata, use Watch Trailer; verify mpv launch when installed and the default URI handler fallback when it is not. Confirm entries without valid trailer metadata do not show a broken action.
- [ ] Open Anime Links from a library row/card and from the episode editor. Confirm AniList, MyAnimeList, Kitsu, and configured custom links open the expected HTTPS pages.
- [ ] Add/edit/remove a custom link template; confirm unsafe schemes and malformed templates are rejected.

## Local media scanning and exclusions — #52

- [ ] Add a test media folder and run Scan Now.
- [ ] Confirm recognized, ambiguous, and unrecognized files are presented distinctly.
- [ ] Add folder, filename, anime-title, and release-group exclusions; rescan and confirm excluded files show the matching reason and do not enter episode inventory.
- [ ] Edit and remove exclusions; restart and confirm rules persist.

## Local collection insights and offline roots — #87

- [ ] Scan two overlapping roots and confirm each canonical file path contributes to aggregate size once.
- [ ] Confirm per-anime size, aggregate size, source path, and Open Folder actions for matched files.
- [ ] Mark an available local episode watched; confirm it is skipped when selecting the next available unwatched episode.
- [ ] Unplug or unmount one configured drive and scan; confirm the root is reported unavailable and missing/next-unwatched claims are withheld.
- [ ] Reconnect the drive and rescan; confirm its files and size return without changing library progress.
- [ ] Test unreadable directories/files and files deleted during a scan; confirm partial results instead of a fatal error or fabricated size.
- [ ] Test symlink roots, directory loops, file symlinks (including broken links), and links targeting paths outside a configured root; confirm they are not followed.
- [ ] Create a hard link where supported; confirm aliases contribute to aggregate size once by device/inode, and conflicting episode names are withheld from availability totals.
- [ ] Cancel a large scan and change configured roots or library entries during a scan; confirm stale results are discarded and the UI remains responsive.

## Local player detection — #32

- [ ] Enable Local Player Detection from the main menu; confirm it is off by default and can be disabled again.
- [ ] Play a recognized local episode in mpv; confirm progress changes only after playback reaches 90% of the reported duration.
- [ ] Repeat with VLC and confirm the MPRIS player is detected.
- [ ] Play an unrecognized file and an ambiguous title; confirm neither changes library data.
- [ ] Disable detection while a player is open; confirm subsequent playback does not update progress.
- [ ] Test with no session bus, no supported player, and a player that exits; confirm the app remains responsive and no progress is changed.

## RSS discovery and smart rules — #43, #44, #54

- [ ] Add a Nyaa.si RSS search feed and a generic RSS/Atom feed.
- [ ] Refresh feeds; confirm one malformed/unavailable feed does not prevent other feeds from refreshing.
- [ ] Inspect available size, swarm, release-group, resolution, source, and publication metadata.
- [ ] Add Prefer, Include, and Exclude rules; test them against loaded results, reorder them, disable one, and confirm the first matching enabled rule and explanation are shown.
- [ ] Confirm feed refresh and rule evaluation never submit a download automatically.

## qBittorrent and credentials — #45, #56, #57, #63

- [ ] Configure a local/test qBittorrent WebUI connection; test authentication before saving.
- [ ] Confirm credentials are stored in the desktop Secret Service and do not appear in plaintext settings or logs.
- [ ] With the Secret Service locked or unavailable, confirm API submission fails closed and the generic desktop magnet handoff remains available.
- [ ] Submit a harmless test magnet explicitly; confirm it appears in the Download Queue.
- [ ] Verify progress, size, transfer rates, ETA, pause, resume, recheck where applicable, and removal.
- [ ] Remove a test queue item with the default option and confirm downloaded files are retained. Do not test delete-files against valuable data.
- [ ] Set per-anime release preferences and disable downloads for one test entry; confirm ineligible releases cannot be handed off to qBittorrent or the desktop torrent handler.
- [ ] Confirm queue polling stops when its window closes and errors can be retried manually.

## Backup and restore — #46

- [ ] Create a full backup and confirm the archive is created with restrictive permissions.
- [ ] Restore into a disposable profile with the confirmation dialog; verify library entries, episode state, watch history, feeds, rules, and non-secret preferences.
- [ ] Confirm a corrupt or unsafe archive is rejected without replacing the current library.
- [ ] Confirm Secret Service passwords are not exported and must be configured again on another desktop.

## Saved searches — #64

- [ ] Run AniList and Nyaa searches; confirm recent queries appear in their own search domains.
- [ ] Save, reuse, and remove a named search; clear recent history.
- [ ] Confirm reusing a Nyaa search restores a feed but never submits a download.

## Accessibility and desktop compatibility — #84

- [ ] Complete core workflows using keyboard only; record any unreachable controls or focus traps.
- [ ] Inspect accessible names, roles, and states for buttons, fields, menus, dialogs, and list/grid actions.
- [ ] Test with Orca or an equivalent screen reader and record announcements that are missing or misleading.
- [ ] Test high-contrast and large-text settings; verify labels, focus, dialogs, and actions remain usable.
- [ ] Test on the supported GNOME session and record Wayland/X11 behavior. Do not claim compatibility with an environment that was not tested.
- [ ] Capture genuine application screenshots for the library, search, settings, and release views for #82. Do not substitute mockups or generated imagery.

## Release gate — #81

- [ ] Run the complete Tests workflow for the exact candidate commit and confirm it completed green.
- [ ] Complete the applicable checks above; record distribution, desktop/session, GTK/libadwaita versions, and results.
- [ ] Confirm library data persists across restart and no startup/runtime errors remain.
- [ ] Review the source tree, license, README install instructions, and draft CHANGELOG.
- [ ] Only after all required checks pass, authorize and create the `v0.1.0` tag/release. Until then, do not publish a tag or release.

## Reporting results

For each checked item, record the date, environment, exact steps, observed outcome, and any issue/commit that resolves a failure. Leave the checkbox unchecked when the environment was unavailable, the result was ambiguous, or the behavior was not actually exercised.
