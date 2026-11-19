"""Small, dependency-free AniList GraphQL client.

This module deliberately does not handle OAuth or user-list mutations yet.
Catalogue search is public; authenticated sync will be added separately.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .metadata_cache import MetadataCache
from ..models import MAX_EPISODE_COUNT
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from .network import open_request


ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
DEFAULT_TIMEOUT = 15
MAX_ANILIST_RESPONSE_BYTES = 2_000_000


class AniListError(RuntimeError):
    """Raised when AniList cannot return a usable response."""


SEARCH_QUERY = """
query SearchAnime($search: String!, $perPage: Int!) {
  Page(perPage: $perPage) {
    media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
      id
      title { romaji english native }
      episodes
      format
      status
      seasonYear
      coverImage { medium large }
      siteUrl
      trailer { id site thumbnail }
    }
  }
}
"""

SEASON_QUERY = """
query SeasonAnime($season: MediaSeason!, $seasonYear: Int!, $perPage: Int!) {
  Page(page: 1, perPage: $perPage) {
    media(type: ANIME, season: $season, seasonYear: $seasonYear, sort: POPULARITY_DESC) {
      id
      title { romaji english native }
      episodes
      format
      status
      season
      seasonYear
      popularity
      averageScore
      startDate { year month day }
      coverImage { medium large }
      siteUrl
      genres
      nextAiringEpisode { airingAt timeUntilAiring episode }
      trailer { id site thumbnail }
    }
  }
}
"""


TRENDING_QUERY = """
query TrendingAnime($perPage: Int!) {
  Page(page: 1, perPage: $perPage) {
    media(type: ANIME, sort: TRENDING_DESC) {
      id
      title { romaji english native }
      episodes
      format
      status
      seasonYear
      popularity
      averageScore
      coverImage { medium large }
      siteUrl
      genres
      trailer { id site thumbnail }
    }
  }
}
"""


MONTH_AIRING_QUERY = """
query MonthAiring($ids: [Int!], $from: Int, $to: Int, $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    airingSchedules(mediaId_in: $ids, airingAt_greater: $from, airingAt_lesser: $to, sort: TIME) {
      airingAt
      episode
      mediaId
    }
  }
}
"""


AIRING_QUERY = """
query AiringSchedules($ids: [Int!]!) {
  Page(perPage: 50) {
    media(type: ANIME, id_in: $ids) {
      id
      nextAiringEpisode { airingAt episode }
    }
  }
}
"""


DETAIL_QUERY = """
query AnimeDetails($id: Int!) {
  Media(id: $id, type: ANIME) {
    id
    title { romaji english native }
    episodes
    format
    status
    seasonYear
    description(asHtml: false)
    coverImage { medium large }
    siteUrl
    genres
    nextAiringEpisode { airingAt timeUntilAiring episode }
    trailer { id site thumbnail }
  }
}
"""



VIEWER_QUERY = """
query CurrentViewer {
  Viewer { id name siteUrl }
}
"""

USER_LIBRARY_QUERY = """
query CurrentUserAnimeList($userId: Int!) {
  MediaListCollection(userId: $userId, type: ANIME) {
    lists {
      entries {
        mediaId
        status
        progress
        score
        updatedAt
        media {
          id
          title { romaji english native }
          episodes
          format
          status
          coverImage { medium large }
          siteUrl
        }
      }
    }
  }
}
"""

SAVE_MEDIA_LIST_ENTRY_MUTATION = """
mutation SaveAniListEntry($mediaId: Int!, $status: MediaListStatus!, $progress: Int!) {
  SaveMediaListEntry(mediaId: $mediaId, status: $status, progress: $progress) {
    id
    mediaId
    status
    progress
    updatedAt
  }
}
"""

def _normalise_media(media: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, UI-friendly subset of an AniList media object."""
    title_data = media.get("title")
    if not isinstance(title_data, dict):
        title_data = {}
    cover = media.get("coverImage")
    if not isinstance(cover, dict):
        cover = {}
    airing = media.get("nextAiringEpisode")
    if not isinstance(airing, dict):
        airing = {}
    trailer = media.get("trailer")
    if not isinstance(trailer, dict):
        trailer = {}
    trailer_id = trailer.get("id")
    trailer_site = trailer.get("site")
    trailer_url = None
    if isinstance(trailer_id, str) and isinstance(trailer_site, str):
        site = trailer_site.casefold()
        if site == "youtube" and re.fullmatch(r"[A-Za-z0-9_-]{11}", trailer_id):
            trailer_url = f"https://www.youtube.com/watch?v={trailer_id}"
        elif site == "dailymotion" and re.fullmatch(r"[A-Za-z0-9]+", trailer_id):
            trailer_url = f"https://www.dailymotion.com/video/{trailer_id}"
        elif site == "vimeo" and re.fullmatch(r"[0-9]+", trailer_id):
            trailer_url = f"https://vimeo.com/{trailer_id}"
    airing_at = airing.get("airingAt")
    time_until = airing.get("timeUntilAiring")
    next_episode = airing.get("episode")
    if isinstance(airing_at, bool) or not isinstance(airing_at, int) or airing_at <= 0:
        airing_at = None
    if isinstance(time_until, bool) or not isinstance(time_until, int) or time_until < 0:
        time_until = None
    if isinstance(next_episode, bool) or not isinstance(next_episode, int) or next_episode <= 0:
        next_episode = None
    title = title_data.get("english") or title_data.get("romaji") or title_data.get("native")
    if not title:
        title = "Untitled anime"
    return {
        "id": media.get("id"),
        "title": title,
        "title_romaji": title_data.get("romaji"),
        "title_english": title_data.get("english"),
        "title_native": title_data.get("native"),
        "episodes": media.get("episodes"),
        "format": media.get("format"),
        "status": media.get("status"),
        "season": media.get("season"),
        "season_year": media.get("seasonYear"),
        "popularity": media.get("popularity"),
        "average_score": media.get("averageScore"),
        "start_date": dict(media["startDate"]) if isinstance(media.get("startDate"), dict) else {},
        "description": media.get("description") or "",
        "cover_image": cover.get("large") or cover.get("medium"),
        "site_url": media.get("siteUrl"),
        "trailer_url": trailer_url,
        "trailer_thumbnail": trailer.get("thumbnail") if trailer_url else None,
        "genres": (
            list(media["genres"])
            if isinstance(media.get("genres"), list)
            else []
        ),
        "next_episode": next_episode,
        "next_airing_at": airing_at,
        "time_until_airing": time_until,
    }


class AniListClient:
    """Synchronous public-catalogue client with bounded request timeouts."""

    def __init__(
        self,
        timeout: int | None = None,
        *,
        cache: MetadataCache | None = None,
        access_token: str | None = None,
    ):
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0
        ):
            raise ValueError("Timeout must be greater than zero")
        if access_token is not None and (
            not isinstance(access_token, str) or not access_token.strip()
            or any(character in access_token for character in ("\x00", "\r", "\n"))
        ):
            raise ValueError("Access token must be non-empty text without line breaks.")
        self.timeout = timeout
        self.cache = cache if cache is not None else MetadataCache()
        self.access_token = access_token.strip() if access_token else None

    def _request(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Aniyori/0.1.0 (Linux desktop anime tracker)",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        request = Request(
            ANILIST_GRAPHQL_URL,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with open_request(
                request, timeout=self.timeout, retry_safe=True, urlopen_func=urlopen
            ) as response:
                raw_payload = response.read(MAX_ANILIST_RESPONSE_BYTES + 1)
            if len(raw_payload) > MAX_ANILIST_RESPONSE_BYTES:
                raise AniListError("AniList response exceeds the maximum allowed size.")
            payload = json.loads(raw_payload.decode("utf-8"))
        except HTTPError as error:
            raise AniListError(f"AniList returned HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise AniListError(f"Could not reach AniList: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AniListError("AniList returned invalid JSON") from error

        if not isinstance(payload, dict):
            raise AniListError("AniList response must be a JSON object")
        errors = payload.get("errors")
        if errors is not None:
            if not isinstance(errors, list):
                raise AniListError("AniList returned malformed GraphQL errors")
            messages = []
            for item in errors:
                if not isinstance(item, dict):
                    raise AniListError("AniList returned malformed GraphQL errors")
                message = item.get("message")
                if not isinstance(message, str) or not message.strip():
                    raise AniListError("AniList returned malformed GraphQL errors")
                messages.append(message.strip())
            if messages:
                raise AniListError("; ".join(messages))
        if not isinstance(payload.get("data"), dict):
            raise AniListError("AniList response did not contain data")
        return payload["data"]

    def clear_cache(self) -> None:
        """Clear cached catalogue metadata; cached cover images are unaffected."""
        self.cache.clear()

    def search_anime(
        self, search: str, per_page: int = 10, *, refresh: bool = False
    ) -> list[dict[str, Any]]:
        """Search the public catalogue, using cached results when available.

        Expired results are retained as an offline fallback. Set refresh=True
        to bypass a fresh cache entry and attempt a network refresh.
        """
        search = search.strip()
        if not search:
            return []
        if not 1 <= per_page <= 25:
            raise ValueError("per_page must be between 1 and 25")
        cache_key = json.dumps(
            {"search": search.casefold(), "per_page": per_page}, sort_keys=True
        )
        cached = self.cache.get("search", cache_key)
        if cached is not None and cached[1] and not refresh:
            return cached[0]
        try:
            data = self._request(SEARCH_QUERY, {"search": search, "perPage": per_page})
            page = data.get("Page")
            if not isinstance(page, dict):
                raise AniListError("AniList search response did not contain a page")
            media = page.get("media")
            if not isinstance(media, list) or not all(
                isinstance(item, dict) for item in media
            ):
                raise AniListError("AniList search response contained invalid media results")
            results = [_normalise_media(item) for item in media]
        except AniListError:
            if cached is not None:
                return cached[0]
            raise
        self.cache.set("search", cache_key, results)
        return results


    def search_season(self, season: str, year: int, per_page: int = 50, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return popular anime for one AniList season, with offline cache fallback."""
        season = season.upper() if isinstance(season, str) else ""
        if season not in {"WINTER", "SPRING", "SUMMER", "FALL"}:
            raise ValueError("season must be WINTER, SPRING, SUMMER, or FALL")
        if isinstance(year, bool) or not isinstance(year, int) or not 1970 <= year <= 2100:
            raise ValueError("year must be between 1970 and 2100")
        if isinstance(per_page, bool) or not isinstance(per_page, int) or not 1 <= per_page <= 50:
            raise ValueError("per_page must be between 1 and 50")
        cache_key = f"{season}:{year}:{per_page}"
        cached = self.cache.get("season", cache_key)
        if cached is not None and cached[1] and not refresh:
            return cached[0]
        try:
            data = self._request(SEASON_QUERY, {"season": season, "seasonYear": year, "perPage": per_page})
            page = data.get("Page")
            if not isinstance(page, dict):
                raise AniListError("AniList season response did not contain a page")
            media = page.get("media")
            if not isinstance(media, list) or not all(isinstance(item, dict) for item in media):
                raise AniListError("AniList season response contained invalid media results")
            results = [_normalise_media(item) for item in media]
        except AniListError:
            if cached is not None:
                return cached[0]
            raise
        self.cache.set("season", cache_key, results)
        return results

    def get_trending_anime(self, per_page: int = 50, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return currently trending anime from the public catalogue."""
        if isinstance(per_page, bool) or not isinstance(per_page, int) or not 1 <= per_page <= 50:
            raise ValueError("per_page must be between 1 and 50")
        cache_key = str(per_page)
        cached = self.cache.get("trending", cache_key)
        if cached is not None and cached[1] and not refresh:
            return cached[0]
        try:
            data = self._request(TRENDING_QUERY, {"perPage": per_page})
            page = data.get("Page")
            if not isinstance(page, dict):
                raise AniListError("AniList trending response did not contain a page")
            media = page.get("media")
            if not isinstance(media, list) or not all(isinstance(item, dict) for item in media):
                raise AniListError("AniList trending response contained invalid media results")
            results = [_normalise_media(item) for item in media]
        except AniListError:
            if cached is not None:
                return cached[0]
            raise
        self.cache.set("trending", cache_key, results)
        return results

    def get_airing_schedules(self, media_ids) -> dict[int, tuple[int, int] | None]:
        """Fetch next-airing metadata in batches, with cached fallback when offline."""
        try:
            ids = list(media_ids)
        except TypeError:
            raise ValueError("media_ids must be an iterable of positive integers") from None
        if any(
            isinstance(media_id, bool)
            or not isinstance(media_id, int)
            or media_id <= 0
            for media_id in ids
        ):
            raise ValueError("media_ids must contain only positive integers")
        ids = tuple(dict.fromkeys(ids))
        if not ids:
            return {}

        schedules = {}
        for offset in range(0, len(ids), 50):
            batch = ids[offset:offset + 50]
            try:
                data = self._request(AIRING_QUERY, {"ids": list(batch)})
            except AniListError:
                for media_id in batch:
                    cached = self.cache.get("details", str(media_id))
                    value = cached[0] if cached is not None else None
                    episode = value.get("next_episode") if isinstance(value, dict) else None
                    airing_at = value.get("next_airing_at") if isinstance(value, dict) else None
                    schedules[media_id] = (
                        (episode, airing_at)
                        if isinstance(episode, int) and not isinstance(episode, bool)
                        and isinstance(airing_at, int) and not isinstance(airing_at, bool)
                        else None
                    )
                continue

            page = data.get("Page")
            media = page.get("media") if isinstance(page, dict) else None
            if not isinstance(media, list) or not all(
                isinstance(item, dict) for item in media
            ):
                raise AniListError("AniList airing response contained invalid media results")
            seen = set()
            for item in media:
                media_id = item.get("id")
                if (
                    isinstance(media_id, bool)
                    or not isinstance(media_id, int)
                    or media_id not in batch
                    or media_id in seen
                ):
                    raise AniListError("AniList airing response contained an invalid media ID")
                seen.add(media_id)
                normalized = _normalise_media(item)
                episode = normalized.get("next_episode")
                airing_at = normalized.get("next_airing_at")
                schedules[media_id] = (
                    (episode, airing_at)
                    if episode is not None and airing_at is not None
                    else None
                )
            for media_id in batch:
                schedules.setdefault(media_id, None)
        return schedules

    def get_month_airing_schedules(
        self,
        media_ids,
        start_at: int,
        end_at: int,
        *,
        chunk_size: int = 100,
        per_page: int = 50,
        max_pages: int = 3,
    ) -> list[dict[str, int]]:
        """Return every scheduled episode for the given anime in a time range.

        AniList rejects very large mediaId_in lists, so IDs are chunked and
        each chunk is paginated. Results are cached by range and library size.
        """
        if isinstance(start_at, bool) or not isinstance(start_at, int):
            raise ValueError("start_at must be an integer timestamp")
        if isinstance(end_at, bool) or not isinstance(end_at, int) or end_at <= start_at:
            raise ValueError("end_at must be a timestamp after start_at")
        if (
            isinstance(chunk_size, bool) or not isinstance(chunk_size, int)
            or not 1 <= chunk_size <= 100
            or isinstance(per_page, bool) or not isinstance(per_page, int)
            or not 1 <= per_page <= 50
            or isinstance(max_pages, bool) or not isinstance(max_pages, int)
            or not 1 <= max_pages <= 10
        ):
            raise ValueError("invalid chunk size, page size, or page limit")
        try:
            ids = list(media_ids)
        except TypeError:
            raise ValueError("media_ids must be an iterable of positive integers") from None
        if any(
            isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0
            for media_id in ids
        ):
            raise ValueError("media_ids must contain only positive integers")
        ids = tuple(dict.fromkeys(ids))
        if not ids:
            return []

        cache_key = f"{start_at}:{end_at}:{len(ids)}"
        cached = self.cache.get("airing-month", cache_key)
        if cached is not None and cached[1]:
            return cached[0]

        results = []
        for offset in range(0, len(ids), chunk_size):
            batch = list(ids[offset:offset + chunk_size])
            for page_number in range(1, max_pages + 1):
                data = self._request(MONTH_AIRING_QUERY, {
                    "ids": batch,
                    "from": start_at,
                    "to": end_at,
                    "page": page_number,
                    "perPage": per_page,
                })
                page = data.get("Page")
                entries = page.get("airingSchedules") if isinstance(page, dict) else None
                if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
                    raise AniListError("AniList airing schedule response contained invalid results")
                for item in entries:
                    media_id = item.get("mediaId")
                    episode = item.get("episode")
                    airing_at = item.get("airingAt")
                    if (
                        isinstance(media_id, bool) or not isinstance(media_id, int)
                        or media_id not in batch
                        or isinstance(episode, bool) or not isinstance(episode, int) or episode <= 0
                        or isinstance(airing_at, bool) or not isinstance(airing_at, int)
                    ):
                        raise AniListError("AniList airing schedule response contained invalid values")
                    results.append({"media_id": media_id, "episode": episode, "airing_at": airing_at})
                if len(entries) < per_page:
                    break
        self.cache.set("airing-month", cache_key, results)
        return results

    def get_anime(self, media_id: int, *, refresh: bool = False) -> dict[str, Any]:
        """Fetch one catalogue entry, falling back to cached metadata offline."""
        if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0:
            raise ValueError("media_id must be a positive integer")
        cache_key = str(media_id)
        cached = self.cache.get("details", cache_key)
        if cached is not None and cached[1] and not refresh:
            return cached[0]
        try:
            data = self._request(DETAIL_QUERY, {"id": media_id})
            media = data.get("Media")
            if not isinstance(media, dict):
                raise AniListError(f"AniList anime {media_id} was not found")
            result = _normalise_media(media)
        except AniListError:
            if cached is not None:
                return cached[0]
            raise
        self.cache.set("details", cache_key, result)
        return result

    def get_viewer(self) -> dict[str, Any]:
        """Return the authenticated AniList account identity."""
        if not self.access_token:
            raise AniListError("Connect an AniList account before requesting account data.")
        data = self._request(VIEWER_QUERY, {})
        viewer = data.get("Viewer")
        if (
            not isinstance(viewer, dict)
            or isinstance(viewer.get("id"), bool)
            or not isinstance(viewer.get("id"), int)
            or viewer["id"] <= 0
            or not isinstance(viewer.get("name"), str)
            or not viewer["name"].strip()
        ):
            raise AniListError("AniList did not return a valid authenticated account.")
        return {
            "id": viewer["id"],
            "name": viewer["name"].strip(),
            "site_url": viewer.get("siteUrl"),
        }

    def get_user_library(self, user_id: int) -> list[dict[str, Any]]:
        """Fetch all anime list entries for one authenticated AniList user."""
        if not self.access_token:
            raise AniListError("Connect an AniList account before requesting account data.")
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer.")
        data = self._request(USER_LIBRARY_QUERY, {"userId": user_id})
        collection = data.get("MediaListCollection")
        if collection is None:
            return []
        if not isinstance(collection, dict) or not isinstance(collection.get("lists"), list):
            raise AniListError("AniList returned an invalid user library.")
        results_by_id = {}
        for media_list in collection["lists"]:
            if not isinstance(media_list, dict) or not isinstance(media_list.get("entries"), list):
                raise AniListError("AniList returned an invalid user list.")
            for entry in media_list["entries"]:
                if not isinstance(entry, dict) or not isinstance(entry.get("media"), dict):
                    raise AniListError("AniList returned an invalid list entry.")
                media_id = entry.get("mediaId")
                status = entry.get("status")
                progress = entry.get("progress")
                updated_at = entry.get("updatedAt")
                if (
                    isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0
                    or not isinstance(status, str)
                    or status not in {"CURRENT", "PLANNING", "COMPLETED", "PAUSED", "DROPPED", "REPEATING"}
                    or isinstance(progress, bool) or not isinstance(progress, int) or not 0 <= progress <= MAX_EPISODE_COUNT
                    or isinstance(updated_at, bool) or not isinstance(updated_at, int) or updated_at < 0
                ):
                    raise AniListError("AniList returned an invalid or duplicate list entry.")
                media = _normalise_media(entry["media"])
                if media.get("id") != media_id:
                    raise AniListError("AniList list entry media IDs did not match.")
                normalized = {
                    "media_id": media_id,
                    "status": status,
                    "progress": progress,
                    "score": entry.get("score"),
                    "updated_at": updated_at,
                    "media": media,
                }
                previous = results_by_id.get(media_id)
                if previous is not None:
                    if previous != normalized:
                        raise AniListError("AniList returned conflicting duplicate list entries.")
                    continue
                results_by_id[media_id] = normalized
        return list(results_by_id.values())

    def save_media_list_entry(self, media_id: int, status: str, progress: int) -> dict[str, Any]:
        """Create or update one authenticated AniList list entry."""
        if not self.access_token:
            raise AniListError("Connect an AniList account before updating AniList.")
        if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0:
            raise ValueError("media_id must be a positive integer.")
        if not isinstance(status, str) or status not in {
            "CURRENT", "PLANNING", "COMPLETED", "PAUSED", "DROPPED", "REPEATING"
        }:
            raise ValueError("Unsupported AniList list status.")
        if isinstance(progress, bool) or not isinstance(progress, int) or not 0 <= progress <= MAX_EPISODE_COUNT:
            raise ValueError(f"progress must be between 0 and {MAX_EPISODE_COUNT:,}.")
        data = self._request(
            SAVE_MEDIA_LIST_ENTRY_MUTATION,
            {"mediaId": media_id, "status": status, "progress": progress},
        )
        result = data.get("SaveMediaListEntry")
        if (
            not isinstance(result, dict)
            or result.get("mediaId") != media_id
            or result.get("status") != status
            or result.get("progress") != progress
        ):
            raise AniListError("AniList did not confirm the requested list update.")
        return result

