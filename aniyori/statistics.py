"""Library statistics derived from local anime entries."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone, tzinfo

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



def calculate_history_insights(
    events: Iterable[Mapping[str, object]],
    year: int,
    *,
    local_timezone=None,
    minutes_per_episode: int = DEFAULT_MINUTES_PER_EPISODE,
) -> dict[str, object]:
    """Summarize recorded watch-history events for one local calendar year.

    Naive database timestamps are interpreted as UTC because SQLite's
    CURRENT_TIMESTAMP is UTC. Invalid or undated records are omitted rather
    than assigned an invented date. Episode totals count recorded episode
    events, not inferred progress corrections. Estimated time is explicitly
    an estimate based on the configured average episode duration.
    """
    if isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999:
        raise ValueError("Year must be a valid calendar year.")
    if isinstance(minutes_per_episode, bool) or not isinstance(minutes_per_episode, int):
        raise ValueError("Minutes per episode must be a whole number.")
    if minutes_per_episode < 0:
        raise ValueError("Minutes per episode cannot be negative.")
    if isinstance(events, (str, bytes)) or events is None:
        raise ValueError("Watch-history events must be an iterable of records.")
    try:
        iter(events)
    except TypeError as error:
        raise ValueError("Watch-history events must be an iterable of records.") from error

    if local_timezone is None:
        local_timezone = datetime.now().astimezone().tzinfo or timezone.utc
    if not isinstance(local_timezone, tzinfo):
        raise ValueError("A valid local timezone is required.")

    month_rows = [
        {
            "month": month,
            "event_count": 0,
            "episode_events": 0,
            "first_watch_events": 0,
            "rewatch_events": 0,
            "progress_changes": 0,
            "status_changes": 0,
        }
        for month in range(1, 13)
    ]
    active_days = set()
    completed = {}
    seen_ids = set()

    for event in events:
        if not isinstance(event, Mapping):
            continue
        action = event.get("action")
        if action not in ("episode", "progress", "status"):
            continue
        raw_timestamp = event.get("created_at")
        if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
            continue
        try:
            timestamp = datetime.fromisoformat(
                raw_timestamp.strip().replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        try:
            local_timestamp = timestamp.astimezone(local_timezone)
        except (OverflowError, ValueError):
            continue
        if local_timestamp.year != year:
            continue

        event_id = event.get("id")
        if (
            isinstance(event_id, int)
            and not isinstance(event_id, bool)
            and event_id > 0
        ):
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)

        month = month_rows[local_timestamp.month - 1]
        month["event_count"] += 1
        active_days.add(local_timestamp.date())

        details = event.get("details")
        if action == "episode":
            month["episode_events"] += 1
            if details == "Rewatched episode":
                month["rewatch_events"] += 1
            elif details == "Marked episode watched":
                month["first_watch_events"] += 1
            elif isinstance(details, str) and "→" in details:
                previous, current = details.split("→", 1)
                try:
                    previous_count = int(previous.strip())
                    current_count = int(current.strip())
                except ValueError:
                    pass
                else:
                    if previous_count >= 0 and current_count == previous_count + 1:
                        month["first_watch_events"] += 1
        elif action == "progress":
            month["progress_changes"] += 1
        else:
            month["status_changes"] += 1
            if isinstance(details, str) and details.split("→", 1)[-1].strip() == "completed":
                anime_id = event.get("anime_id")
                title = event.get("anime_title")
                if not isinstance(title, str) or not title.strip():
                    continue
                valid_anime_id = (
                    isinstance(anime_id, int)
                    and not isinstance(anime_id, bool)
                    and anime_id > 0
                )
                key = (
                    ("id", anime_id)
                    if valid_anime_id else ("title", title.strip().casefold())
                )
                completed.setdefault(key, {
                    "id": anime_id if valid_anime_id else None,
                    "title": title.strip(),
                })

    totals = {
        key: sum(month[key] for month in month_rows)
        for key in (
            "event_count",
            "episode_events",
            "first_watch_events",
            "rewatch_events",
            "progress_changes",
            "status_changes",
        )
    }
    completed_anime = sorted(
        completed.values(), key=lambda item: item["title"].casefold()
    )
    return {
        "year": year,
        "months": month_rows,
        **totals,
        "unclassified_episode_events": (
            totals["episode_events"]
            - totals["first_watch_events"]
            - totals["rewatch_events"]
        ),
        "active_days": len(active_days),
        "completed_anime": completed_anime,
        "completed_anime_count": len(completed_anime),
        "minutes_per_episode": minutes_per_episode,
        "estimated_minutes": totals["episode_events"] * minutes_per_episode,
    }
