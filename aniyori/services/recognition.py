"""Headless orchestration for local anime file recognition."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .matching import AnimeMatchDecision, ReleaseMatchDecision, match_release_filename
from ..filename_parser import parse_anime_filename
from .media_scanner import scan_video_files
from .recognition_exclusions import exclusion_reason


@dataclass(frozen=True, slots=True)
class LocalVideoMatch:
    """Recognition result for one discovered local video file."""

    path: Path
    result: ReleaseMatchDecision
    excluded_reason: str | None = None


def recognize_local_videos(
    roots: Iterable[str | Path],
    candidates: Iterable[Mapping[str, Any]],
    *,
    aliases: Mapping[int | str, Iterable[str]] | None = None,
    overrides: Mapping[str, int | str] | None = None,
    minimum_score: float = 0.84,
    ambiguity_margin: float = 0.06,
    excluded_directories: Iterable[str] | None = None,
    exclusions: Iterable[Mapping[str, str]] = (),
    is_cancelled: Callable[[], bool] | None = None,
) -> list[LocalVideoMatch]:
    """Scan roots and classify files as matched, ambiguous, or unrecognized.

    Catalogue candidates are snapshotted once so generators work across every
    discovered file. The function performs no network or GTK work; callers can
    supply cached catalogue results and run it from a worker thread.
    """
    scan_options = {}
    if excluded_directories is not None:
        scan_options["excluded_directories"] = excluded_directories
    paths = scan_video_files(roots, is_cancelled=is_cancelled, **scan_options)
    catalogue = tuple(candidates)
    exclusion_rules = tuple(exclusions)
    results = []
    for path in paths:
        if is_cancelled is not None and is_cancelled():
            break
        parsed = parse_anime_filename(path.name)
        reason = exclusion_reason(path, parsed, None, exclusion_rules)
        if reason is not None:
            result = ReleaseMatchDecision(parsed, AnimeMatchDecision("no_match", ()))
            results.append(LocalVideoMatch(path=path, result=result, excluded_reason=reason))
            continue
        result = match_release_filename(
            path.name,
            catalogue,
            aliases=aliases,
            overrides=overrides,
            minimum_score=minimum_score,
            ambiguity_margin=ambiguity_margin,
        )
        reason = exclusion_reason(
            path, result.parsed, result.decision.best_match, exclusion_rules
        )
        results.append(LocalVideoMatch(path=path, result=result, excluded_reason=reason))
    return results
