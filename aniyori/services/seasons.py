"""Season selection and filtering helpers for AniList discovery."""

from __future__ import annotations

from datetime import date
from typing import Any


SEASONS = ("WINTER", "SPRING", "SUMMER", "FALL")


def season_for_date(value: date | None = None) -> tuple[str, int]:
    """Return the AniList season containing a date."""
    value = value or date.today()
    if not isinstance(value, date):
        raise ValueError("value must be a date")
    return SEASONS[(value.month - 1) // 3], value.year


def filter_season_results(results: list[dict[str, Any]], *, query: str = "", genre: str = "",
                          format_name: str = "", status: str = "", sort_by: str = "popularity") -> list[dict[str, Any]]:
    """Filter and sort a season result set without mutating cached results."""
    if sort_by not in {"popularity", "score", "title", "airing_date"}:
        raise ValueError("Unknown season sort mode")
    needle = query.strip().casefold()
    visible = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        genres = item.get("genres") if isinstance(item.get("genres"), list) else []
        if needle and needle not in title.casefold() and not any(needle in str(value).casefold() for value in genres):
            continue
        if genre and genre not in genres:
            continue
        if format_name and item.get("format") != format_name:
            continue
        if status and item.get("status") != status:
            continue
        visible.append(item)

    def number(item, key):
        value = item.get(key)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else -1

    def airing_key(item):
        timestamp = item.get("next_airing_at")
        if isinstance(timestamp, int) and not isinstance(timestamp, bool) and timestamp > 0:
            return (0, timestamp, 0, 0)
        value = item.get("start_date")
        if isinstance(value, dict):
            parts = tuple(
                value.get(key) if isinstance(value.get(key), int) and not isinstance(value.get(key), bool) else 0
                for key in ("year", "month", "day")
            )
            if any(parts):
                return (1, *parts)
        return (2, 0, 0, 0)

    if sort_by == "popularity":
        visible.sort(key=lambda item: number(item, "popularity"), reverse=True)
    elif sort_by == "score":
        visible.sort(key=lambda item: number(item, "average_score"), reverse=True)
    elif sort_by == "title":
        visible.sort(key=lambda item: str(item.get("title") or "").casefold())
    else:
        visible.sort(key=airing_key)
    return visible
