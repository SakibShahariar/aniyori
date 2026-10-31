"""End-to-end, UI-independent local library scanning."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import AnimeEntry
from .episode_inventory import EpisodeInventory, summarize_episode_inventory
from .recognition import LocalVideoMatch, recognize_local_videos
from .scan_locations import ScanLocationStore


@dataclass(frozen=True, slots=True)
class LibraryScanResult:
    """Snapshot of one scan, including its roots, file matches, and inventory."""

    locations: tuple[Path, ...]
    matches: tuple[LocalVideoMatch, ...]
    inventory: tuple[EpisodeInventory, ...]


def scan_configured_library(
    location_store: ScanLocationStore,
    candidates: Iterable[Mapping[str, Any]],
    entries: Iterable[AnimeEntry],
    *,
    aliases: Mapping[int | str, Iterable[str]] | None = None,
    overrides: Mapping[str, int | str] | None = None,
    minimum_score: float = 0.84,
    ambiguity_margin: float = 0.06,
    excluded_directories: Iterable[str] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> LibraryScanResult:
    """Scan saved folders, recognize releases, and summarize episode coverage.

    The function is synchronous by design but has no GTK dependency. Desktop
    callers should run it in a worker thread and provide a thread-safe
    cancellation callback.
    """
    locations = location_store.list_locations()
    library_entries = tuple(entries)
    matches = recognize_local_videos(
        locations,
        candidates,
        aliases=aliases,
        overrides=overrides,
        minimum_score=minimum_score,
        ambiguity_margin=ambiguity_margin,
        excluded_directories=excluded_directories,
        is_cancelled=is_cancelled,
    )
    inventory = summarize_episode_inventory(matches, library_entries)
    return LibraryScanResult(
        locations=locations,
        matches=tuple(matches),
        inventory=inventory,
    )
