"""Tests for the qBittorrent Web API integration."""

import os
import stat
import tempfile
import unittest
from urllib.parse import parse_qs

from aniyori.services.qbittorrent import (
    QBittorrentAuthenticationError,
    QBittorrentClient,
    QBittorrentError,
    QBittorrentSettings,
    QBittorrentSettingsStore,
    validate_magnet_uri,
    validate_server_url,
)


MAGNET = "magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01&dn=Test"


class _Response:
    def __init__(self, body):
        self.body = body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class _Opener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return _Response(response)


class QBittorrentSettingsStoreTests(unittest.TestCase):
    def test_round_trip_persists_only_non_secret_preferences_with_private_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "qbittorrent.json")
            store = QBittorrentSettingsStore(path)
            settings = QBittorrentSettings(
                "http://localhost:8080/", " anime-user ", " Anime ", True
            )
            store.save(settings)
            self.assertEqual(
                store.load(),
                QBittorrentSettings("http://localhost:8080", "anime-user", "Anime", True),
            )
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600)
            with open(path, encoding="utf-8") as saved:
                content = saved.read()
            self.assertTrue(content.endswith("\n"))
            self.assertNotIn("password", content)
            self.assertNotIn("secret", content)
            store.clear()
            self.assertIsNone(store.load())

    def test_missing_settings_file_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(
                QBittorrentSettingsStore(os.path.join(directory, "missing.json")).load()
            )

    def test_rejects_insecure_remote_url_and_malformed_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            store = QBittorrentSettingsStore(os.path.join(directory, "settings.json"))
            with self.assertRaises(ValueError):
                store.save(QBittorrentSettings("http://seedbox.example", "user"))
            with self.assertRaises(ValueError):
                store.save(QBittorrentSettings("http://localhost", "", "Anime"))

class QBittorrentValidationTests(unittest.TestCase):
    def test_server_url_requires_tls_except_for_loopback(self):
        self.assertEqual(
            validate_server_url("http://127.0.0.1:8080/"),
            "http://127.0.0.1:8080",
        )
        self.assertEqual(
            validate_server_url("https://seedbox.example:8443/qbt/"),
            "https://seedbox.example:8443/qbt",
        )
        for value in (
            "http://seedbox.example:8080",
            "http://192.168.1.20:8080",
            "ftp://localhost",
            "https://user:pass@example.com",
            "https://example.com/path?token=x",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_server_url(value)

    def test_magnet_requires_valid_v1_info_hash(self):
        self.assertEqual(validate_magnet_uri(MAGNET), MAGNET)
        for value in (
            "https://example.com/file.torrent",
            "magnet:?xt=urn:btih:not-a-hash",
            "magnet:?dn=missing-hash",
            "magnet:?xt=urn:btih:" + "a" * 39,
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_magnet_uri(value)


class QBittorrentClientTests(unittest.TestCase):
    def test_connection_authenticates_and_logs_out_without_submitting(self):
        opener = _Opener(["Ok.", "Ok."])
        client = QBittorrentClient(
            "http://localhost:8080", "user", "password",
            opener=opener,
        )
        client.test_connection()
        self.assertEqual(len(opener.requests), 2)
        self.assertTrue(opener.requests[0][0].full_url.endswith("/api/v2/auth/login"))
        self.assertTrue(opener.requests[1][0].full_url.endswith("/api/v2/auth/logout"))

    def test_add_magnet_authenticates_submits_category_and_logs_out(self):
        opener = _Opener(["Ok.", "Ok.", "Ok."])
        client = QBittorrentClient(
            "http://localhost:8080", "anime-user", "secret",
            opener=opener,
        )
        client.add_magnet(MAGNET, category="Anime", paused=True)

        self.assertEqual(len(opener.requests), 3)
        login, add, logout = (item[0] for item in opener.requests)
        self.assertTrue(login.full_url.endswith("/api/v2/auth/login"))
        login_fields = parse_qs(login.data.decode())
        self.assertEqual(login_fields["username"], ["anime-user"])
        self.assertEqual(login_fields["password"], ["secret"])
        self.assertTrue(add.full_url.endswith("/api/v2/torrents/add"))
        content_type = add.get_header("Content-type")
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        self.assertIn(content_type.split("boundary=", 1)[1].encode(), add.data)
        self.assertIn(b'name="urls"', add.data)
        self.assertIn(MAGNET.encode(), add.data)
        self.assertIn(b'name="category"\r\n\r\nAnime', add.data)
        self.assertIn(b'name="paused"\r\n\r\ntrue', add.data)
        self.assertTrue(logout.full_url.endswith("/api/v2/auth/logout"))
        self.assertEqual(login.get_header("Referer"), "http://localhost:8080/")

    def test_rejected_credentials_do_not_submit_magnet(self):
        opener = _Opener(["Fails."])
        client = QBittorrentClient(
            "http://localhost:8080", "wrong", "wrong",
            opener=opener,
        )
        with self.assertRaises(QBittorrentAuthenticationError):
            client.add_magnet(MAGNET)
        self.assertEqual(len(opener.requests), 1)

    def test_accepts_newer_api_json_submission_confirmation(self):
        opener = _Opener([
            "Ok.",
            '{"success_count":0,"pending_count":1,"failure_count":0,"added_torrent_ids":["abc"]}',
            "Ok.",
        ])
        client = QBittorrentClient(
            "http://localhost:8080", "user", "password",
            opener=opener,
        )
        client.add_magnet(MAGNET)
        self.assertEqual(len(opener.requests), 3)

    def test_failed_add_is_reported_and_session_is_logged_out(self):
        opener = _Opener(["Ok.", "Fails.", "Ok."])
        client = QBittorrentClient(
            "http://localhost:8080", "user", "password",
            opener=opener,
        )
        with self.assertRaises(QBittorrentError):
            client.add_magnet(MAGNET)
        self.assertEqual(len(opener.requests), 3)

    def test_invalid_category_and_magnet_are_rejected_before_network(self):
        opener = _Opener([])
        client = QBittorrentClient(
            "http://localhost:8080", "user", "password",
            opener=opener,
        )
        with self.assertRaises(ValueError):
            client.add_magnet(MAGNET, category="bad\ncategory")
        with self.assertRaises(ValueError):
            client.add_magnet("https://example.com/torrent")
        self.assertEqual(opener.requests, [])


if __name__ == "__main__":
    unittest.main()
