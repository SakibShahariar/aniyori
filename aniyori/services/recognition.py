"""Headless orchestration for local anime file recognition."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .matching import ReleaseMatchDecision, match_release_filename
from .media_scanner import scan_video_files


@dataclass(frozen=True, slots=True)
class LocalVideoMatch:
    """Recognition result for one discovered local video file."""

    path: Path
    result: ReleaseMatchDecision


def recognize_local_videos(
    roots: Iterable[str | Path],
    candidates: Iterable[Mapping[str, Any]],
    *,
    aliases: Mapping[int | str, Iterable[str]] | None = None,
    overrides: Mapping[str, int | str] | None = None,
    minimum_score: float = 0.84,
    ambiguity_margin: float = 0.06,
    excluded_directories: Iterable[str] | None = None,
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
    results = []
    for path in paths:
        if is_cancelled is not None and is_cancelled():
            break
        results.append(
            LocalVideoMatch(
                path=path,
                result=match_release_filename(
                    path.name,
                    catalogue,
                    aliases=aliases,
                    overrides=overrides,
                    minimum_score=minimum_score,
                    ambiguity_margin=ambiguity_margin,
                ),
            )
        )
    return results
