"""Refresh configured release feeds and match entries to the local catalogue."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..filename_parser import parse_anime_filename
from .matching import AnimeMatchDecision, match_anime_title
from .release_scoring import (
    DEFAULT_WEIGHTS, ReleaseScore, score_release, validate_minimum_score,
)
from .rss import FeedEntry, FeedParseError, RSSFeed, _safe_link, parse_release_feed
from .release_rules import ReleaseRule, evaluate_release_rules, normalize_release_rules


DEFAULT_FEED_TIMEOUT = 15


class FeedFetchError(RuntimeError):
    """Raised when a configured release feed cannot be retrieved safely."""


@dataclass(frozen=True, slots=True)
class MonitoredRelease:
    """A feed entry enriched with conservative catalogue and quality results."""

    feed_name: str
    feed_url: str
    entry: FeedEntry
    match_status: str
    media_id: int | str | None
    matched_title: str | None
    episode: int | None
    season: int | None
    score: ReleaseScore
    metadata: Mapping[str, Any]
    eligible: bool
    decision_explanation: str
    rule_status: str = "unmatched"
    rule_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FeedRefreshResult:
    """The independent outcome of refreshing one configured feed."""

    feed: RSSFeed
    releases: tuple[MonitoredRelease, ...]
    error: str | None = None


def fetch_feed_content(
    url: str,
    *,
    timeout: int = DEFAULT_FEED_TIMEOUT,
    max_bytes: int = 2_000_000,
) -> bytes:
    """Fetch one HTTP(S) feed with a timeout and a strict response-size bound."""
    safe_url = _safe_link(url)
    if safe_url is None:
        raise FeedFetchError("Feed URL must be a credential-free HTTP(S) URL.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("Feed timeout must be greater than zero.")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("Feed size limit must be a positive integer.")

    request = Request(
        safe_url,
        headers={
            "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml",
            "User-Agent": "Aniyori/0.1.0 (Linux desktop anime tracker)",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            final_url = _safe_link(response.geturl())
            if final_url is None:
                raise FeedFetchError("Feed redirected to an unsafe URL.")
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise FeedFetchError("Feed exceeds the maximum allowed size.")
                except ValueError:
                    pass
            content = response.read(max_bytes + 1)
    except FeedFetchError:
        raise
    except HTTPError as error:
        raise FeedFetchError(f"Feed server returned HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise FeedFetchError(f"Could not retrieve feed: {error}") from error

    if len(content) > max_bytes:
        raise FeedFetchError("Feed exceeds the maximum allowed size.")
    return content


def _release_metadata(entry: FeedEntry, parsed) -> dict[str, Any]:
    """Extract only explicit, recognizable release facts from feed text."""
    metadata: dict[str, Any] = {}
    if parsed is not None:
        if parsed.resolution:
            metadata["resolution"] = parsed.resolution
        if parsed.source:
            metadata["source"] = parsed.source
        if parsed.release_group:
            metadata["release_group"] = parsed.release_group

    text = " ".join((entry.title, entry.summary, *entry.categories))
    audio_patterns = (
        (r"(?i)\bDTS[- .]?HD\b", "DTS-HD"),
        (r"(?i)\bTrueHD\b", "TrueHD"),
        (r"(?i)\bFLAC\b", "FLAC"),
        (r"(?i)\bDTS\b", "DTS"),
        (r"(?i)\bAAC\b", "AAC"),
        (r"(?i)\bOpus\b", "Opus"),
        (r"(?i)\bAC-?3\b", "AC3"),
        (r"(?i)\bMP3\b", "MP3"),
    )
    for pattern, value in audio_patterns:
        if re.search(pattern, text):
            metadata["audio"] = value
            break

    subtitle_patterns = (
        (r"(?i)\b(?:multi[- ]?sub|multi[- ]?subtitle)\b", "Multi-Sub"),
        (r"(?i)\b(?:soft[- ]?sub|soft[- ]?subs)\b", "SoftSub"),
        (r"(?i)\b(?:hard[- ]?sub|hard[- ]?subs)\b", "HardSub"),
        (r"(?i)\b(?:eng(?:lish)?[- ]?subs?|english subtitles?)\b", "English"),
        (r"(?i)\b(?:no subs?|no subtitles?)\b", "None"),
    )
    for pattern, value in subtitle_patterns:
        if re.search(pattern, text):
            metadata["subtitles"] = value
            break

    size_match = re.search(
        r"(?i)\b(\d+(?:\.\d+)?)\s*(GiB|GB|MiB|MB)\b", text
    )
    if size_match:
        amount = float(size_match.group(1))
        unit = size_match.group(2).casefold()
        multiplier = 1024 if unit == "gib" else 1000 if unit == "gb" else 1
        metadata["file_size_mb"] = round(amount * multiplier, 2)

    for key in ("seeders", "leechers", "downloads"):
        value = getattr(entry, key, None)
        if value is not None:
            metadata[key] = value
    if getattr(entry, "size", None):
        metadata["size"] = entry.size
    if getattr(entry, "info_hash", None):
        metadata["info_hash"] = entry.info_hash

    if "seeders" not in metadata:
        seeder_match = re.search(
            r"(?i)\bseeders?\s*[:=]\s*(\d+)\b|\b(\d+)\s+seeders?\b", text
        )
        if seeder_match:
            metadata["seeders"] = int(seeder_match.group(1) or seeder_match.group(2))

    size_text = getattr(entry, "size", None) or text
    size_match = re.search(
        r"(?i)\b(\d+(?:\.\d+)?)\s*(GiB|GB|MiB|MB)\b", size_text
    )
    if size_match:
        amount = float(size_match.group(1))
        unit = size_match.group(2).casefold()
        multiplier = 1024 if unit == "gib" else 1000 if unit == "gb" else 1
        metadata["file_size_mb"] = round(amount * multiplier, 2)
    return metadata


def _enrich_entry(
    feed: RSSFeed,
    entry: FeedEntry,
    candidates: tuple[Mapping[str, Any], ...],
    *,
    preferences: Mapping[str, Any] | tuple | None,
    weights: Mapping[str, float] | None,
    minimum_score: float,
    rules: tuple[ReleaseRule, ...],
) -> MonitoredRelease:
    parsed = parse_anime_filename(entry.title)
    if parsed is None:
        decision = AnimeMatchDecision("unparsed", ())
    else:
        decision = match_anime_title(parsed.title, candidates)
    release_metadata = _release_metadata(entry, parsed)

    quality = score_release(
        release_metadata,
        weights=weights,
        preferences=preferences,
    )
    rule_decision = evaluate_release_rules({
        "title": entry.title,
        "release_group": release_metadata.get("release_group"),
        "resolution": release_metadata.get("resolution"),
        "source": release_metadata.get("source"),
        "episode": parsed.episode if parsed else None,
        "summary": entry.summary,
        "categories": entry.categories,
    }, rules)
    best = decision.best_match
    return MonitoredRelease(
        feed_name=feed.name,
        feed_url=feed.url,
        entry=entry,
        match_status=decision.status,
        media_id=best.media_id if best else None,
        matched_title=best.title if best else None,
        episode=parsed.episode if parsed else None,
        season=parsed.season if parsed else None,
        score=quality,
        metadata=release_metadata,
        eligible=(
            quality.accepted
            and quality.score >= minimum_score
            and rule_decision.status != "discarded"
        ),
        decision_explanation=(
            (quality.explanation
             if quality.score >= minimum_score
             else quality.explanation + f"; Below minimum score {minimum_score:g}/100")
            + (f"; {rule_decision.reason}" if rule_decision.reason else "")
        ),
        rule_status=rule_decision.status,
        rule_reason=rule_decision.reason,
    )


def refresh_release_feeds(
    feeds: Iterable[RSSFeed],
    candidates: Iterable[Mapping[str, Any]],
    *,
    fetcher: Callable[[str], bytes | str] = fetch_feed_content,
    preferences: Mapping[str, Any] | tuple | None = None,
    weights: Mapping[str, float] | None = None,
    minimum_score: float = 0.0,
    rules: Iterable[ReleaseRule] = (),
) -> tuple[FeedRefreshResult, ...]:
    """Refresh enabled feeds independently; one failure never aborts other feeds.

    The fetcher is injectable so callers can use a worker, deterministic tests,
    or a different transport without coupling network I/O to parsing/matching.
    """
    if isinstance(feeds, (str, bytes)):
        raise ValueError("Feeds must be an iterable of RSSFeed values.")
    if isinstance(candidates, (str, bytes)):
        raise ValueError("Catalogue candidates must be an iterable of mappings.")
    cutoff = validate_minimum_score(minimum_score)
    normalized_rules = normalize_release_rules(rules)
    candidate_list = tuple(item for item in candidates if isinstance(item, Mapping))
    results = []
    for feed in feeds:
        if not isinstance(feed, RSSFeed):
            raise ValueError("Feeds must contain RSSFeed values.")
        if not feed.enabled:
            continue
        try:
            content = fetcher(feed.url)
            entries = parse_release_feed(content)
            releases = tuple(sorted(
                (
                    _enrich_entry(
                        feed,
                        entry,
                        candidate_list,
                        preferences=preferences,
                        weights=weights if weights is not None else DEFAULT_WEIGHTS,
                        minimum_score=cutoff,
                        rules=normalized_rules,
                    )
                    for entry in entries
                ),
                key=lambda release: (not release.eligible, -release.score.score),
            ))
            results.append(FeedRefreshResult(feed, releases))
        except Exception as error:
            # Keep a failed feed visible to the caller while continuing with
            # the remaining sources. Do not allow one broken source to abort
            # the whole refresh operation.
            results.append(FeedRefreshResult(feed, (), str(error) or error.__class__.__name__))
    return tuple(results)


def filter_release_results(
    results: Iterable[FeedRefreshResult],
    *,
    query: str = "",
    eligible_only: bool = False,
    sort_by: str = "quality",
) -> tuple[FeedRefreshResult, ...]:
    """Filter and sort refreshed releases without mutating cached feed results."""
    if not isinstance(query, str):
        raise ValueError("Release search query must be text.")
    if not isinstance(eligible_only, bool):
        raise ValueError("Eligible-only filter must be a boolean.")
    sort_keys = {"quality", "newest", "seeders", "title"}
    if sort_by not in sort_keys:
        raise ValueError("Unsupported release sort order.")

    needle = query.strip().casefold()
    filtered_results = []
    for result in results:
        if result.error:
            filtered_results.append(result)
            continue
        releases = []
        for release in result.releases:
            if eligible_only and not release.eligible:
                continue
            if needle:
                searchable = " ".join((
                    release.entry.title,
                    release.feed_name,
                    release.matched_title or "",
                    str(release.metadata.get("release_group", "")),
                    *release.entry.categories,
                )).casefold()
                if needle not in searchable:
                    continue
            releases.append(release)

        if sort_by == "newest":
            key = lambda item: (
                item.entry.published_at is None,
                -(item.entry.published_at.timestamp() if item.entry.published_at else 0),
            )
        elif sort_by == "seeders":
            key = lambda item: (
                item.metadata.get("seeders") is None,
                -(item.metadata.get("seeders") or 0),
            )
        elif sort_by == "title":
            key = lambda item: item.entry.title.casefold()
        else:
            rule_priority = {"preferred": 0, "wanted": 1, "unmatched": 2, "discarded": 3}
            key = lambda item: (
                not item.eligible, rule_priority.get(item.rule_status, 2),
                -item.score.score, item.entry.title.casefold(),
            )
        releases.sort(key=key)
        filtered_results.append(FeedRefreshResult(result.feed, tuple(releases), result.error))
    return tuple(filtered_results)
