"""Validated user-configured HTTP webhook destinations and delivery."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


WEBHOOK_FORMAT = "aniyori-webhooks"
WEBHOOK_VERSION = 1
DEFAULT_TIMEOUT = 8
MAX_WEBHOOKS = 20
MAX_RESPONSE_BYTES = 4096
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}$")
_BLOCKED_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "proxy-authorization"}


class WebhookError(ValueError):
    """Raised when webhook configuration or payload is invalid."""


@dataclass(frozen=True, slots=True)
class Webhook:
    webhook_id: str
    name: str
    url: str
    enabled: bool = True
    headers: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class WebhookDelivery:
    webhook_id: str
    name: str
    success: bool
    message: str


def _validate_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise WebhookError("Webhook URL must be non-empty and at most 2,048 characters.")
    value = value.strip()
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        raise WebhookError("Webhook URL is malformed.") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise WebhookError("Webhook URL must be HTTP(S), without credentials or a fragment.")
    return value


def _validate_headers(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or len(value) > 16:
        raise WebhookError("Webhook headers must be an object containing at most 16 entries.")
    result = {}
    for name, content in value.items():
        if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
            raise WebhookError("Webhook header names must be valid HTTP tokens.")
        if name.casefold() in _BLOCKED_HEADERS or name.casefold() in {"content-type"}:
            raise WebhookError(f"The {name} header is managed by Aniyori or is not allowed.")
        if not isinstance(content, str) or not content or len(content) > 2048:
            raise WebhookError("Webhook header values must contain 1–2,048 characters.")
        if any(ord(char) < 32 or ord(char) == 127 for char in content):
            raise WebhookError("Webhook header values cannot contain control characters.")
        if any(existing.casefold() == name.casefold() for existing in result):
            raise WebhookError("Webhook header names must be unique, ignoring case.")
        result[name] = content
    return result


def _normalize(item: Webhook) -> Webhook:
    if not isinstance(item, Webhook):
        raise WebhookError("Webhook entries must be Webhook values.")
    if not isinstance(item.webhook_id, str) or not re.fullmatch(r"[a-f0-9]{32}", item.webhook_id):
        raise WebhookError("Webhook IDs must be 32 lowercase hexadecimal characters.")
    if not isinstance(item.name, str) or not item.name.strip() or len(item.name.strip()) > 80:
        raise WebhookError("Webhook names must contain 1–80 characters.")
    if not isinstance(item.enabled, bool):
        raise WebhookError("Webhook enabled state must be a boolean.")
    return Webhook(
        item.webhook_id, item.name.strip(), _validate_url(item.url),
        item.enabled, _validate_headers(item.headers),
    )


def default_webhook_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "webhooks.json"


class WebhookStore:
    """Atomically persist webhook endpoints with owner-only file permissions."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_webhook_path()

    def load(self) -> tuple[Webhook, ...]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WebhookError("Saved webhooks are invalid JSON.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != WEBHOOK_FORMAT
            or payload.get("version") != WEBHOOK_VERSION
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("webhooks"), list)
            or len(payload["webhooks"]) > MAX_WEBHOOKS
        ):
            raise WebhookError("Saved webhooks have an unsupported format.")
        result = []
        seen = set()
        for item in payload["webhooks"]:
            if not isinstance(item, dict):
                raise WebhookError("Saved webhook entries must be objects.")
            webhook = _normalize(Webhook(
                item.get("id"), item.get("name"), item.get("url"),
                item.get("enabled", True), item.get("headers", {}),
            ))
            if webhook.webhook_id in seen:
                raise WebhookError("Saved webhook IDs must be unique.")
            seen.add(webhook.webhook_id)
            result.append(webhook)
        return tuple(result)

    def save(self, webhooks: Iterable[Webhook]) -> tuple[Webhook, ...]:
        import uuid

        if isinstance(webhooks, (str, bytes)):
            raise WebhookError("Webhooks must be an iterable of webhook entries.")
        normalized = tuple(_normalize(item) for item in webhooks)
        if len(normalized) > MAX_WEBHOOKS:
            raise WebhookError(f"At most {MAX_WEBHOOKS} webhooks can be configured.")
        if len({item.webhook_id for item in normalized}) != len(normalized):
            raise WebhookError("Webhook IDs must be unique.")
        payload = {
            "format": WEBHOOK_FORMAT,
            "version": WEBHOOK_VERSION,
            "webhooks": [
                {"id": item.webhook_id, "name": item.name, "url": item.url,
                 "enabled": item.enabled, "headers": dict(item.headers or {})}
                for item in normalized
            ],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".webhooks-", delete=False,
            ) as stream:
                stream.write(content)
                temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return normalized

    def add(self, name: str, url: str, headers: Mapping[str, str] | None = None) -> tuple[Webhook, ...]:
        import uuid

        current = list(self.load())
        if len(current) >= MAX_WEBHOOKS:
            raise WebhookError(f"At most {MAX_WEBHOOKS} webhooks can be configured.")
        webhook = _normalize(Webhook(uuid.uuid4().hex, name, url, True, headers or {}))
        current.append(webhook)
        return self.save(current)

    def update(self, webhook_id: str, **changes) -> tuple[Webhook, ...]:
        current = list(self.load())
        for index, item in enumerate(current):
            if item.webhook_id == webhook_id:
                current[index] = _normalize(Webhook(
                    item.webhook_id, changes.get("name", item.name),
                    changes.get("url", item.url), changes.get("enabled", item.enabled),
                    changes.get("headers", item.headers),
                ))
                return self.save(current)
        raise WebhookError("The selected webhook no longer exists.")

    def remove(self, webhook_id: str) -> tuple[Webhook, ...]:
        current = list(self.load())
        updated = [item for item in current if item.webhook_id != webhook_id]
        if len(updated) == len(current):
            raise WebhookError("The selected webhook no longer exists.")
        return self.save(updated)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deliver_webhooks(
    webhooks: Iterable[Webhook],
    event: Mapping[str, object],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    opener=None,
) -> tuple[WebhookDelivery, ...]:
    """Deliver one event to enabled endpoints; isolate all endpoint failures."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("Webhook timeout must be greater than zero.")
    if not isinstance(event, Mapping):
        raise WebhookError("Webhook event must be an object.")
    payload = json.dumps(dict(event), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 64 * 1024:
        raise WebhookError("Webhook event payload exceeds 64 KiB.")
    client = opener or build_opener(_NoRedirect())
    results = []
    for raw in webhooks:
        try:
            webhook = _normalize(raw)
            if not webhook.enabled:
                continue
            headers = {"Content-Type": "application/json; charset=utf-8",
                       "Accept": "application/json", "User-Agent": "Aniyori/0.1"}
            headers.update(dict(webhook.headers or {}))
            request = Request(webhook.url, data=payload, headers=headers, method="POST")
            with client.open(request, timeout=timeout) as response:
                status = getattr(response, "status", response.getcode())
                response.read(MAX_RESPONSE_BYTES)
            if not 200 <= status < 300:
                raise WebhookError(f"Endpoint returned HTTP {status}.")
            results.append(WebhookDelivery(webhook.webhook_id, webhook.name, True, f"HTTP {status}"))
        except HTTPError as error:
            results.append(WebhookDelivery(raw.webhook_id, raw.name, False, f"HTTP {error.code}"))
        except (OSError, URLError, TimeoutError, ValueError, WebhookError) as error:
            results.append(WebhookDelivery(raw.webhook_id, raw.name, False, str(error)))
    return tuple(results)
