"""Bounded, persistent JSON cache for public AniList metadata."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


DEFAULT_TTL = 24 * 60 * 60
MAX_CACHE_ENTRIES = 100
MAX_CACHE_ENTRY_BYTES = 1024 * 1024


def default_cache_directory() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "aniyori" / "metadata"


class MetadataCache:
    """Cache JSON-compatible metadata with expiry and a bounded entry count."""

    def __init__(
        self,
        directory: str | Path | None = None,
        *,
        ttl: int = DEFAULT_TTL,
        max_entries: int = MAX_CACHE_ENTRIES,
    ):
        if ttl < 0:
            raise ValueError("Cache TTL cannot be negative.")
        if max_entries < 1:
            raise ValueError("Cache must allow at least one entry.")
        self.directory = Path(directory) if directory else default_cache_directory()
        self.ttl = ttl
        self.max_entries = max_entries

    @staticmethod
    def _key(namespace: str, key: str) -> str:
        digest = hashlib.sha256(f"{namespace}\0{key}".encode("utf-8")).hexdigest()
        return f"{digest}.json"

    def _path(self, namespace: str, key: str) -> Path:
        return self.directory / self._key(namespace, key)

    def get(self, namespace: str, key: str) -> tuple[Any, bool] | None:
        """Return (value, is_fresh); expired entries remain available as fallback."""
        path = self._path(namespace, key)
        try:
            if path.stat().st_size > MAX_CACHE_ENTRY_BYTES:
                path.unlink(missing_ok=True)
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or "value" not in payload:
                path.unlink(missing_ok=True)
                return None
            timestamp = payload.get("stored_at")
            now = time.time()
            invalid_timestamp = (
                isinstance(timestamp, bool)
                or not isinstance(timestamp, (int, float))
            )
            if not invalid_timestamp:
                invalid_timestamp = timestamp < 0 or timestamp > now
                if isinstance(timestamp, float):
                    import math

                    invalid_timestamp = invalid_timestamp or not math.isfinite(timestamp)
            if invalid_timestamp:
                path.unlink(missing_ok=True)
                return None
            os.utime(path, None)
            return payload["value"], (now - timestamp) <= self.ttl
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def set(self, namespace: str, key: str, value: Any) -> None:
        """Atomically store a JSON value and prune least-recently-used entries."""
        encoded = json.dumps(
            {"stored_at": time.time(), "value": value},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_CACHE_ENTRY_BYTES:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self._path(namespace, key)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.directory, prefix=".metadata-", delete=False
            ) as temporary:
                temporary.write(encoded)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        self._prune()

    def _prune(self) -> None:
        try:
            entries = sorted(
                self.directory.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for path in entries[self.max_entries:]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue

    def clear(self) -> None:
        """Remove cached metadata without touching cached cover images."""
        if not self.directory.exists():
            return
        for path in self.directory.glob("*.json"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
