"""Persistent per-anime release preferences that override global defaults."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .release_preferences import (
    PREFERENCE_ATTRIBUTES, ReleasePreferenceError, normalize_release_preferences,
)

FORMAT = "aniyori-anime-release-preferences"
VERSION = 1


class AnimeReleasePreferenceError(ValueError):
    """Raised when per-anime release preferences are invalid."""


def default_anime_release_preferences_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "anime-release-preferences.json"


def _normalise_size(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnimeReleasePreferenceError(f"{field} must be a finite number of MiB.")
    if not math.isfinite(value) or value < 0 or value > 10_000_000:
        raise AnimeReleasePreferenceError(f"{field} must be between 0 and 10,000,000 MiB.")
    return float(value)


def normalize_anime_release_preference(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AnimeReleasePreferenceError("Per-anime preferences must be an object.")
    unknown = set(value) - {"enabled", "min_file_size_mb", "max_file_size_mb", "preferences"}
    if unknown:
        raise AnimeReleasePreferenceError("Unknown per-anime preference fields: " + ", ".join(sorted(unknown)))
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise AnimeReleasePreferenceError("The per-anime download toggle must be a boolean.")
    minimum = _normalise_size(value.get("min_file_size_mb"), "Minimum file size")
    maximum = _normalise_size(value.get("max_file_size_mb"), "Maximum file size")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise AnimeReleasePreferenceError("Minimum file size cannot exceed maximum file size.")
    raw_preferences = value.get("preferences", {})
    if not isinstance(raw_preferences, Mapping):
        raise AnimeReleasePreferenceError("Per-anime attribute preferences must be an object.")
    unknown_attributes = set(raw_preferences) - set(PREFERENCE_ATTRIBUTES)
    if unknown_attributes:
        raise AnimeReleasePreferenceError("Unknown release attributes: " + ", ".join(sorted(unknown_attributes)))
    preferences = {}
    for attribute, raw in raw_preferences.items():
        normalized = normalize_release_preferences({attribute: raw})
        item = next(group for group in normalized if group.attribute == attribute)
        preferences[attribute] = {
            "preferred": list(item.preferred),
            "rejected": list(item.rejected),
            "priority": item.priority,
        }
    return {
        "enabled": enabled,
        "min_file_size_mb": minimum,
        "max_file_size_mb": maximum,
        "preferences": preferences,
    }


class AnimeReleasePreferenceStore:
    """Load, update, and reset overrides keyed by stable local library IDs."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_anime_release_preferences_path()

    def load(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AnimeReleasePreferenceError("Saved per-anime preferences are invalid.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != FORMAT
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("version"), int)
            or payload.get("version") != VERSION
            or not isinstance(payload.get("anime"), dict)
        ):
            raise AnimeReleasePreferenceError("Saved per-anime preferences have an unsupported format.")
        result = {}
        for key, value in payload["anime"].items():
            if not isinstance(key, str) or not key.isdigit() or int(key) <= 0:
                raise AnimeReleasePreferenceError("Saved per-anime preference IDs are invalid.")
            result[key] = normalize_anime_release_preference(value)
        return result

    def save(self, anime_preferences: Mapping[str | int, Mapping[str, Any]]) -> None:
        if not isinstance(anime_preferences, Mapping):
            raise AnimeReleasePreferenceError("Per-anime preferences must be a mapping.")
        prepared = {}
        for key, value in anime_preferences.items():
            if isinstance(key, bool) or not str(key).isdigit() or int(key) <= 0:
                raise AnimeReleasePreferenceError("A valid positive library ID is required.")
            prepared[str(key)] = normalize_anime_release_preference(value)
        self._write(prepared)

    def _write(self, anime_preferences: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"format": FORMAT, "version": VERSION, "anime": anime_preferences},
            ensure_ascii=False, indent=2,
        ) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".anime-release-preferences-", delete=False,
            ) as temporary:
                os.chmod(temporary.name, 0o600)
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load_for(self, anime_id: int) -> dict[str, Any]:
        if isinstance(anime_id, bool) or not isinstance(anime_id, int) or anime_id <= 0:
            raise AnimeReleasePreferenceError("A valid positive library ID is required.")
        return self.load().get(str(anime_id), normalize_anime_release_preference({}))

    def save_for(self, anime_id: int, preferences: Mapping[str, Any]) -> None:
        if isinstance(anime_id, bool) or not isinstance(anime_id, int) or anime_id <= 0:
            raise AnimeReleasePreferenceError("A valid positive library ID is required.")
        all_preferences = self.load()
        all_preferences[str(anime_id)] = normalize_anime_release_preference(preferences)
        self._write(all_preferences)

    def reset_for(self, anime_id: int) -> bool:
        if isinstance(anime_id, bool) or not isinstance(anime_id, int) or anime_id <= 0:
            raise AnimeReleasePreferenceError("A valid positive library ID is required.")
        all_preferences = self.load()
        removed = all_preferences.pop(str(anime_id), None) is not None
        if removed:
            self._write(all_preferences)
        return removed
