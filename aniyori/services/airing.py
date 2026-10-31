"""Helpers for presenting AniList next-episode schedule metadata."""

from __future__ import annotations

from datetime import datetime, timezone


def format_airing_countdown(
    episode: int | None,
    airing_at: int | None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Format an upcoming episode relative to an aware or UTC clock value."""
    if (
        isinstance(episode, bool) or not isinstance(episode, int) or episode <= 0
        or isinstance(airing_at, bool) or not isinstance(airing_at, int) or airing_at <= 0
    ):
        return None
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    seconds = max(
        0,
        int(datetime.fromtimestamp(airing_at, timezone.utc).timestamp() - current.timestamp()),
    )
    if seconds == 0:
        return f"Episode {episode} · airing now"
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    if days:
        countdown = f"{days}d {hours}h"
    elif hours:
        countdown = f"{hours}h {minutes}m"
    else:
        countdown = f"{max(1, minutes)}m"
    return f"Episode {episode} · in {countdown}"
