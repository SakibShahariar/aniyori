"""Summarize locally available episodes for matched AniList entries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from ..models import AnimeEntry
from .recognition import LocalVideoMatch


@dataclass(frozen=True, slots=True)
class EpisodeInventory:
    """Episode availability for one AniList library entry.

    Season-tagged releases are kept separate because a season-local episode
    number cannot safely be compared with an anime's overall episode total.
    """

    entry: AnimeEntry
    available_episodes: tuple[int, ...]
    missing_episodes: tuple[int, ...]
    next_episode: int | None
    seasoned_episodes: tuple[tuple[int, tuple[int, ...]], ...]


def summarize_episode_inventory(
    matches: Iterable[LocalVideoMatch],
    entries: Iterable[AnimeEntry],
) -> tuple[EpisodeInventory, ...]:
    """Build deterministic episode inventories without guessing season offsets.

    Only confident matches to AniList-backed library entries are counted.
    Ambiguous, unparsed, unmatched, and out-of-library files are ignored.
    Duplicate releases of the same episode count once.
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

    for item in matches:
        decision = item.result.decision
        best = decision.best_match
        parsed = item.result.parsed
        if best is None or parsed is None:
            continue
        key = str(best.media_id)
        if key not in entries_by_id or parsed.episode < 1:
            continue
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

        # Do not compare season-local numbers with the catalogue's overall
        # episode count. Mixed season-tagged and untagged naming is also
        # treated conservatively because the numbering scheme is unclear.
        if season_groups:
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

        inventories.append(
            EpisodeInventory(
                entry=entry,
                available_episodes=episodes,
                missing_episodes=missing,
                next_episode=next_episode,
                seasoned_episodes=season_groups,
            )
        )

    return tuple(inventories)
