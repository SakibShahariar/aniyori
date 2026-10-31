"""Persistent release-attribute preferences and explainable decisions."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


PREFERENCE_FORMAT = "aniyori-release-preferences"
PREFERENCE_VERSION = 1
PREFERENCE_ATTRIBUTES = (
    "resolution", "source", "audio", "subtitles", "release_group"
)


class ReleasePreferenceError(ValueError):
    """Raised when release preferences are malformed or invalid."""


@dataclass(frozen=True, slots=True)
class AttributePreference:
    """Preferred and rejected values for one release attribute."""

    attribute: str
    preferred: tuple[str, ...]
    rejected: tuple[str, ...]
    priority: int


@dataclass(frozen=True, slots=True)
class PreferenceDecision:
    """The result of applying user preferences to one release."""

    accepted: bool
    matched_preferred: tuple[str, ...]
    matched_rejected: tuple[str, ...]
    explanations: tuple[str, ...]


def _normalise_value(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleasePreferenceError("Preference values must be non-empty text.")
    return " ".join(value.casefold().split())


def _normalise_group(attribute: str, raw: Any) -> AttributePreference:
    if not isinstance(raw, dict):
        raise ReleasePreferenceError(f"Preferences for {attribute} must be an object.")
    preferred_raw = raw.get("preferred", [])
    rejected_raw = raw.get("rejected", [])
    priority = raw.get("priority", PREFERENCE_ATTRIBUTES.index(attribute))
    if not isinstance(preferred_raw, list) or not isinstance(rejected_raw, list):
        raise ReleasePreferenceError(
            f"Preferred and rejected values for {attribute} must be lists."
        )
    if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0:
        raise ReleasePreferenceError(f"Priority for {attribute} must be a nonnegative integer.")
    preferred = tuple(dict.fromkeys(_normalise_value(item) for item in preferred_raw))
    rejected = tuple(dict.fromkeys(_normalise_value(item) for item in rejected_raw))
    overlap = set(preferred) & set(rejected)
    if overlap:
        raise ReleasePreferenceError(
            f"{attribute} values cannot be both preferred and rejected: {', '.join(sorted(overlap))}."
        )
    return AttributePreference(attribute, preferred, rejected, priority)


def normalize_release_preferences(
    payload: Mapping[str, Any] | None = None,
) -> tuple[AttributePreference, ...]:
    """Validate and normalize all supported preference attributes."""
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise ReleasePreferenceError("Release preferences must be an object.")
    unknown = set(payload) - set(PREFERENCE_ATTRIBUTES)
    if unknown:
        raise ReleasePreferenceError(
            "Unknown release preference attributes: " + ", ".join(sorted(unknown))
        )
    groups = [
        _normalise_group(attribute, payload.get(attribute, {}))
        for attribute in PREFERENCE_ATTRIBUTES
    ]
    return tuple(sorted(groups, key=lambda item: (item.priority, item.attribute)))


def evaluate_release_preferences(
    release: Mapping[str, Any],
    preferences: Mapping[str, Any] | tuple[AttributePreference, ...],
) -> PreferenceDecision:
    """Reject releases with a rejected value and explain every matched rule."""
    if not isinstance(release, Mapping):
        raise ReleasePreferenceError("Release metadata must be an object.")
    if isinstance(preferences, Mapping):
        groups = normalize_release_preferences(preferences)
    else:
        groups = tuple(preferences)
        if not all(isinstance(item, AttributePreference) for item in groups):
            raise ReleasePreferenceError("Release preferences are malformed.")

    matched_preferred = []
    matched_rejected = []
    explanations = []
    for preference in sorted(groups, key=lambda item: (item.priority, item.attribute)):
        raw_value = release.get(preference.attribute)
        if raw_value is None or not isinstance(raw_value, (str, int, float)):
            continue
        value = " ".join(str(raw_value).casefold().split())
        if value in preference.rejected:
            matched_rejected.append(preference.attribute)
            explanations.append(
                f"Rejected: {preference.attribute} is {raw_value}."
            )
        elif value in preference.preferred:
            matched_preferred.append(preference.attribute)
            explanations.append(
                f"Preferred: {preference.attribute} is {raw_value}."
            )
    return PreferenceDecision(
        accepted=not matched_rejected,
        matched_preferred=tuple(matched_preferred),
        matched_rejected=tuple(matched_rejected),
        explanations=tuple(explanations),
    )


def default_release_preferences_path() -> Path:
    """Return the XDG configuration path without creating it."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "release-preferences.json"


class ReleasePreferenceStore:
    """Load and atomically persist validated release preferences."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_release_preferences_path()

    def load(self) -> tuple[AttributePreference, ...]:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return normalize_release_preferences()
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReleasePreferenceError("Saved release preferences are invalid JSON.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != PREFERENCE_FORMAT
            or payload.get("version") != PREFERENCE_VERSION
            or not isinstance(payload.get("preferences"), dict)
        ):
            raise ReleasePreferenceError("Saved release preferences have an unsupported format.")
        return normalize_release_preferences(payload["preferences"])

    def save(self, preferences: Mapping[str, Any]) -> None:
        normalized = normalize_release_preferences(preferences)
        values = {
            item.attribute: {
                "preferred": list(item.preferred),
                "rejected": list(item.rejected),
                "priority": item.priority,
            }
            for item in normalized
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"format": PREFERENCE_FORMAT, "version": PREFERENCE_VERSION,
             "preferences": values},
            ensure_ascii=False, indent=2,
        ) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".release-preferences-", delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
