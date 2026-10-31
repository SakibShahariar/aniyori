"""Asynchronous-friendly, disk-cached AniList cover image retrieval."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MAX_COVER_BYTES = 8 * 1024 * 1024
MAX_COVER_CACHE_BYTES = 256 * 1024 * 1024
MAX_COVER_CACHE_ENTRIES = 250
DEFAULT_TIMEOUT = 12


def _cache_directory() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    if not base.is_absolute():
        base = Path.home() / ".cache"
    return base / "aniyori" / "covers"


def _cache_path(url: str, cache_dir: Path | None = None) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return (cache_dir or _cache_directory()) / f"{digest}.img"


def _prune_cache(directory: Path) -> None:
    """Keep the cover cache within both its byte and entry limits."""
    try:
        entries = sorted(
            directory.glob("*.img"),
            key=lambda path: path.stat().st_mtime,
        )
        total_bytes = sum(path.stat().st_size for path in entries)
    except OSError:
        return

    while entries and (
        total_bytes > MAX_COVER_CACHE_BYTES
        or len(entries) > MAX_COVER_CACHE_ENTRIES
    ):
        oldest = entries.pop(0)
        try:
            size = oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            total_bytes -= size
        except OSError:
            continue


def get_cached_cover(
    url: str,
    *,
    cache_dir: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Path:
    """Return a cached cover path, downloading a bounded HTTPS image if needed."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or not (host == "anilist.co" or host.endswith(".anilist.co"))
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Cover URL must be an HTTPS URL hosted by AniList.")

    destination = _cache_path(url, cache_dir)
    if destination.is_file() and destination.stat().st_size > 0:
        os.utime(destination, None)
        _prune_cache(destination.parent)
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        url,
        headers={"Accept": "image/*", "User-Agent": "Aniyori/0.1.0"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
            if not content_type.startswith("image/"):
                raise ValueError("AniList did not return an image.")
            data = response.read(MAX_COVER_BYTES + 1)
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError(f"Could not download cover image: {error}") from error

    if not data:
        raise ValueError("AniList returned an empty cover image.")
    if len(data) > MAX_COVER_BYTES:
        raise ValueError("Cover image exceeds the 8 MiB download limit.")

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=".cover-", delete=False
        ) as temporary:
            temporary.write(data)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    _prune_cache(destination.parent)
    return destination
