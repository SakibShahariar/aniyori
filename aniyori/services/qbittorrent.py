"""Small, dependency-free client for the qBittorrent Web API."""

from __future__ import annotations

from http.cookiejar import CookieJar
import json
import ipaddress
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPCookieProcessor,
    Request,
    build_opener,
)
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
        timeout: int = DEFAULT_TIMEOUT,
        opener=None,
    ):
        self.server_url = validate_server_url(server_url)
        if not isinstance(username, str) or not username.strip():
            raise ValueError("A qBittorrent WebUI username is required.")
        if not isinstance(password, str) or not password:
            raise ValueError("A qBittorrent WebUI password is required.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Request timeout must be greater than zero.")
        self.username = username.strip()
        self.password = password
        self.timeout = timeout
        self._opener = opener or build_opener(
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
            with self._opener.open(request, timeout=self.timeout) as response:
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
