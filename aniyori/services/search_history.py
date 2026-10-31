"""Persistent recent-query history and reusable saved searches."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


SEARCH_STORE_FORMAT = "aniyori-search-history"
SEARCH_STORE_VERSION = 1
SEARCH_DOMAINS = frozenset({"anilist", "torrent"})
MAX_HISTORY_ITEMS = 20


class SearchHistoryError(ValueError):
    """Raised when saved search data is invalid."""


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SearchHistoryError(f"Duplicate saved-search key: {key}")
        result[key] = value
    return result


def default_search_history_path() -> Path:
    """Return the XDG configuration path without creating it."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "search-history.json"


class SearchHistoryStore:
    """Store recent queries and named saved searches for supported search views."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_search_history_path()

    @staticmethod
    def _validate_domain(domain: str) -> str:
        if not isinstance(domain, str) or domain not in SEARCH_DOMAINS:
            raise SearchHistoryError(
                "Search domain must be 'anilist' or 'torrent'."
            )
        return domain

    def _load(self) -> dict[str, Any]:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {
                "history": {domain: [] for domain in SEARCH_DOMAINS},
                "saved": {domain: [] for domain in SEARCH_DOMAINS},
            }
        try:
            payload = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SearchHistoryError("Saved search history is invalid JSON.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != SEARCH_STORE_FORMAT
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("version"), int)
            or payload.get("version") != SEARCH_STORE_VERSION
            or not isinstance(payload.get("history"), dict)
            or not isinstance(payload.get("saved"), dict)
        ):
            raise SearchHistoryError("Saved search history has an unsupported format.")
        normalized = {
            "history": {domain: [] for domain in SEARCH_DOMAINS},
            "saved": {domain: [] for domain in SEARCH_DOMAINS},
        }
        for domain in SEARCH_DOMAINS:
            history = payload["history"].get(domain, [])
            saved = payload["saved"].get(domain, [])
            if not isinstance(history, list) or not all(
                isinstance(query, str) and query.strip() for query in history
            ):
                raise SearchHistoryError(f"Recent {domain} searches are malformed.")
            if not isinstance(saved, list):
                raise SearchHistoryError(f"Saved {domain} searches are malformed.")
            normalized["history"][domain] = list(
                dict.fromkeys(query.strip() for query in history)
            )[:MAX_HISTORY_ITEMS]
            seen_names = set()
            for item in saved:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("name"), str)
                    or not item["name"].strip()
                    or not isinstance(item.get("query"), str)
                    or not item["query"].strip()
                ):
                    raise SearchHistoryError(f"Saved {domain} searches are malformed.")
                name = item["name"].strip()
                key = name.casefold()
                if key in seen_names:
                    continue
                seen_names.add(key)
                normalized["saved"][domain].append(
                    {"name": name, "query": item["query"].strip()}
                )
        return normalized

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {
                "format": SEARCH_STORE_FORMAT,
                "version": SEARCH_STORE_VERSION,
                **payload,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".search-history-", delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def list_history(self, domain: str) -> tuple[str, ...]:
        domain = self._validate_domain(domain)
        return tuple(self._load()["history"][domain])

    def list_saved_searches(self, domain: str) -> tuple[dict[str, str], ...]:
        domain = self._validate_domain(domain)
        return tuple(dict(item) for item in self._load()["saved"][domain])

    def record_query(self, domain: str, query: str) -> bool:
        domain = self._validate_domain(domain)
        if not isinstance(query, str) or not query.strip():
            return False
        query = query.strip()
        payload = self._load()
        history = payload["history"][domain]
        updated = [item for item in history if item.casefold() != query.casefold()]
        updated.insert(0, query)
        payload["history"][domain] = updated[:MAX_HISTORY_ITEMS]
        self._save(payload)
        return True

    def save_search(self, domain: str, name: str, query: str) -> bool:
        domain = self._validate_domain(domain)
        if not isinstance(name, str) or not name.strip():
            raise SearchHistoryError("A saved search name is required.")
        if not isinstance(query, str) or not query.strip():
            raise SearchHistoryError("A saved search query is required.")
        payload = self._load()
        saved = payload["saved"][domain]
        key = name.strip().casefold()
        if any(item["name"].casefold() == key for item in saved):
            return False
        saved.append({"name": name.strip(), "query": query.strip()})
        self._save(payload)
        return True

    def remove_history(self, domain: str, query: str) -> bool:
        domain = self._validate_domain(domain)
        payload = self._load()
        history = payload["history"][domain]
        updated = [item for item in history if item.casefold() != query.casefold()]
        if len(updated) == len(history):
            return False
        payload["history"][domain] = updated
        self._save(payload)
        return True

    def clear_history(self, domain: str) -> int:
        domain = self._validate_domain(domain)
        payload = self._load()
        count = len(payload["history"][domain])
        payload["history"][domain] = []
        if count:
            self._save(payload)
        return count

    def remove_saved_search(self, domain: str, name: str) -> bool:
        domain = self._validate_domain(domain)
        payload = self._load()
        saved = payload["saved"][domain]
        updated = [item for item in saved if item["name"].casefold() != name.casefold()]
        if len(updated) == len(saved):
            return False
        payload["saved"][domain] = updated
        self._save(payload)
        return True
