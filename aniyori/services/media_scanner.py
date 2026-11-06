"""Deterministic, UI-independent discovery of local video files."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


VIDEO_EXTENSIONS = frozenset(
    {".mkv", ".mp4", ".avi", ".webm", ".mov", ".m4v", ".ts", ".wmv", ".flv"}
)
DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".cache",
        ".git",
        ".local",
        ".trash",
        "__pycache__",
        "$recycle.bin",
        "lost+found",
        "system volume information",
    }
)


@dataclass(frozen=True, slots=True)
class ScannedVideoFile:
    """One contained regular video file and its best-known size."""

    path: Path
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class VideoScanResult:
    """File snapshot plus roots that made the scan incomplete."""

    files: tuple[ScannedVideoFile, ...]
    unavailable_roots: tuple[Path, ...]
    size_complete: bool


def scan_video_files_detailed(
    roots: Iterable[str | Path],
    *,
    excluded_directories: Iterable[str] = DEFAULT_EXCLUDED_DIRECTORIES,
    is_cancelled: Callable[[], bool] | None = None,
) -> VideoScanResult:
    """Discover unique contained video paths without following symlinks.

    Directory and file symlinks are not followed. Every discovered file is
    resolved and checked against its canonical configured root before it is
    accepted. Overlapping roots are deduplicated by canonical path. Distinct
    Hard links and overlapping roots are deduplicated by device/inode when
    the filesystem supplies a stable inode, so one physical file contributes
    to size totals once.
    """
    if isinstance(roots, (str, Path)):
        roots = (roots,)
    excluded = {name.casefold() for name in excluded_directories}
    discovered: dict[tuple[int, int] | Path, ScannedVideoFile] = {}
    incomplete_roots: set[Path] = set()
    cancelled = False

    for raw_root in roots:
        if is_cancelled is not None and is_cancelled():
            cancelled = True
            break
        root_path = Path(raw_root).expanduser()
        try:
            if root_path.is_symlink():
                incomplete_roots.add(root_path)
                continue
            root = root_path.resolve(strict=True)
            if not root.is_dir():
                incomplete_roots.add(root_path)
                continue
        except (OSError, RuntimeError):
            incomplete_roots.add(root_path)
            continue

        def record_walk_error(_error):
            incomplete_roots.add(root_path)

        for current, directories, filenames in os.walk(
            root, topdown=True, followlinks=False, onerror=record_walk_error
        ):
            if is_cancelled is not None and is_cancelled():
                cancelled = True
                break

            current_path = Path(current)
            safe_directories = []
            for name in sorted(directories, key=str.casefold):
                if name.casefold() in excluded:
                    continue
                candidate = current_path / name
                try:
                    if candidate.is_symlink():
                        continue
                    resolved = candidate.resolve(strict=True)
                    resolved.relative_to(root)
                    if resolved.is_dir():
                        safe_directories.append(name)
                except (OSError, RuntimeError, ValueError):
                    continue
            directories[:] = safe_directories

            for filename in sorted(filenames, key=str.casefold):
                if is_cancelled is not None and is_cancelled():
                    cancelled = True
                    break
                path = current_path / filename
                if path.suffix.casefold() not in VIDEO_EXTENSIONS:
                    continue
                try:
                    metadata = path.lstat()
                    if not stat.S_ISREG(metadata.st_mode):
                        continue
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(root)
                except (OSError, RuntimeError, ValueError):
                    incomplete_roots.add(root_path)
                    continue
                identity = (
                    (metadata.st_dev, metadata.st_ino)
                    if metadata.st_ino else resolved
                )
                discovered.setdefault(
                    identity,
                    ScannedVideoFile(path=resolved, size_bytes=metadata.st_size),
                )
            if cancelled:
                break
        if cancelled:
            break

    files = tuple(
        sorted(discovered.values(), key=lambda item: str(item.path).casefold())
    )
    unavailable = tuple(
        sorted(incomplete_roots, key=lambda path: str(path).casefold())
    )
    return VideoScanResult(
        files=files,
        unavailable_roots=unavailable,
        size_complete=not unavailable and not cancelled,
    )


def scan_video_files(
    roots: Iterable[str | Path],
    *,
    excluded_directories: Iterable[str] = DEFAULT_EXCLUDED_DIRECTORIES,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[Path]:
    """Return unique video paths while preserving the original scanner API."""
    result = scan_video_files_detailed(
        roots,
        excluded_directories=excluded_directories,
        is_cancelled=is_cancelled,
    )
    return [item.path for item in result.files]
