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
from .release_scoring import DEFAULT_WEIGHTS, ReleaseScore, score_release
from .rss import FeedEntry, FeedParseError, RSSFeed, _safe_link, parse_release_feed


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

    seeder_match = re.search(
        r"(?i)\bseeders?\s*[:=]\s*(\d+)\b|\b(\d+)\s+seeders?\b", text
    )
    if seeder_match:
        metadata["seeders"] = int(seeder_match.group(1) or seeder_match.group(2))
    return metadata


def _enrich_entry(
    feed: RSSFeed,
    entry: FeedEntry,
    candidates: tuple[Mapping[str, Any], ...],
    *,
    preferences: Mapping[str, Any] | tuple | None,
    weights: Mapping[str, float] | None,
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
    )


def refresh_release_feeds(
    feeds: Iterable[RSSFeed],
    candidates: Iterable[Mapping[str, Any]],
    *,
    fetcher: Callable[[str], bytes | str] = fetch_feed_content,
    preferences: Mapping[str, Any] | tuple | None = None,
    weights: Mapping[str, float] | None = None,
) -> tuple[FeedRefreshResult, ...]:
    """Refresh enabled feeds independently; one failure never aborts other feeds.

    The fetcher is injectable so callers can use a worker, deterministic tests,
    or a different transport without coupling network I/O to parsing/matching.
    """
    if isinstance(feeds, (str, bytes)):
        raise ValueError("Feeds must be an iterable of RSSFeed values.")
    if isinstance(candidates, (str, bytes)):
        raise ValueError("Catalogue candidates must be an iterable of mappings.")
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
            releases = tuple(
                _enrich_entry(
                    feed,
                    entry,
                    candidate_list,
                    preferences=preferences,
                    weights=weights if weights is not None else DEFAULT_WEIGHTS,
                )
                for entry in entries
            )
            results.append(FeedRefreshResult(feed, releases))
        except Exception as error:
            # Keep a failed feed visible to the caller while continuing with
            # the remaining sources. Do not allow one broken source to abort
            # the whole refresh operation.
            results.append(FeedRefreshResult(feed, (), str(error) or error.__class__.__name__))
    return tuple(results)
