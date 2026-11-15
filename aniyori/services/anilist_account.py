"""Desktop OAuth helpers and non-secret AniList account settings."""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from ..backup import default_config_dir


AUTH_PIN_REDIRECT_URI = "https://anilist.co/api/v2/oauth/pin"
AUTHORIZATION_URL = "https://anilist.co/api/v2/oauth/authorize"
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
