"""Small, dependency-free AniList GraphQL client.

This module deliberately does not handle OAuth or user-list mutations yet.
Catalogue search is public; authenticated sync will be added separately.
"""

from __future__ import annotations

import json
from typing import Any

from .metadata_cache import MetadataCache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
DEFAULT_TIMEOUT = 15


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
  }
}
"""


def _normalise_media(media: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, UI-friendly subset of an AniList media object."""
    title_data = media.get("title") or {}
    cover = media.get("coverImage") or {}
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
        "season_year": media.get("seasonYear"),
        "description": media.get("description") or "",
        "cover_image": cover.get("large") or cover.get("medium"),
        "site_url": media.get("siteUrl"),
        "genres": list(media.get("genres") or []),
    }


class AniListClient:
    """Synchronous public-catalogue client with bounded request timeouts."""

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        *,
        cache: MetadataCache | None = None,
    ):
        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero")
        self.timeout = timeout
        self.cache = cache if cache is not None else MetadataCache()

    def _request(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        request = Request(
            ANILIST_GRAPHQL_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Aniyori/0.1.0 (Linux desktop anime tracker)",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise AniListError(f"AniList returned HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise AniListError(f"Could not reach AniList: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AniListError("AniList returned invalid JSON") from error

        if payload.get("errors"):
            messages = [
                item.get("message", "Unknown GraphQL error")
                for item in payload["errors"]
            ]
            raise AniListError("; ".join(messages))
        if not isinstance(payload.get("data"), dict):
            raise AniListError("AniList response did not contain data")
        return payload["data"]

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
            page = data.get("Page") or {}
            media = page.get("media") or []
            results = [_normalise_media(item) for item in media]
        except AniListError:
            if cached is not None:
                return cached[0]
            raise
        self.cache.set("search", cache_key, results)
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
