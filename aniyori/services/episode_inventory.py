"""Summarize locally available episodes for matched AniList entries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..models import AnimeEntry
from .recognition import LocalVideoMatch


@dataclass(frozen=True, slots=True)
class EpisodeInventory:
    """Episode availability and file-size details for one AniList entry."""

    entry: AnimeEntry
    available_episodes: tuple[int, ...]
    missing_episodes: tuple[int, ...]
    next_episode: int | None
    seasoned_episodes: tuple[tuple[int, tuple[int, ...]], ...]
    next_unwatched_episode: int | None = None
    size_bytes: int = 0
    size_complete: bool = True
    missing_complete: bool = True
    source_paths: tuple[Path, ...] = ()


def summarize_episode_inventory(
    matches: Iterable[LocalVideoMatch],
    entries: Iterable[AnimeEntry],
    *,
    watched_episodes: Mapping[int | str, Iterable[int]] | None = None,
    scan_complete: bool = True,
    size_complete: bool = True,
) -> tuple[EpisodeInventory, ...]:
    """Build deterministic inventories without guessing season offsets.

    Only confident matches to AniList-backed library entries are counted.
    Ambiguous, unparsed, unmatched, excluded, and out-of-library files are
    ignored. Duplicate releases of one episode count once. If no explicit
    per-episode state is supplied, aggregate progress retains the legacy
    assumption that episodes 1..N are watched.
    """
    entries_by_id = {
        str(entry.provider_id): entry
        for entry in entries
        if entry.provider == "anilist" and entry.provider_id is not None
    }
    available: dict[str, set[int]] = defaultdict(set)
    seasoned: dict[str, dict[int, set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    sizes: dict[str, int] = defaultdict(int)
    sizes_complete: dict[str, bool] = defaultdict(lambda: size_complete)
    paths: dict[str, set[Path]] = defaultdict(set)

    for item in matches:
        if item.excluded_reason is not None:
            continue
        decision = item.result.decision
        best = decision.best_match
        parsed = item.result.parsed
        if best is None or parsed is None:
            continue
        key = str(best.media_id)
        if key not in entries_by_id or parsed.episode < 1:
            continue
        paths[key].add(item.path)
        if item.size_bytes is None:
            sizes_complete[key] = False
        elif isinstance(item.size_bytes, int) and not isinstance(item.size_bytes, bool) and item.size_bytes >= 0:
            sizes[key] += item.size_bytes
        else:
            sizes_complete[key] = False
        if parsed.season is None:
            available[key].add(parsed.episode)
        elif parsed.season > 0:
            seasoned[key][parsed.season].add(parsed.episode)

    inventories = []
    for key, entry in sorted(
        entries_by_id.items(), key=lambda pair: (pair[1].title.casefold(), pair[0])
    ):
        episodes = tuple(sorted(available[key]))
        season_groups = tuple(
            (season, tuple(sorted(numbers)))
            for season, numbers in sorted(seasoned[key].items())
        )

        missing_complete = scan_complete and not season_groups and entry.episodes_total is not None
        if not scan_complete or season_groups:
            missing = ()
            next_episode = None
        elif entry.episodes_total is not None:
            missing = tuple(
                number
                for number in range(1, entry.episodes_total + 1)
                if number not in available[key]
            )
            next_episode = missing[0] if missing else None
        else:
            missing = ()
            next_episode = episodes[-1] + 1 if episodes else None

        if not scan_complete or season_groups:
            next_unwatched = None
        else:
            if watched_episodes is not None and key in watched_episodes:
                raw_watched = watched_episodes[key]
            else:
                raw_watched = range(1, entry.episodes_watched + 1)
            watched = {
                number for number in raw_watched
                if isinstance(number, int) and not isinstance(number, bool) and number > 0
            }
            unwatched = [number for number in episodes if number not in watched]
            next_unwatched = unwatched[0] if unwatched else None

        inventories.append(
            EpisodeInventory(
                entry=entry,
                available_episodes=episodes,
                missing_episodes=missing,
                next_episode=next_episode,
                seasoned_episodes=season_groups,
                next_unwatched_episode=next_unwatched,
                size_bytes=sizes[key],
                size_complete=sizes_complete[key],
                missing_complete=missing_complete,
                source_paths=tuple(sorted(paths[key], key=lambda path: str(path).casefold())),
            )
        )

    return tuple(inventories)
