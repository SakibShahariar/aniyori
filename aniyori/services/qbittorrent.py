"""Small, dependency-free client for the qBittorrent Web API."""

from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import tempfile
import ipaddress
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPCookieProcessor,
    Request,
)
from .network import build_network_opener, open_request
import secrets


DEFAULT_TIMEOUT = 10
_INFO_HASH = re.compile(r"(?i)^[0-9a-f]{40}$")


class QBittorrentError(RuntimeError):
    """Base error for qBittorrent connection and submission failures."""


class QBittorrentAuthenticationError(QBittorrentError):
    """Raised when qBittorrent rejects the supplied credentials."""


class _RejectRedirects(HTTPRedirectHandler):
    """Do not forward credentials or cookies to a redirected origin."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def validate_server_url(value: str) -> str:
    """Normalize a qBittorrent WebUI URL and require TLS off the local host."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter the qBittorrent WebUI address.")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use an HTTP(S) WebUI URL without credentials, query, or fragment.")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("The qBittorrent WebUI port is invalid.") from error
    host = parsed.hostname.rstrip(".").casefold()
    is_loopback = host == "localhost"
    try:
        is_loopback = is_loopback or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if parsed.scheme == "http" and not is_loopback:
        raise ValueError("Use HTTPS for qBittorrent servers outside this device.")
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port is not None:
        netloc = f"{netloc}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def validate_magnet_uri(value: str) -> str:
    """Accept only BitTorrent v1 magnet links with a valid info hash."""
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("The release magnet link is invalid.")
    parsed = urlsplit(value)
    if parsed.scheme != "magnet" or parsed.netloc or parsed.fragment:
        raise ValueError("Only valid BitTorrent magnet links can be submitted.")
    from urllib.parse import parse_qs

    info_hashes = parse_qs(parsed.query, strict_parsing=False).get("xt", ())
    if not any(
        item.startswith("urn:btih:") and _INFO_HASH.fullmatch(item[9:])
        for item in info_hashes
    ):
        raise ValueError("The magnet link does not contain a valid BitTorrent v1 info hash.")
    return value



QBITTORRENT_SETTINGS_FORMAT = "aniyori-qbittorrent-settings"
QBITTORRENT_SETTINGS_VERSION = 1


@dataclass(frozen=True, slots=True)
class QBittorrentSettings:
    """Non-secret qBittorrent connection preferences."""

    server_url: str
    username: str
    category: str = ""
    paused: bool = False


def default_qbittorrent_settings_path() -> Path:
    """Return the XDG path for non-secret qBittorrent settings."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "qbittorrent.json"


class QBittorrentSettingsStore:
    """Atomically persist qBittorrent preferences without storing passwords."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_qbittorrent_settings_path()

    @staticmethod
    def normalize(settings: QBittorrentSettings) -> QBittorrentSettings:
        if not isinstance(settings, QBittorrentSettings):
            raise ValueError("qBittorrent settings are malformed.")
        server_url = validate_server_url(settings.server_url)
        if (
            not isinstance(settings.username, str)
            or not settings.username.strip()
            or len(settings.username) > 256
        ):
            raise ValueError("A valid qBittorrent username is required.")
        if (
            not isinstance(settings.category, str)
            or len(settings.category) > 128
            or any(ord(character) < 32 for character in settings.category)
        ):
            raise ValueError("The qBittorrent category is invalid.")
        if not isinstance(settings.paused, bool):
            raise ValueError("The qBittorrent paused preference must be a boolean.")
        return QBittorrentSettings(
            server_url=server_url,
            username=settings.username.strip(),
            category=settings.category.strip(),
            paused=settings.paused,
        )

    def load(self) -> QBittorrentSettings | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise QBittorrentError("Saved qBittorrent settings are unreadable.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != QBITTORRENT_SETTINGS_FORMAT
            or payload.get("version") != QBITTORRENT_SETTINGS_VERSION
            or isinstance(payload.get("version"), bool)
        ):
            raise QBittorrentError("Saved qBittorrent settings have an unsupported format.")
        try:
            settings = QBittorrentSettings(
                server_url=payload.get("server_url"),
                username=payload.get("username"),
                category=payload.get("category", ""),
                paused=payload.get("paused", False),
            )
            return self.normalize(settings)
        except (TypeError, ValueError) as error:
            raise QBittorrentError("Saved qBittorrent settings are invalid.") from error

    def save(self, settings: QBittorrentSettings) -> None:
        normalized = self.normalize(settings)
        payload = {
            "format": QBITTORRENT_SETTINGS_FORMAT,
            "version": QBITTORRENT_SETTINGS_VERSION,
            "server_url": normalized.server_url,
            "username": normalized.username,
            "category": normalized.category,
            "paused": normalized.paused,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".qbittorrent-",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class QBittorrentClient:
    """Submit a magnet link using qBittorrent's cookie-authenticated Web API.

    Credentials are accepted only for this client instance and are never written
    to disk. HTTP is permitted only for loopback connections; remote servers
    must use HTTPS to protect the WebUI password in transit.
    """

    def __init__(
        self,
        server_url: str,
        username: str,
        password: str,
        *,
        timeout: int | None = None,
        opener=None,
    ):
        self.server_url = validate_server_url(server_url)
        if not isinstance(username, str) or not username.strip():
            raise ValueError("A qBittorrent WebUI username is required.")
        if not isinstance(password, str) or not password:
            raise ValueError("A qBittorrent WebUI password is required.")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0
        ):
            raise ValueError("Request timeout must be greater than zero.")
        self.username = username.strip()
        self.password = password
        self.timeout = timeout
        self._opener = opener or build_network_opener(
            HTTPCookieProcessor(CookieJar()), _RejectRedirects()
        )

    def _request(
        self, path: str, data: bytes | None = None, *, content_type: str | None = None
    ):
        url = self.server_url + path
        headers = {
            "Accept": "text/plain, application/json",
            "Referer": self.server_url + "/",
            "User-Agent": "Aniyori/0.1.0",
        }
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(
            url,
            data=data,
            headers=headers,
            method="POST" if data is not None else "GET",
        )
        try:
            with open_request(request, timeout=self.timeout, opener=self._opener) as response:
                return response.read().decode("utf-8", errors="replace").strip()
        except HTTPError as error:
            if error.code == 403:
                raise QBittorrentAuthenticationError(
                    "qBittorrent rejected the request (HTTP 403). Check WebUI credentials and access settings."
                ) from error
            raise QBittorrentError(
                f"qBittorrent returned HTTP {error.code}."
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise QBittorrentError(
                "Could not reach the qBittorrent WebUI. Check its address and connection."
            ) from error

    def _login(self) -> None:
        body = urlencode({
            "username": self.username,
            "password": self.password,
        }).encode("utf-8")
        try:
            response = self._request("/api/v2/auth/login", body)
        except QBittorrentError as error:
            if isinstance(error, QBittorrentAuthenticationError):
                raise
            raise
        if response.casefold() != "ok.":
            raise QBittorrentAuthenticationError(
                "qBittorrent did not accept the WebUI credentials."
            )

    def test_connection(self) -> None:
        """Verify credentials and the WebUI endpoint without changing torrent state."""
        self._login()
        try:
            self._request("/api/v2/auth/logout", b"")
        except QBittorrentError:
            pass

    @staticmethod
    def _normalize_torrent(payload: dict) -> dict:
        """Validate one qBittorrent torrent-info record before exposing it to the UI."""
        if not isinstance(payload, dict):
            raise QBittorrentError("qBittorrent returned an invalid torrent record.")
        info_hash = payload.get("hash")
        if not isinstance(info_hash, str) or not re.fullmatch(r"(?i)(?:[0-9a-f]{40}|[0-9a-f]{64})", info_hash):
            raise QBittorrentError("qBittorrent returned a torrent with an invalid hash.")
        name = payload.get("name")
        state = payload.get("state")
        if not isinstance(name, str) or len(name) > 2048 or not isinstance(state, str) or len(state) > 64:
            raise QBittorrentError("qBittorrent returned invalid torrent details.")
        progress = payload.get("progress", 0.0)
        if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not 0 <= progress <= 1:
            raise QBittorrentError("qBittorrent returned an invalid progress value.")
        def count(key, default=0):
            value = payload.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int):
                raise QBittorrentError(f"qBittorrent returned an invalid {key} value.")
            return value
        eta = count("eta", -1)
        return {
            "hash": info_hash.lower(),
            "name": name,
            "state": state,
            "progress": float(progress),
            "size": max(0, count("size")),
            "downloaded": max(0, count("completed")),
            "download_speed": max(0, count("dlspeed")),
            "upload_speed": max(0, count("upspeed")),
            "eta": eta if eta >= 0 else None,
            "seeds": max(0, count("num_seeds")),
            "leechers": max(0, count("num_leechs")),
            "category": payload.get("category", "") if isinstance(payload.get("category", ""), str) else "",
        }

    def list_torrents(self) -> tuple[dict, ...]:
        """Return a validated snapshot of the configured qBittorrent queue."""
        self._login()
        try:
            response = self._request("/api/v2/torrents/info?filter=all")
            try:
                payload = json.loads(response)
            except (TypeError, json.JSONDecodeError) as error:
                raise QBittorrentError("qBittorrent returned an unreadable torrent list.") from error
            if not isinstance(payload, list) or len(payload) > 10000:
                raise QBittorrentError("qBittorrent returned an invalid torrent list.")
            return tuple(self._normalize_torrent(item) for item in payload)
        finally:
            try:
                self._request("/api/v2/auth/logout", b"")
            except QBittorrentError:
                pass

    def _torrent_action(self, action: str, info_hash: str, *, delete_files: bool = False) -> None:
        """Run one explicit queue action; deletion preserves downloaded files by default."""
        if not isinstance(info_hash, str) or not re.fullmatch(r"(?i)(?:[0-9a-f]{40}|[0-9a-f]{64})", info_hash):
            raise ValueError("The torrent identifier is invalid.")
        if action not in {"pause", "resume", "delete"}:
            raise ValueError("The requested torrent action is invalid.")
        fields = {"hashes": info_hash.lower()}
        if action == "delete":
            if not isinstance(delete_files, bool):
                raise ValueError("The delete-files option must be a boolean.")
            fields["deleteFiles"] = "true" if delete_files else "false"
        self._login()
        try:
            self._request(
                f"/api/v2/torrents/{action}",
                urlencode(fields).encode("utf-8"),
                content_type="application/x-www-form-urlencoded",
            )
        finally:
            try:
                self._request("/api/v2/auth/logout", b"")
            except QBittorrentError:
                pass

    def pause_torrent(self, info_hash: str) -> None:
        """Pause one torrent after explicit user action."""
        self._torrent_action("pause", info_hash)

    def resume_torrent(self, info_hash: str) -> None:
        """Resume one torrent after explicit user action."""
        self._torrent_action("resume", info_hash)

    def remove_torrent(self, info_hash: str, *, delete_files: bool = False) -> None:
        """Remove one torrent; downloaded files are retained unless explicitly requested."""
        self._torrent_action("delete", info_hash, delete_files=delete_files)

    def add_magnet(
        self,
        magnet_uri: str,
        *,
        category: str | None = None,
        paused: bool = False,
    ) -> None:
        """Submit one validated magnet URI; downloads start only after this call."""
        magnet = validate_magnet_uri(magnet_uri)
        if category is not None:
            if not isinstance(category, str) or len(category) > 128 or any(
                ord(character) < 32 for character in category
            ):
                raise ValueError("The qBittorrent category is invalid.")
            category = category.strip()
        if not isinstance(paused, bool):
            raise ValueError("The paused option must be a boolean.")

        boundary = "----Aniyori" + secrets.token_hex(16)
        fields = [("urls", magnet)]
        if category:
            fields.append(("category", category))
        if paused:
            fields.append(("paused", "true"))
        chunks = []
        for name, value in fields:
            chunks.extend((
                f"--{boundary}\r\n".encode("ascii"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                value.encode("utf-8"),
                b"\r\n",
            ))
        chunks.append(f"--{boundary}--\r\n".encode("ascii"))
        payload = b"".join(chunks)

        self._login()
        try:
            result = self._request(
                "/api/v2/torrents/add",
                payload,
                content_type=f"multipart/form-data; boundary={boundary}",
            )
            if result.casefold() not in {"ok.", "ok"}:
                try:
                    outcome = json.loads(result)
                except (TypeError, json.JSONDecodeError):
                    outcome = None
                if not isinstance(outcome, dict):
                    raise QBittorrentError(
                        "qBittorrent did not confirm that the release was added."
                    )
                added = outcome.get("success_count", 0)
                pending = outcome.get("pending_count", 0)
                if (
                    isinstance(added, bool) or not isinstance(added, int)
                    or isinstance(pending, bool) or not isinstance(pending, int)
                    or added + pending < 1
                ):
                    raise QBittorrentError(
                        "qBittorrent did not confirm that the release was added."
                    )
        finally:
            try:
                self._request("/api/v2/auth/logout", b"")
            except QBittorrentError:
                pass
