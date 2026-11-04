"""Shared proxy, timeout, retry, and TLS settings for outbound HTTP requests."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import ssl
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener


NETWORK_SETTINGS_FORMAT = "aniyori-network-settings"
NETWORK_SETTINGS_VERSION = 1
DEFAULT_TIMEOUT = 15
MAX_TIMEOUT = 120
MAX_RETRIES = 5


class NetworkSettingsError(ValueError):
    """Raised when network settings are invalid or cannot be persisted."""


@dataclass(frozen=True, slots=True)
class NetworkSettings:
    proxy_url: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT
    retries: int = 2
    ca_bundle_path: str | None = None


def default_network_settings_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "network.json"


def normalize_network_settings(settings: NetworkSettings) -> NetworkSettings:
    if not isinstance(settings, NetworkSettings):
        raise NetworkSettingsError("Network settings must be a NetworkSettings value.")
    proxy = settings.proxy_url
    if proxy is not None:
        if not isinstance(proxy, str) or not proxy.strip():
            raise NetworkSettingsError("Proxy URL must be empty or a valid HTTP(S) URL.")
        proxy = proxy.strip()
        try:
            parsed = urlsplit(proxy)
            _ = parsed.port
        except ValueError as error:
            raise NetworkSettingsError("Proxy URL is malformed.") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise NetworkSettingsError("Proxy must be an HTTP(S) URL without credentials or a path.")
    timeout = settings.timeout_seconds
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= MAX_TIMEOUT:
        raise NetworkSettingsError(f"Request timeout must be between 1 and {MAX_TIMEOUT} seconds.")
    retries = settings.retries
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= MAX_RETRIES:
        raise NetworkSettingsError(f"Retry count must be between 0 and {MAX_RETRIES}.")
    ca_path = settings.ca_bundle_path
    if ca_path is not None:
        if not isinstance(ca_path, str) or not ca_path.strip():
            raise NetworkSettingsError("CA bundle path must be empty or an absolute file path.")
        path = Path(ca_path.strip()).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise NetworkSettingsError("Custom CA bundle must point to an existing absolute file.")
        ca_path = str(path)
    return NetworkSettings(proxy, timeout, retries, ca_path)


class NetworkSettingsStore:
    """Persist non-secret network preferences atomically with private permissions."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_network_settings_path()

    def load(self) -> NetworkSettings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return NetworkSettings()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NetworkSettingsError("Saved network settings are unreadable.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != NETWORK_SETTINGS_FORMAT
            or isinstance(payload.get("version"), bool)
            or payload.get("version") != NETWORK_SETTINGS_VERSION
        ):
            raise NetworkSettingsError("Saved network settings have an unsupported format.")
        try:
            return normalize_network_settings(NetworkSettings(
                proxy_url=payload.get("proxy_url"),
                timeout_seconds=payload.get("timeout_seconds", DEFAULT_TIMEOUT),
                retries=payload.get("retries", 2),
                ca_bundle_path=payload.get("ca_bundle_path"),
            ))
        except (TypeError, ValueError) as error:
            raise NetworkSettingsError("Saved network settings are invalid: " + str(error)) from error

    def save(self, settings: NetworkSettings) -> NetworkSettings:
        normalized = normalize_network_settings(settings)
        payload = {
            "format": NETWORK_SETTINGS_FORMAT,
            "version": NETWORK_SETTINGS_VERSION,
            "proxy_url": normalized.proxy_url,
            "timeout_seconds": normalized.timeout_seconds,
            "retries": normalized.retries,
            "ca_bundle_path": normalized.ca_bundle_path,
        }
        content = json.dumps(payload, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".network-settings-", delete=False,
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


def build_network_opener(*handlers):
    """Build an opener using configured proxy and verified system/custom CA roots."""
    settings = NetworkSettingsStore().load()
    proxies = (
        {"http": settings.proxy_url, "https": settings.proxy_url}
        if settings.proxy_url else None
    )
    context = ssl.create_default_context(cafile=settings.ca_bundle_path)
    return build_opener(
        ProxyHandler(proxies),
        HTTPSHandler(context=context),
        *handlers,
    )


def open_request(
    request: Request,
    *,
    timeout: float | None = None,
    retry_safe: bool = False,
    opener=None,
    urlopen_func=None,
):
    """Open a request with configured timeout/proxy/TLS and bounded safe retries.

    Only explicitly idempotent requests may be retried. Certificate validation
    is always enabled; a custom CA bundle extends/replaces trust roots safely.
    """
    settings = NetworkSettingsStore().load()
    selected_timeout = settings.timeout_seconds if timeout is None else timeout
    if isinstance(selected_timeout, bool) or not isinstance(selected_timeout, (int, float)) or selected_timeout <= 0:
        raise ValueError("Request timeout must be greater than zero.")
    retries = settings.retries if retry_safe else 0
    client = opener
    if client is None and (settings.proxy_url or settings.ca_bundle_path):
        client = build_network_opener()
    attempt = 0
    while True:
        try:
            if client is not None:
                return client.open(request, timeout=selected_timeout)
            open_func = urlopen_func
            if open_func is None:
                from urllib.request import urlopen as open_func
            return open_func(request, timeout=selected_timeout)
        except HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600
            if not retry_safe or not retryable or attempt >= retries:
                raise
        except (URLError, TimeoutError, OSError):
            if not retry_safe or attempt >= retries:
                raise
        attempt += 1
        time.sleep(min(0.25 * (2 ** (attempt - 1)), 1.0))
