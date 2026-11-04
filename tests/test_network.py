"""Tests for shared proxy, timeout, retry, and TLS network preferences."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from aniyori.services.network import (
    NetworkSettings, NetworkSettingsError, NetworkSettingsStore,
    normalize_network_settings, open_request,
)
from urllib.request import Request


class NetworkSettingsTests(unittest.TestCase):
    def test_round_trip_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.json"
            store = NetworkSettingsStore(path)
            settings = NetworkSettings("http://127.0.0.1:8080", 30, 4)
            self.assertEqual(store.save(settings), settings)
            self.assertEqual(store.load(), settings)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_custom_ca_bundle_must_be_existing_absolute_file(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory) / "ca.pem"
            ca.write_text("test CA placeholder", encoding="utf-8")
            settings = normalize_network_settings(NetworkSettings(ca_bundle_path=str(ca)))
            self.assertEqual(settings.ca_bundle_path, str(ca))
            with self.assertRaises(NetworkSettingsError):
                normalize_network_settings(NetworkSettings(ca_bundle_path="relative.pem"))
            with self.assertRaises(NetworkSettingsError):
                normalize_network_settings(NetworkSettings(ca_bundle_path=str(ca) + ".missing"))

    def test_rejects_proxy_credentials_paths_and_invalid_values(self):
        for proxy in ("ftp://proxy.example", "http://user:pass@proxy.example",
                      "http://proxy.example/path", "http://proxy.example:bad"):
            with self.subTest(proxy=proxy), self.assertRaises(NetworkSettingsError):
                normalize_network_settings(NetworkSettings(proxy_url=proxy))
        for timeout in (0, 121, True, 1.5):
            with self.subTest(timeout=timeout), self.assertRaises(NetworkSettingsError):
                normalize_network_settings(NetworkSettings(timeout_seconds=timeout))
        for retries in (-1, 6, True, 1.5):
            with self.subTest(retries=retries), self.assertRaises(NetworkSettingsError):
                normalize_network_settings(NetworkSettings(retries=retries))

    def test_invalid_saved_settings_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.json"
            path.write_text('{"format":"wrong","version":1}', encoding="utf-8")
            with self.assertRaises(NetworkSettingsError):
                NetworkSettingsStore(path).load()

    def test_idempotent_requests_retry_transient_failures(self):
        opener = MagicMock()
        response = MagicMock()
        opener.open.side_effect = [URLError("offline"), response]
        with patch("aniyori.services.network.NetworkSettingsStore.load",
                   return_value=NetworkSettings(retries=1)):
            with patch("aniyori.services.network.time.sleep"):
                result = open_request(Request("https://example.org"), retry_safe=True, opener=opener)
        self.assertIs(result, response)
        self.assertEqual(opener.open.call_count, 2)

    def test_non_idempotent_requests_are_not_retried(self):
        opener = MagicMock()
        opener.open.side_effect = URLError("offline")
        with patch("aniyori.services.network.NetworkSettingsStore.load",
                   return_value=NetworkSettings(retries=4)):
            with self.assertRaises(URLError):
                open_request(Request("https://example.org", data=b"payload"), retry_safe=False, opener=opener)
        self.assertEqual(opener.open.call_count, 1)

    def test_http_server_errors_retry_but_client_errors_do_not(self):
        opener = MagicMock()
        opener.open.side_effect = [
            HTTPError("https://example.org", 503, "Unavailable", None, None),
            MagicMock(),
        ]
        with patch("aniyori.services.network.NetworkSettingsStore.load",
                   return_value=NetworkSettings(retries=1)):
            with patch("aniyori.services.network.time.sleep"):
                open_request(Request("https://example.org"), retry_safe=True, opener=opener)
        self.assertEqual(opener.open.call_count, 2)


if __name__ == "__main__":
    unittest.main()
