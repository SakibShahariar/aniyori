"""Conservative parser for common anime release filenames."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
import re

_VIDEO_SUFFIXES = {".mkv", ".mp4", ".avi", ".webm", ".mov", ".m4v", ".ts"}
_RESOLUTION = re.compile(r"(?i)\b(2160|1440|1080|720|576|480|360)p\b")
_SOURCE = re.compile(r"(?i)\b(BluRay|BDRip|BRRip|WEB[- .]?DL|WEBRip|HDTV|DVD|DVDRip)\b")
_VERSION = re.compile(r"(?i)v(\d+)(?=$|[ ._\-\[])")
_QUALITY_SUFFIX = re.compile(
    r"(?i)(?:^|[ ._\-])(?:2160p|1440p|1080p|720p|576p|480p|360p|"
    r"WEB[- .]?DL|WEBRip|BluRay|BDRip|BRRip|HDTV|DVDRip|DVD)"
    r"(?:$|[ ._\-])"
)
_EPISODE_PATTERNS = (
    re.compile(r"(?i)(?:^|[ ._\-])S(\d{1,2})E(\d{1,3})(?:\b|$)"),
    re.compile(r"(?i)(?:^|[ ._\-])第(\d{1,3})話"),
    re.compile(r"(?i)(?:^|[ ._\-])-[ ._]*(\d{1,4})(?:v\d+)?(?=[ ._\-]|$|\[|\()"),
    re.compile(r"(?i)(?:^|[ ._])(?<!\d)(\d{1,3})(?:v\d)?(?=\s*(?:\[|\(|$))"),
)
_HASH = re.compile(r"(?i)\[[0-9a-f]{8,}\]")


@dataclass(frozen=True, slots=True)
class ParsedAnimeFilename:
    title: str
    episode: int
    season: int | None = None
    episode_title: str | None = None
    release_group: str | None = None
    resolution: str | None = None
    source: str | None = None
    version: int | None = None


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[._]+", " ", value)).strip(" -_.[]")


def parse_anime_filename(filename: str) -> ParsedAnimeFilename | None:
    """Parse recognizable episode releases; leave ambiguous names unmatched."""
    if not isinstance(filename, str) or not filename.strip():
        return None
    # Normalize Windows separators so imported paths parse on Linux too.
    name = PurePath(filename.replace("\\\\", "/")).name
    suffix = PurePath(name).suffix
    if suffix.lower() in _VIDEO_SUFFIXES:
        name = name[:-len(suffix)]
    if not name:
        return None

    group = None
    group_match = re.match(r"^\[([^\]]+)\]\s*", name)
    if group_match:
        group = group_match.group(1).strip() or None
        name = name[group_match.end():]

    name = _HASH.sub(" ", name)
    resolution_match = _RESOLUTION.search(name)
    source_match = _SOURCE.search(name)
    version_match = _VERSION.search(name)
    resolution = f"{resolution_match.group(1)}p" if resolution_match else None
    source = source_match.group(1).replace(" ", "") if source_match else None
    version = int(version_match.group(1)) if version_match else None

    episode_match = None
    pattern_index = None
    for index, pattern in enumerate(_EPISODE_PATTERNS):
        episode_match = pattern.search(name)
        if episode_match:
            pattern_index = index
            break
    if episode_match is None:
        return None

    if pattern_index == 0:
        season, episode = int(episode_match.group(1)), int(episode_match.group(2))
    else:
        season, episode = None, int(episode_match.group(1))

    title = _clean(name[:episode_match.start()])
    if not title:
        return None
    remainder = re.sub(r"(?i)^\s*[-_. ]+\s*", "", name[episode_match.end():])
    remainder = re.sub(r"(?i)\s+v\d+(?=\s*(?:\[|\(|$))", "", remainder)
    quality_match = _QUALITY_SUFFIX.search(remainder)
    if quality_match:
        remainder = remainder[:quality_match.start()]
    remainder = re.split(
        r"(?i)\s*[\[(](?:\d{3,4}p|WEB[- .]?DL|WEBRip|BluRay|BDRip|HDTV|v\d+)\b",
        remainder, maxsplit=1
    )[0]
    episode_title = _clean(remainder) or None

    return ParsedAnimeFilename(
        title=title, episode=episode, season=season,
        episode_title=episode_title, release_group=group,
        resolution=resolution, source=source, version=version,
    )
