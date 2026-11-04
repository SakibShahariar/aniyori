"""Deterministic library sorting shared by list and grid views."""

from __future__ import annotations

from datetime import datetime
from collections.abc import Mapping, Iterable

from ..models import AnimeEntry

SORT_MODES = ("title", "progress", "recently_updated", "next_airing")


def _updated_timestamp(value: str | None) -> float:
    if not value:
        return float("-inf")
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return float("-inf")


def sort_library_entries(
    entries: Iterable[AnimeEntry],
    *,
    sort_by: str = "title",
    airing_by_id: Mapping[int, tuple[int, int]] | None = None,
    updated_at_by_id: Mapping[int, str] | None = None,
) -> list[AnimeEntry]:
    """Return entries in a stable order for the selected sort mode."""
    if sort_by not in SORT_MODES:
        raise ValueError("Unsupported library sort mode.")
    airing_by_id = airing_by_id or {}
    updated_at_by_id = updated_at_by_id or {}
    items = list(entries)
    if sort_by == "progress":
        return sorted(
            items,
            key=lambda item: (
                -(
                    item.episodes_watched / item.episodes_total
                    if item.episodes_total else item.episodes_watched
                ),
                item.title.casefold(),
                item.storage_id or 0,
            ),
        )
    if sort_by == "recently_updated":
        return sorted(
            items,
            key=lambda item: (
                -_updated_timestamp(updated_at_by_id.get(item.storage_id)),
                item.title.casefold(),
                item.storage_id or 0,
            ),
        )
    if sort_by == "next_airing":
        return sorted(
            items,
            key=lambda item: (
                item.storage_id not in airing_by_id,
                airing_by_id.get(item.storage_id, (0, 0))[1],
                item.title.casefold(),
                item.storage_id or 0,
            ),
        )
    return sorted(items, key=lambda item: (item.title.casefold(), item.storage_id or 0))
