"""Desktop OAuth helpers and non-secret AniList account settings."""

from __future__ import annotations

import base64
from dataclasses import replace
import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from ..models import MAX_EPISODE_COUNT, AnimeEntry, WatchStatus
from ..backup import default_config_dir


AUTH_PIN_REDIRECT_URI = "https://anilist.co/api/v2/oauth/pin"
AUTHORIZATION_URL = "https://anilist.co/api/v2/oauth/authorize"
DEFAULT_CLIENT_ID = "57061"
_ACCOUNT_FORMAT = "aniyori-anilist-account"
_ACCOUNT_VERSION = 1
_CLIENT_ID = re.compile(r"^[0-9]{1,20}$")


class AniListAccountError(ValueError):
    """Raised when AniList account settings or OAuth input is invalid."""


def validate_client_id(client_id: str) -> str:
    """Return a normalized public AniList client ID."""
    if not isinstance(client_id, str):
        raise AniListAccountError("AniList Client ID must be text.")
    client_id = client_id.strip()
    if not _CLIENT_ID.fullmatch(client_id) or int(client_id) <= 0:
        raise AniListAccountError("Enter the numeric Client ID from your AniList application.")
    return client_id


def build_authorization_url(client_id: str) -> str:
    """Build the implicit-grant URL for the registered Auth Pin redirect."""
    client_id = validate_client_id(client_id)
    return f"{AUTHORIZATION_URL}?{urlencode({'client_id': client_id, 'response_type': 'token'})}"


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise AniListAccountError("The pasted value is not a valid AniList access token.")
    try:
        payload_part = parts[1]
        payload_part += "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_part.encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise AniListAccountError("The AniList access token could not be read.") from error
    if not isinstance(payload, dict):
        raise AniListAccountError("The AniList access token has an invalid payload.")
    return payload


def parse_access_token(value: str, *, now: float | None = None) -> str:
    """Extract and locally check an AniList JWT pasted from the Auth Pin page.

    The JWT signature is intentionally not verified here; AniList verifies it
    when Aniyori makes the authenticated Viewer request before storing it.
    """
    if not isinstance(value, str) or not value.strip():
        raise AniListAccountError("Paste the access token shown by AniList.")
    value = value.strip()
    token = value
    if "://" in value:
        parsed = urlparse(value)
        candidates = parse_qs(parsed.fragment).get("access_token") or parse_qs(parsed.query).get("access_token")
        if not candidates:
            raise AniListAccountError("The pasted URL does not contain an access token.")
        token = candidates[0].strip()
    payload = _decode_jwt_payload(token)
    expiry = payload.get("exp")
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
        raise AniListAccountError("The AniList access token has no valid expiry.")
    current_time = time.time() if now is None else now
    if expiry <= current_time:
        raise AniListAccountError("This AniList access token has expired. Authorize again.")
    return token


_STATUS_MAP = {
    "CURRENT": WatchStatus.WATCHING,
    "PLANNING": WatchStatus.PLANNING,
    "COMPLETED": WatchStatus.COMPLETED,
    "PAUSED": WatchStatus.PAUSED,
    "DROPPED": WatchStatus.DROPPED,
    "REPEATING": WatchStatus.WATCHING,
}


def _normalise_score(value, *, maximum: float) -> float | None:
    """Convert AniList scores to the local 0-10 scale, or omit invalid values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not 0 <= value <= maximum:
        return None
    return round(float(value) * 10 / maximum, 1)


def import_entry_from_anilist(remote: dict) -> AnimeEntry:
    """Convert one validated AniList list entry without losing watch progress."""
    if not isinstance(remote, dict) or not isinstance(remote.get("media"), dict):
        raise AniListAccountError("AniList returned an invalid library entry.")
    media = remote["media"]
    media_id = remote.get("media_id")
    status = remote.get("status")
    progress = remote.get("progress")
    title = media.get("title")
    if (
        isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0
        or not isinstance(status, str) or status not in _STATUS_MAP
        or isinstance(progress, bool) or not isinstance(progress, int)
        or not 0 <= progress <= MAX_EPISODE_COUNT
        or not isinstance(title, str) or not title.strip()
        or isinstance(media.get("id"), bool)
        or media.get("id") != media_id
    ):
        raise AniListAccountError("AniList returned invalid media or progress values.")
    total = media.get("episodes")
    if (
        isinstance(total, bool) or not isinstance(total, int)
        or total <= 0 or total > MAX_EPISODE_COUNT
    ):
        total = None
    if total is not None and progress > total:
        total = None
    cover = media.get("cover_image")
    if cover is not None and not isinstance(cover, str):
        cover = None
    return AnimeEntry(
        title=title.strip(),
        episodes_total=total,
        episodes_watched=progress,
        status=_STATUS_MAP[status],
        provider="anilist",
        provider_id=str(media_id),
        cover_image=cover,
        my_score=_normalise_score(remote.get("score"), maximum=10),
        global_score=_normalise_score(
            media.get("average_score", media.get("averageScore")), maximum=100
        ),
    )


_REMOTE_STATUS_BY_LOCAL = {
    WatchStatus.PLANNING: "PLANNING",
    WatchStatus.WATCHING: "CURRENT",
    WatchStatus.COMPLETED: "COMPLETED",
    WatchStatus.PAUSED: "PAUSED",
    WatchStatus.DROPPED: "DROPPED",
}


def anilist_status_for_local(entry: AnimeEntry) -> str:
    """Map a local watch status to the closest supported AniList status."""
    if not isinstance(entry, AnimeEntry):
        raise AniListAccountError("A valid local anime entry is required.")
    return _REMOTE_STATUS_BY_LOCAL[entry.status]


def build_sync_plan(local_entries, remote_entries: list[dict]) -> dict:
    """Classify sync differences without modifying either library.

    Without a persisted last-synced snapshot, every differing status/progress
    pair is deliberately surfaced as a conflict rather than guessing which
    side changed most recently.
    """
    if not isinstance(remote_entries, list):
        raise AniListAccountError("AniList library data must be a list.")
    local_by_id = {}
    for entry in local_entries:
        if not isinstance(entry, AnimeEntry):
            raise AniListAccountError("Local library contains an invalid entry.")
        if entry.provider == "anilist" and entry.provider_id:
            if not entry.provider_id.isdecimal() or int(entry.provider_id) <= 0:
                raise AniListAccountError("Local library contains an invalid AniList ID.")
            if entry.provider_id in local_by_id:
                raise AniListAccountError("Local library contains duplicate AniList IDs.")
            local_by_id[entry.provider_id] = entry

    remote_by_id = {}
    for remote in remote_entries:
        if not isinstance(remote, dict):
            raise AniListAccountError("AniList library contains an invalid entry.")
        media_id = remote.get("media_id")
        if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0:
            raise AniListAccountError("AniList library contains an invalid media ID.")
        key = str(media_id)
        if key in remote_by_id:
            raise AniListAccountError("AniList library contains duplicate media IDs.")
        if not isinstance(remote.get("status"), str) or remote["status"] not in _STATUS_MAP:
            raise AniListAccountError("AniList library contains an unsupported status.")
        progress = remote.get("progress")
        if isinstance(progress, bool) or not isinstance(progress, int) or not 0 <= progress <= MAX_EPISODE_COUNT:
            raise AniListAccountError("AniList library contains invalid progress.")
        remote_by_id[key] = remote

    imports = []
    conflicts = []
    unchanged = 0
    for media_id, remote in remote_by_id.items():
        local = local_by_id.get(media_id)
        if local is None:
            imports.append(remote)
            continue
        if (
            local.status != _STATUS_MAP[remote["status"]]
            or local.episodes_watched != remote["progress"]
        ):
            conflicts.append({"local": local, "remote": remote})
        else:
            unchanged += 1

    local_only = [
        entry for media_id, entry in local_by_id.items()
        if media_id not in remote_by_id
    ]
    return {
        "imports": tuple(imports),
        "conflicts": tuple(conflicts),
        "local_only": tuple(local_only),
        "unchanged": unchanged,
    }


def local_entry_sync_payload(entry: AnimeEntry) -> dict:
    """Build a validated AniList mutation payload from one linked local entry."""
    if (
        not isinstance(entry, AnimeEntry)
        or entry.provider != "anilist"
        or not isinstance(entry.provider_id, str)
        or not entry.provider_id.isdecimal()
        or int(entry.provider_id) <= 0
    ):
        raise AniListAccountError("A valid AniList-linked local entry is required.")
    return {
        "media_id": int(entry.provider_id),
        "status": anilist_status_for_local(entry),
        "progress": entry.episodes_watched,
    }


def local_entry_from_remote(remote: dict, existing: AnimeEntry) -> AnimeEntry:
    """Apply a remote snapshot to one local row while preserving its database ID."""
    if not isinstance(existing, AnimeEntry) or existing.storage_id is None:
        raise AniListAccountError("A saved local entry is required for a remote update.")
    imported = import_entry_from_anilist(remote)
    if existing.provider != "anilist" or existing.provider_id != imported.provider_id:
        raise AniListAccountError("The remote entry does not match the selected local entry.")
    return replace(imported, storage_id=existing.storage_id)


class AniListAccountSettingsStore:
    """Persist the public Client ID and account label, never the access token."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_config_dir() / "anilist-account.json"

    def load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"client_id": "", "viewer_id": None, "viewer_name": None}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AniListAccountError("AniList account settings could not be read.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != _ACCOUNT_FORMAT
            or isinstance(payload.get("version"), bool)
            or payload.get("version") != _ACCOUNT_VERSION
            or not isinstance(payload.get("client_id"), str)
            or payload.get("viewer_id") is not None
            and (isinstance(payload.get("viewer_id"), bool) or not isinstance(payload.get("viewer_id"), int) or payload["viewer_id"] <= 0)
            or payload.get("viewer_name") is not None
            and not isinstance(payload.get("viewer_name"), str)
        ):
            raise AniListAccountError("AniList account settings have an unsupported format.")
        client_id = payload["client_id"]
        if client_id:
            client_id = validate_client_id(client_id)
        return {
            "client_id": client_id,
            "viewer_id": payload.get("viewer_id"),
            "viewer_name": payload.get("viewer_name"),
        }

    def save(self, *, client_id: str, viewer_id: int | None = None, viewer_name: str | None = None) -> None:
        client_id = validate_client_id(client_id)
        if viewer_id is not None and (
            isinstance(viewer_id, bool) or not isinstance(viewer_id, int) or viewer_id <= 0
        ):
            raise AniListAccountError("AniList account ID must be a positive integer.")
        if viewer_name is not None and (not isinstance(viewer_name, str) or not viewer_name.strip()):
            raise AniListAccountError("AniList account name must be non-empty text.")
        payload = {
            "format": _ACCOUNT_FORMAT,
            "version": _ACCOUNT_VERSION,
            "client_id": client_id,
            "viewer_id": viewer_id,
            "viewer_name": viewer_name.strip() if viewer_name else None,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(prefix=".anilist-account-", dir=self.path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise
