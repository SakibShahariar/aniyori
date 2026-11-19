"""Data selection helpers for the Home dashboard."""

import time
from collections import Counter, defaultdict
from datetime import datetime

from .models import AnimeEntry, WatchStatus


def count_library_statuses(entries: list[AnimeEntry]) -> dict[WatchStatus, int]:
    """Return a count for every library status, including statuses with no entries."""
    counts = Counter(entry.status for entry in entries)
    return {status: counts[status] for status in WatchStatus}


def continue_watching_entries(
    entries: list[AnimeEntry],
    updated_at_by_id: dict[int, str] | None = None,
    *,
    limit: int = 6,
) -> list[AnimeEntry]:
    """Return unfinished watching entries, most recently updated first."""
    if limit <= 0:
        return []
    candidates = [
        entry for entry in entries
        if entry.status == WatchStatus.WATCHING
        and (
            entry.episodes_total is None
            or entry.episodes_watched < entry.episodes_total
        )
    ]
    if updated_at_by_id is not None:
        candidates.sort(
            key=lambda entry: (
                updated_at_by_id.get(entry.storage_id, "")
                if entry.storage_id is not None else ""
            ),
            reverse=True,
        )
    return candidates[:limit]


def recently_added_entries(
    entries: list[AnimeEntry],
    created_at_by_id: dict[int, str],
    *,
    limit: int = 8,
) -> list[AnimeEntry]:
    """Return saved entries ordered by their original creation timestamps, newest first."""
    if limit <= 0:
        return []
    candidates = (
        entry for entry in entries
        if entry.storage_id is not None and entry.storage_id in created_at_by_id
    )
    return sorted(
        candidates,
        key=lambda entry: created_at_by_id[entry.storage_id],
        reverse=True,
    )[:limit]


def group_airing_schedules(
    schedules: list[dict],
    entries: list[AnimeEntry],
    year: int,
    month: int,
    timezone,
) -> dict[int, list[tuple[AnimeEntry, int, datetime]]]:
    """Group API airing episodes for one month into local calendar days."""
    by_provider_id = {
        str(entry.provider_id): entry
        for entry in entries
        if entry.provider == "anilist" and entry.provider_id
    }
    grouped = defaultdict(list)
    for item in schedules:
        if not isinstance(item, dict):
            continue
        entry = by_provider_id.get(str(item.get("media_id")))
        episode, airing_at = item.get("episode"), item.get("airing_at")
        if entry is None or (
            isinstance(episode, bool) or not isinstance(episode, int) or episode <= 0
            or isinstance(airing_at, bool) or not isinstance(airing_at, int)
        ):
            continue
        try:
            local = datetime.fromtimestamp(airing_at, tz=timezone)
        except (ValueError, OverflowError, OSError):
            continue
        if local.year == year and local.month == month:
            grouped[local.day].append((entry, episode, local))
    for day in grouped:
        grouped[day].sort(key=lambda item: item[2])
    return dict(grouped)


def airing_by_local_date(
    entries: list[AnimeEntry],
    airing_by_id: dict[int, tuple[int, int]],
    year: int,
    month: int,
    timezone,
) -> dict[int, list[tuple[AnimeEntry, int, datetime]]]:
    """Group saved airing times into local calendar days for one month."""
    grouped = defaultdict(list)
    for entry in entries:
        storage_id = entry.storage_id
        if storage_id is None:
            continue
        airing = airing_by_id.get(storage_id)
        if not isinstance(airing, tuple) or len(airing) != 2:
            continue
        episode, airing_at = airing
        if (
            isinstance(episode, bool) or not isinstance(episode, int) or episode <= 0
            or isinstance(airing_at, bool) or not isinstance(airing_at, int)
        ):
            continue
        try:
            local = datetime.fromtimestamp(airing_at, tz=timezone)
        except (ValueError, OverflowError, OSError):
            continue
        if local.year != year or local.month != month:
            continue
        grouped[local.day].append((entry, episode, local))
    for day in grouped:
        grouped[day].sort(key=lambda item: item[2])
    return dict(grouped)


def upcoming_airing_entries(
    entries: list[AnimeEntry],
    airing_by_id: dict[int, tuple[int, int]],
    *,
    limit: int = 12,
    now: int | None = None,
) -> list[AnimeEntry]:
    """Return saved entries with a future airing time, soonest first.

    Airing data is supplied by the existing AniList schedule refresh; entries
    without a valid future timestamp are omitted rather than fabricated.
    """
    if limit <= 0:
        return []
    current_time = int(time.time()) if now is None else now
    candidates = []
    for entry in entries:
        storage_id = entry.storage_id
        if storage_id is None:
            continue
        airing = airing_by_id.get(storage_id)
        if not isinstance(airing, tuple) or len(airing) != 2:
            continue
        episode, airing_at = airing
        if (
            isinstance(airing_at, bool)
            or not isinstance(airing_at, int)
            or airing_at <= current_time
        ):
            continue
        candidates.append((airing_at, episode, entry))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [entry for _airing_at, _episode, entry in candidates[:limit]]
