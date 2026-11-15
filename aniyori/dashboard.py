"""Data selection helpers for the Home dashboard."""

from collections import Counter

from .models import AnimeEntry, WatchStatus


def count_library_statuses(entries: list[AnimeEntry]) -> dict[WatchStatus, int]:
    """Return a count for every library status, including statuses with no entries."""
    counts = Counter(entry.status for entry in entries)
    return {status: counts[status] for status in WatchStatus}


def continue_watching_entries(
    entries: list[AnimeEntry], *, limit: int = 6
) -> list[AnimeEntry]:
    """Return in-progress entries that can still advance."""
    if limit <= 0:
        return []
    return [
        entry for entry in entries
        if entry.status == WatchStatus.WATCHING
        and (
            entry.episodes_total is None
            or entry.episodes_watched < entry.episodes_total
        )
    ][:limit]


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
