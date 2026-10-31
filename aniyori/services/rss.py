"""Safe parsing for RSS 2.0 and Atom release feeds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urlsplit
import re
import xml.etree.ElementTree as ET


MAX_FEED_BYTES = 2_000_000
MAX_FEED_ENTRIES = 500


class FeedParseError(ValueError):
    """Raised when a feed is malformed, unsupported, or too large."""


@dataclass(frozen=True, slots=True)
class FeedEntry:
    """A normalized item from an RSS or Atom feed."""

    title: str
    link: str | None
    identifier: str | None
    published_at: datetime | None
    summary: str
    categories: tuple[str, ...]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _child_text(element: ET.Element, *names: str) -> str:
    wanted = {name.casefold() for name in names}
    for child in element:
        if _local_name(child.tag) in wanted and child.text:
            value = child.text.strip()
            if value:
                return value
    return ""


def _safe_link(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        parsed.port  # Validate malformed port values.
    except ValueError:
        return None
    return candidate


def _atom_link(element: ET.Element) -> str | None:
    links = [
        child for child in element
        if _local_name(child.tag) == "link"
    ]
    for link in links:
        relation = link.attrib.get("rel", "alternate").casefold()
        if relation == "alternate":
            safe = _safe_link(link.attrib.get("href"))
            if safe:
                return safe
    return None


def _published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _entry(element: ET.Element, *, atom: bool) -> FeedEntry | None:
    title = _child_text(element, "title")
    if not title:
        return None
    if atom:
        link = _atom_link(element)
        identifier = _child_text(element, "id") or link
        published = _child_text(element, "published", "updated")
        summary = _child_text(element, "summary", "content")
    else:
        link = _safe_link(_child_text(element, "link"))
        identifier = _child_text(element, "guid") or link
        published = _child_text(element, "pubDate")
        summary = _child_text(element, "description", "content:encoded")
    categories = tuple(
        value for value in (
            (child.attrib.get("term", "").strip() if atom else (child.text or "").strip())
            for child in element if _local_name(child.tag) == "category"
        ) if value
    )
    return FeedEntry(
        title=title,
        link=link,
        identifier=identifier or None,
        published_at=_published(published),
        summary=summary,
        categories=tuple(dict.fromkeys(categories)),
    )


def parse_release_feed(
    content: str | bytes,
    *,
    max_bytes: int = MAX_FEED_BYTES,
    max_entries: int = MAX_FEED_ENTRIES,
) -> tuple[FeedEntry, ...]:
    """Parse bounded RSS 2.0 or Atom XML into normalized feed entries.

    HTML in descriptions is retained as text and must be escaped by any UI
    before display. Only credential-free HTTP(S) entry links are accepted.
    """
    if isinstance(content, str):
        raw = content.encode("utf-8")
    elif isinstance(content, bytes):
        raw = content
    else:
        raise FeedParseError("Feed content must be text or bytes.")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise FeedParseError("Feed size limit must be a positive integer.")
    if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 0:
        raise FeedParseError("Feed entry limit must be a nonnegative integer.")
    if len(raw) > max_bytes:
        raise FeedParseError("Feed exceeds the maximum allowed size.")
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise FeedParseError("DTD and entity declarations are not supported.")

    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, ValueError, UnicodeError) as error:
        raise FeedParseError("Feed contains invalid XML.") from error

    root_name = _local_name(root.tag)
    if root_name == "rss":
        channel = next(
            (child for child in root if _local_name(child.tag) == "channel"),
            None,
        )
        if channel is None:
            raise FeedParseError("RSS feed is missing its channel.")
        elements = (child for child in channel if _local_name(child.tag) == "item")
        atom = False
    elif root_name == "feed":
        elements = (child for child in root if _local_name(child.tag) == "entry")
        atom = True
    else:
        raise FeedParseError("Unsupported feed format; expected RSS 2.0 or Atom.")

    entries = []
    for element in elements:
        if len(entries) >= max_entries:
            break
        item = _entry(element, atom=atom)
        if item is not None:
            entries.append(item)
    return tuple(entries)


RSS_FEED_FORMAT = "aniyori-rss-feeds"
RSS_FEED_VERSION = 1


@dataclass(frozen=True, slots=True)
class RSSFeed:
    """A user-configured RSS or Atom feed source."""

    name: str
    url: str
    enabled: bool = True


def _validate_feed(feed: RSSFeed) -> RSSFeed:
    if not isinstance(feed, RSSFeed):
        raise FeedParseError("Feed sources must be RSSFeed values.")
    name = feed.name.strip() if isinstance(feed.name, str) else ""
    url = _safe_link(feed.url)
    if not name:
        raise FeedParseError("Feed names must be non-empty text.")
    if url is None:
        raise FeedParseError("Feed URLs must be credential-free HTTP(S) URLs.")
    if not isinstance(feed.enabled, bool):
        raise FeedParseError("Feed enabled state must be a boolean.")
    return RSSFeed(name=name, url=url, enabled=feed.enabled)


def default_rss_feed_path() -> Path:
    """Return the XDG configuration path without creating it."""
    import os
    from pathlib import Path

    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "rss-feeds.json"


class RSSFeedStore:
    """Persist validated feed sources atomically in the user's config directory."""

    def __init__(self, path=None):
        from pathlib import Path

        self.path = Path(path) if path is not None else default_rss_feed_path()

    def load(self) -> tuple[RSSFeed, ...]:
        import json

        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FeedParseError("Saved RSS feeds are invalid JSON.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != RSS_FEED_FORMAT
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("version"), int)
            or payload.get("version") != RSS_FEED_VERSION
            or not isinstance(payload.get("feeds"), list)
        ):
            raise FeedParseError("Saved RSS feeds have an unsupported format.")
        feeds = []
        seen = set()
        for item in payload["feeds"]:
            if not isinstance(item, dict):
                raise FeedParseError("Saved RSS feed entries must be objects.")
            feed = _validate_feed(RSSFeed(
                name=item.get("name"),
                url=item.get("url"),
                enabled=item.get("enabled", True),
            ))
            key = feed.url.casefold()
            if key in seen:
                raise FeedParseError("Saved RSS feeds contain duplicate URLs.")
            seen.add(key)
            feeds.append(feed)
        return tuple(feeds)

    def save(self, feeds: Iterable[RSSFeed]) -> None:
        import json
        import os
        import tempfile

        if isinstance(feeds, (str, bytes)):
            raise FeedParseError("RSS feeds must be an iterable of feed sources.")
        normalized = tuple(_validate_feed(feed) for feed in feeds)
        seen = set()
        for feed in normalized:
            key = feed.url.casefold()
            if key in seen:
                raise FeedParseError("RSS feed URLs must be unique.")
            seen.add(key)
        payload = {
            "format": RSS_FEED_FORMAT,
            "version": RSS_FEED_VERSION,
            "feeds": [
                {"name": feed.name, "url": feed.url, "enabled": feed.enabled}
                for feed in normalized
            ],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".rss-feeds-", delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def add(self, url: str, name: str | None = None) -> tuple[RSSFeed, ...]:
        feeds = list(self.load())
        safe_url = _safe_link(url)
        if safe_url is None:
            raise FeedParseError("Feed URLs must be credential-free HTTP(S) URLs.")
        if any(feed.url.casefold() == safe_url.casefold() for feed in feeds):
            raise FeedParseError("This RSS feed URL is already configured.")
        label = name.strip() if isinstance(name, str) else ""
        if not label:
            label = safe_url
        feeds.append(RSSFeed(label, safe_url))
        self.save(feeds)
        return tuple(feeds)

    def remove(self, url: str) -> tuple[RSSFeed, ...]:
        target = _safe_link(url)
        if target is None:
            raise FeedParseError("Feed URLs must be credential-free HTTP(S) URLs.")
        feeds = [feed for feed in self.load() if feed.url.casefold() != target.casefold()]
        self.save(feeds)
        return tuple(feeds)
