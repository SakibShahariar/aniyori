"""Deterministic, explainable release-quality scoring."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


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
    """A normalized 0–100 score with the factors that produced it."""

    score: float
    factors: tuple[ScoreFactor, ...]

    @property
    def explanation(self) -> str:
        if not self.factors:
            return "No supported release metadata was available to score."
        return "; ".join(factor.explanation for factor in self.factors)


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
) -> ReleaseScore:
    """Score one release using available metadata; missing fields are omitted.

    The final result is a weighted average of only the available factors, so a
    missing field neither acts as a penalty nor gives a release an advantage.
    """
    if not isinstance(release, Mapping):
        raise ValueError("Release metadata must be a mapping.")
    configured_weights = _validate_weights(weights)
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
        return ReleaseScore(0.0, ())
    return ReleaseScore(
        score=round(weighted_total / available_weight * 100, 2),
        factors=tuple(factors),
    )


def rank_releases(
    releases: Iterable[Mapping[str, Any]],
    *,
    weights: Mapping[str, float] | None = None,
    preferred_groups: Iterable[str] = (),
    rejected_groups: Iterable[str] = (),
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
            ),
            index,
        )
        for index, release in enumerate(releases)
    ]
    ranked.sort(key=lambda item: (-item[1].score, item[2]))
    return [(release, score) for release, score, _index in ranked]
