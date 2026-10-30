"""Library statistics derived from local anime entries."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .models import AnimeEntry, WatchStatus


DEFAULT_MINUTES_PER_EPISODE = 24


def calculate_library_statistics(
    entries: Iterable[AnimeEntry],
    *,
    minutes_per_episode: int = DEFAULT_MINUTES_PER_EPISODE,
) -> dict[str, int | float | dict[str, int]]:
    """Calculate local-library totals without accessing the network.

    Time invested is an estimate based on a configurable average episode
    duration; it is not playback telemetry.
    """
    if isinstance(minutes_per_episode, bool) or not isinstance(minutes_per_episode, int):
        raise ValueError("Minutes per episode must be a whole number.")
    if minutes_per_episode < 0:
        raise ValueError("Minutes per episode cannot be negative.")

    library = list(entries)
    statuses = Counter(entry.status.value for entry in library)
    watched = sum(entry.episodes_watched for entry in library)
    known_total = sum(
        entry.episodes_total or 0
        for entry in library
        if entry.episodes_total is not None
    )
    completed = statuses[WatchStatus.COMPLETED.value]
    completion_rate = (completed / len(library) * 100) if library else 0.0

    return {
        "anime_count": len(library),
        "episodes_watched": watched,
        "known_episodes_total": known_total,
        "completion_rate": round(completion_rate, 1),
        "estimated_minutes": watched * minutes_per_episode,
        "status_counts": {
            status.value: statuses[status.value] for status in WatchStatus
        },
    }
