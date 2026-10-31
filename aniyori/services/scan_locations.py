"""Persistent configuration for folders scanned for local anime videos."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable


CONFIG_FILENAME = "scan-locations.json"
CONFIG_FORMAT_VERSION = 1


def default_scan_locations_path() -> Path:
    """Return the XDG configuration path without creating its parent."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / CONFIG_FILENAME


def normalize_scan_location(value: str | Path) -> Path:
    """Normalize a folder path to an absolute, expanded path."""
    if not isinstance(value, (str, Path)):
        raise ValueError("A scan folder must be a filesystem path.")
    raw = str(value).strip()
    if not raw:
        raise ValueError("A scan folder path must not be empty.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("Scan folder paths must be absolute.")
    return path.resolve(strict=False)


class ScanLocationStore:
    """Read and atomically update configured scan folders.

    Missing configuration means an empty list. Invalid existing configuration
    raises ValueError instead of silently replacing saved folders. Paths remain
    configured when a removable drive is temporarily unavailable.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_scan_locations_path()

    def list_locations(self) -> tuple[Path, ...]:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        except OSError:
            raise
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("The saved scan folder configuration is invalid.") from error
        if not isinstance(payload, dict):
            raise ValueError("The saved scan folder configuration must be an object.")
        version = payload.get("version")
        if (
            payload.get("format") != "aniyori-scan-locations"
            or isinstance(version, bool)
            or version != CONFIG_FORMAT_VERSION
        ):
            raise ValueError("The saved scan folder configuration has an unsupported format.")
        locations = payload.get("locations")
        if not isinstance(locations, list) or not all(
            isinstance(item, str) and item.strip() for item in locations
        ):
            raise ValueError("The saved scan folder list is malformed.")

        normalized = []
        seen = set()
        for item in locations:
            path = normalize_scan_location(item)
            key = os.path.normcase(str(path))
            if key not in seen:
                normalized.append(path)
                seen.add(key)
        return tuple(normalized)

    def _write(self, locations: Iterable[Path]) -> None:
        normalized = []
        seen = set()
        for item in locations:
            path = normalize_scan_location(item)
            key = os.path.normcase(str(path))
            if key not in seen:
                normalized.append(str(path))
                seen.add(key)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"format": "aniyori-scan-locations", "version": CONFIG_FORMAT_VERSION,
             "locations": normalized},
            ensure_ascii=False, indent=2,
        ) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".scan-locations-", delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def add_location(self, location: str | Path) -> bool:
        """Add a folder, returning False when it is already configured."""
        path = normalize_scan_location(location)
        locations = list(self.list_locations())
        key = os.path.normcase(str(path))
        if any(os.path.normcase(str(item)) == key for item in locations):
            return False
        locations.append(path)
        self._write(locations)
        return True

    def remove_location(self, location: str | Path) -> bool:
        """Remove a configured folder; return False when it is absent."""
        path = normalize_scan_location(location)
        key = os.path.normcase(str(path))
        locations = list(self.list_locations())
        remaining = [item for item in locations if os.path.normcase(str(item)) != key]
        if len(remaining) == len(locations):
            return False
        self._write(remaining)
        return True
