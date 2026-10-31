"""Deterministic, explainable release-quality scoring."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .release_preferences import evaluate_release_preferences


DEFAULT_WEIGHTS = {
    "resolution": 0.25,
    "source": 0.20,
    "audio": 0.15,
    "subtitles": 0.15,
    "release_group": 0.10,
    "file_size": 0.05,
    "seeders": 0.10,
}
SOURCE_SCORES = {
    "bluray": 1.0,
    "blu-ray": 1.0,
    "bdrip": 0.90,
    "web-dl": 0.85,
    "webdl": 0.85,
    "webrip": 0.75,
    "hdtv": 0.55,
    "dvd": 0.40,
}
AUDIO_SCORES = {
    "flac": 1.0,
    "truehd": 1.0,
    "dts-hd": 0.95,
    "dtshd": 0.95,
    "dts": 0.85,
    "aac": 0.75,
    "opus": 0.75,
    "ac3": 0.65,
    "mp3": 0.40,
}
SUBTITLE_SCORES = {
    "multi": 1.0,
    "multi-sub": 1.0,
    "english": 0.85,
    "softsub": 0.80,
    "hardsub": 0.55,
    "none": 0.10,
}
QUALITY_FIELDS = frozenset(DEFAULT_WEIGHTS)


@dataclass(frozen=True, slots=True)
class ScoreFactor:
    """One normalized score contribution and its explanation."""

    name: str
    value: float
    weight: float
    contribution: float
    explanation: str


@dataclass(frozen=True, slots=True)
class ReleaseScore:
    """A normalized 0–100 score with its factors and preference decision."""

    score: float
    factors: tuple[ScoreFactor, ...]
    accepted: bool = True
    preference_explanations: tuple[str, ...] = ()

    @property
    def explanation(self) -> str:
        parts = [factor.explanation for factor in self.factors]
        parts.extend(self.preference_explanations)
        return "; ".join(parts) if parts else "No supported release metadata was available to score."


def _normalise_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return re.sub(r"\s+", "", value.casefold()).replace("_", "-")


def _resolution_score(value: Any) -> tuple[float, str] | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        pixels = value
    elif isinstance(value, str):
        match = re.search(r"(\d{3,4})\s*p?", value.casefold())
        if not match:
            return None
        pixels = int(match.group(1))
    else:
        return None
    if pixels not in (480, 576, 720, 1080, 1440, 2160, 4320):
        return None
    rank = {480: 0.35, 576: 0.4, 720: 0.6, 1080: 0.82, 1440: 0.92, 2160: 1.0, 4320: 1.0}[pixels]
    return rank, f"Resolution {pixels}p ({rank * 100:.0f}% quality weight)"


def _categorical_score(value: Any, scores: Mapping[str, float], label: str):
    normalized = _normalise_text(value)
    if normalized is None:
        return None
    score = scores.get(normalized)
    if score is None:
        return 0.5, f"{label} {value} is unranked; neutral score"
    return score, f"{label} {value} ({score * 100:.0f}% quality weight)"


def _numeric_score(value: Any, *, maximum: float, label: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    if value == 0:
        return 0.0, f"{label} is zero"
    score = min(value / maximum, 1.0)
    return score, f"{label} {value:g} ({score * 100:.0f}% availability weight)"


def _validate_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    result = dict(DEFAULT_WEIGHTS)
    if weights is None:
        return result
    if not isinstance(weights, Mapping):
        raise ValueError("Weights must be a mapping.")
    for name, value in weights.items():
        if name not in QUALITY_FIELDS:
            raise ValueError(f"Unknown release score weight: {name}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Weight for {name} must be a finite nonnegative number.")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Weight for {name} must be a finite nonnegative number.")
        result[name] = float(value)
    if not any(result.values()):
        raise ValueError("At least one release score weight must be greater than zero.")
    return result


def score_release(
    release: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
    preferred_groups: Iterable[str] = (),
    rejected_groups: Iterable[str] = (),
    preferences: Mapping[str, Any] | None = None,
) -> ReleaseScore:
    """Score one release using available metadata; missing fields are omitted.

    The final result is a weighted average of only the available factors, so a
    missing field neither acts as a penalty nor gives a release an advantage.
    """
    if not isinstance(release, Mapping):
        raise ValueError("Release metadata must be a mapping.")
    configured_weights = _validate_weights(weights)
    preference_decision = (
        evaluate_release_preferences(release, preferences)
        if preferences is not None else None
    )
    preferred = {_normalise_text(item) for item in preferred_groups}
    rejected = {_normalise_text(item) for item in rejected_groups}
    preferred.discard(None)
    rejected.discard(None)

    raw = {
        "resolution": _resolution_score(release.get("resolution")),
        "source": _categorical_score(release.get("source"), SOURCE_SCORES, "Source"),
        "audio": _categorical_score(release.get("audio"), AUDIO_SCORES, "Audio"),
        "subtitles": _categorical_score(release.get("subtitles"), SUBTITLE_SCORES, "Subtitles"),
        "file_size": _numeric_score(release.get("file_size_mb"), maximum=2000, label="File size"),
        "seeders": _numeric_score(release.get("seeders"), maximum=100, label="Seeders"),
    }

    group = _normalise_text(release.get("release_group"))
    if group is not None:
        if group in rejected:
            raw["release_group"] = (0.0, f"Release group {release.get('release_group')} is rejected")
        elif group in preferred:
            raw["release_group"] = (1.0, f"Release group {release.get('release_group')} is preferred")
        else:
            raw["release_group"] = (0.5, f"Release group {release.get('release_group')} has no preference")
    else:
        raw["release_group"] = None

    if preference_decision is not None:
        preferred_attributes = set(preference_decision.matched_preferred)
        rejected_attributes = set(preference_decision.matched_rejected)
        for attribute in preferred_attributes | rejected_attributes:
            item = raw.get(attribute)
            if item is None:
                continue
            _value, explanation = item
            preferred_match = attribute in preferred_attributes
            raw[attribute] = (
                1.0 if preferred_match else 0.0,
                f"Preference matched ({'preferred' if preferred_match else 'rejected'}): {explanation}",
            )

    factors = []
    weighted_total = 0.0
    available_weight = 0.0
    for name in DEFAULT_WEIGHTS:
        item = raw[name]
        weight = configured_weights[name]
        if item is None or weight == 0:
            continue
        value, explanation = item
        contribution = value * weight
        weighted_total += contribution
        available_weight += weight
        factors.append(
            ScoreFactor(name, value, weight, contribution, explanation)
        )

    if available_weight == 0:
        return ReleaseScore(
            0.0, (),
            accepted=preference_decision.accepted if preference_decision else True,
            preference_explanations=preference_decision.explanations if preference_decision else (),
        )
    return ReleaseScore(
        score=round(weighted_total / available_weight * 100, 2),
        factors=tuple(factors),
        accepted=preference_decision.accepted if preference_decision else True,
        preference_explanations=preference_decision.explanations if preference_decision else (),
    )


def rank_releases(
    releases: Iterable[Mapping[str, Any]],
    *,
    weights: Mapping[str, float] | None = None,
    preferred_groups: Iterable[str] = (),
    rejected_groups: Iterable[str] = (),
    preferences: Mapping[str, Any] | None = None,
) -> list[tuple[Mapping[str, Any], ReleaseScore]]:
    """Return releases sorted by score, preserving input order for ties."""
    preferred = tuple(preferred_groups)
    rejected = tuple(rejected_groups)
    ranked = [
        (
            release,
            score_release(
                release,
                weights=weights,
                preferred_groups=preferred,
                rejected_groups=rejected,
                preferences=preferences,
            ),
            index,
        )
        for index, release in enumerate(releases)
    ]
    ranked.sort(key=lambda item: (not item[1].accepted, -item[1].score, item[2]))
    return [(release, score) for release, score, _index in ranked]


SCORING_SETTINGS_FORMAT = "aniyori-release-scoring"
SCORING_SETTINGS_VERSION = 1


def default_release_scoring_path() -> Path:
    """Return the XDG configuration path without creating it."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "release-scoring.json"


class ReleaseScoringSettingsStore:
    """Load and atomically persist validated release-scoring weights."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_release_scoring_path()

    def load(self) -> dict[str, float]:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return dict(DEFAULT_WEIGHTS)
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Saved release-scoring settings are invalid JSON.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != SCORING_SETTINGS_FORMAT
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("version"), int)
            or payload.get("version") != SCORING_SETTINGS_VERSION
            or not isinstance(payload.get("weights"), dict)
        ):
            raise ValueError("Saved release-scoring settings have an unsupported format.")
        return _validate_weights(payload["weights"])

    def save(self, weights: Mapping[str, float]) -> None:
        normalized = _validate_weights(weights)
        content = json.dumps(
            {
                "format": SCORING_SETTINGS_FORMAT,
                "version": SCORING_SETTINGS_VERSION,
                "weights": normalized,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".release-scoring-", delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
