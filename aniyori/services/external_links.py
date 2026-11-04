"""Validated external links for library anime entries."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from string import Formatter
from urllib.parse import quote_plus, urlsplit

FORMAT = "aniyori-external-links"
VERSION = 1
FIELDS = frozenset({"title", "provider", "provider_id"})
_LABEL = re.compile(r"^[^\x00-\x1f\x7f]{1,48}$")


class ExternalLinkError(ValueError):
    """Raised when an external-link template or store is invalid."""


def validate_link_template(label: str, template: str) -> None:
    if not isinstance(label, str) or not _LABEL.fullmatch(label.strip()):
        raise ExternalLinkError("Link name must be 1–48 printable characters.")
    if not isinstance(template, str) or not template.strip():
        raise ExternalLinkError("Link URL template is required.")
    try:
        for _literal, field, spec, conversion in Formatter().parse(template):
            if field is None:
                continue
            if field not in FIELDS or any(char in field for char in ".["):
                raise ExternalLinkError(f"Unsupported link template field: {field}")
            if spec or conversion:
                raise ExternalLinkError("Link template formatting is not supported.")
    except ValueError as error:
        if isinstance(error, ExternalLinkError):
            raise
        raise ExternalLinkError(f"Malformed link template: {error}") from error
    sample = template.format_map({field: "example" for field in FIELDS})
    _validate_url(sample)


def _validate_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not any(ord(char) < 32 for char in url)
        )
        if valid:
            parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ExternalLinkError("External links must use a valid HTTP or HTTPS URL without embedded credentials.")


def render_link_template(template: str, values: dict[str, str]) -> str:
    validate_link_template("Custom link", template)
    rendered = template.format_map(
        {field: quote_plus(values.get(field, ""), safe="") for field in FIELDS}
    )
    _validate_url(rendered)
    return rendered


def links_for_entry(entry, custom_templates=()) -> tuple[tuple[str, str], ...]:
    """Return only links supported by the entry's available identifiers."""
    links = []
    provider = entry.provider or ""
    provider_id = entry.provider_id or ""
    if provider.casefold() == "anilist" and provider_id.isdigit():
        links.append(("AniList", f"https://anilist.co/anime/{provider_id}"))
    query = quote_plus(entry.title)
    links.extend((
        ("MyAnimeList search", f"https://myanimelist.net/anime.php?q={query}"),
        ("Kitsu search", f"https://kitsu.io/anime?filter[text]={query}"),
    ))
    values = {"title": entry.title, "provider": provider, "provider_id": provider_id}
    for item in custom_templates:
        try:
            label, template = item["name"], item["url"]
            required = {
                field for _literal, field, _spec, _conversion
                in Formatter().parse(template) if field is not None
            }
            if any(not values.get(field) for field in required):
                continue
            links.append((label, render_link_template(template, values)))
        except (KeyError, TypeError, ValueError, ExternalLinkError):
            continue
    return tuple(links)


def default_external_links_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "external-links.json"


class ExternalLinkStore:
    """Atomically persist a small list of validated custom link templates."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_external_links_path()

    def list_templates(self) -> tuple[dict[str, str], ...]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExternalLinkError("Saved external links are invalid.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != FORMAT
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("version"), int)
            or payload.get("version") != VERSION
            or not isinstance(payload.get("links"), list)
        ):
            raise ExternalLinkError("Saved external links have an unsupported format.")
        result = []
        seen = set()
        for item in payload["links"]:
            if not isinstance(item, dict):
                raise ExternalLinkError("A saved external link is malformed.")
            name, url = item.get("name"), item.get("url")
            validate_link_template(name, url)
            key = name.strip().casefold()
            if key in seen:
                raise ExternalLinkError("Saved external link names must be unique.")
            seen.add(key)
            result.append({"name": name.strip(), "url": url})
        return tuple(result)

    def save_templates(self, templates) -> None:
        prepared = []
        seen = set()
        for item in templates:
            if not isinstance(item, dict):
                raise ExternalLinkError("A custom link must contain a name and URL template.")
            name, url = item.get("name"), item.get("url")
            validate_link_template(name, url)
            key = name.strip().casefold()
            if key in seen:
                raise ExternalLinkError("Custom link names must be unique.")
            seen.add(key)
            prepared.append({"name": name.strip(), "url": url})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"format": FORMAT, "version": VERSION, "links": prepared},
            ensure_ascii=False, indent=2,
        ) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".external-links-", delete=False,
            ) as temporary:
                os.chmod(temporary.name, 0o600)
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
