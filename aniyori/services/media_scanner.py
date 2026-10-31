"""Deterministic, UI-independent discovery of local video files."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
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


def scan_video_files(
    roots: Iterable[str | Path],
    *,
    excluded_directories: Iterable[str] = DEFAULT_EXCLUDED_DIRECTORIES,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[Path]:
    """Return unique video files below existing roots in stable path order.

    The scan never follows directory symlinks, ignores symlinked files and
    common non-media/system directories, and tolerates roots that disappear or
    cannot be read. The cancellation callback is checked between directories
    and files, without coupling this service to GTK or a threading primitive.
    """
    excluded = {name.casefold() for name in excluded_directories}
    discovered: set[Path] = set()

    for raw_root in roots:
        if is_cancelled is not None and is_cancelled():
            break
        root = Path(raw_root).expanduser()
        if root.is_symlink() or not root.is_dir():
            continue
        root = root.absolute()

        for current, directories, filenames in os.walk(
            root, topdown=True, followlinks=False, onerror=lambda _error: None
        ):
            if is_cancelled is not None and is_cancelled():
                break

            current_path = Path(current)
            directories[:] = sorted(
                (
                    name
                    for name in directories
                    if name.casefold() not in excluded
                    and not (current_path / name).is_symlink()
                ),
                key=str.casefold,
            )

            for filename in sorted(filenames, key=str.casefold):
                if is_cancelled is not None and is_cancelled():
                    break
                path = current_path / filename
                if path.suffix.casefold() not in VIDEO_EXTENSIONS:
                    continue
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                except OSError:
                    continue
                discovered.add(path)

    return sorted(discovered, key=lambda path: str(path).casefold())
