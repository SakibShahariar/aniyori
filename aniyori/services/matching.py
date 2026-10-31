"""Deterministic title matching for parsed anime releases and catalogue entries."""
from __future__ import annotations
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from ..filename_parser import ParsedAnimeFilename, parse_anime_filename

@dataclass(frozen=True, slots=True)
class ScoredAnimeMatch:
    media_id: int | str
    title: str
    score: float
    matched_title: str

@dataclass(frozen=True, slots=True)
class AnimeMatchDecision:
    status: str
    matches: tuple[ScoredAnimeMatch, ...]
    overridden: bool = False

    @property
    def best_match(self) -> ScoredAnimeMatch | None:
        if self.status != "matched" or not self.matches:
            return None
        return self.matches[0]

def normalize_anime_title(value: str) -> str:
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())

def _candidate_names(candidate: Mapping[str, Any]) -> list[str]:
    names = []
    for key in ("title", "title_english", "title_romaji", "title_native"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    aliases = candidate.get("aliases", ())
    if isinstance(aliases, (list, tuple, set, frozenset)):
        names.extend(value.strip() for value in aliases if isinstance(value, str) and value.strip())
    return names

def match_anime_title(
    title: str,
    candidates: Iterable[Mapping[str, Any]],
    *,
    aliases: Mapping[int | str, Iterable[str]] | None = None,
    overrides: Mapping[str, int | str] | None = None,
    minimum_score: float = 0.84,
    ambiguity_margin: float = 0.06,
) -> AnimeMatchDecision:
    """Rank candidates; close scores are marked ambiguous instead of guessed."""
    normalized = normalize_anime_title(title)
    if not normalized:
        return AnimeMatchDecision("no_match", ())
    if not 0.0 <= minimum_score <= 1.0:
        raise ValueError("minimum_score must be between 0 and 1")
    if not 0.0 <= ambiguity_margin <= 1.0:
        raise ValueError("ambiguity_margin must be between 0 and 1")

    candidate_list = []
    seen_ids = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        media_id = candidate.get("id")
        if isinstance(media_id, bool) or not isinstance(media_id, (int, str)):
            continue
        if not str(media_id).strip() or media_id in seen_ids:
            continue
        names = _candidate_names(candidate)
        extra_aliases = (aliases or {}).get(media_id, ())
        if isinstance(extra_aliases, str):
            extra_aliases = (extra_aliases,)
        names.extend(value.strip() for value in extra_aliases if isinstance(value, str) and value.strip())
        names = [(name, normalize_anime_title(name)) for name in names]
        names = [(name, key) for name, key in names if key]
        if names:
            seen_ids.add(media_id)
            candidate_list.append((media_id, names))
    if not candidate_list:
        return AnimeMatchDecision("no_match", ())

    override_id = None
    if overrides:
        override_id = overrides.get(normalized)
        if override_id is None:
            override_id = overrides.get(title)
    if override_id is not None:
        for media_id, names in candidate_list:
            if media_id == override_id:
                name = names[0][0]
                return AnimeMatchDecision(
                    "matched", (ScoredAnimeMatch(media_id, name, 1.0, name),), True
                )
        return AnimeMatchDecision("no_match", ())

    ranked = []
    for media_id, names in candidate_list:
        scores = [
            (1.0 if key == normalized else SequenceMatcher(None, normalized, key).ratio(), name)
            for name, key in names
        ]
        score, matched_name = max(scores, key=lambda item: (item[0], item[1].casefold()))
        ranked.append(ScoredAnimeMatch(media_id, matched_name, round(score, 6), matched_name))
    ranked.sort(key=lambda item: (-item.score, str(item.media_id), item.title.casefold()))
    matches = tuple(item for item in ranked if item.score >= minimum_score)
    if not matches:
        return AnimeMatchDecision("no_match", ())
    if len(matches) > 1 and matches[0].score - matches[1].score <= ambiguity_margin:
        return AnimeMatchDecision("ambiguous", matches)
    return AnimeMatchDecision("matched", matches)

@dataclass(frozen=True, slots=True)
class ReleaseMatchDecision:
    """Filename parsing and catalogue matching result for one local video."""

    parsed: ParsedAnimeFilename | None
    decision: AnimeMatchDecision

    @property
    def status(self) -> str:
        return "unparsed" if self.parsed is None else self.decision.status


def match_release_filename(
    filename: str,
    candidates: Iterable[Mapping[str, Any]],
    *,
    aliases: Mapping[int | str, Iterable[str]] | None = None,
    overrides: Mapping[str, int | str] | None = None,
    minimum_score: float = 0.84,
    ambiguity_margin: float = 0.06,
) -> ReleaseMatchDecision:
    """Parse a release filename, then match its title without guessing ambiguity."""
    parsed = parse_anime_filename(filename)
    if parsed is None:
        return ReleaseMatchDecision(None, AnimeMatchDecision("no_match", ()))
    decision = match_anime_title(
        parsed.title,
        candidates,
        aliases=aliases,
        overrides=overrides,
        minimum_score=minimum_score,
        ambiguity_margin=ambiguity_margin,
    )
    return ReleaseMatchDecision(parsed, decision)
