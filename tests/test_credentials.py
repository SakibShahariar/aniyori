"""Tests for fail-closed desktop credential storage."""

import subprocess
import unittest
from unittest.mock import Mock

from aniyori.services.credentials import (
    CredentialStoreUnavailable,
    SecretServiceCredentialStore,
)


class SecretServiceCredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.runner = Mock()
        self.store = SecretServiceCredentialStore(
            binary="/usr/bin/secret-tool",
        )
        self.store_runner = self.store._run
        self.store._run = Mock()

    def test_store_passes_secret_via_stdin_not_command_arguments(self):
        self.store._run.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.store.store("aniyori", "qbittorrent:https://localhost", "top-secret")
        args, kwargs = self.store._run.call_args
        self.assertEqual(args[0][0], "store")
        self.assertNotIn("top-secret", args[0])
        self.assertEqual(kwargs["secret"], "top-secret")

    def test_lookup_returns_secret_without_trailing_output_newline(self):
        self.store._run.return_value = subprocess.CompletedProcess(
            [], 0, "secret with spaces\n", ""
        )
        self.assertEqual(
            self.store.lookup("aniyori", "qbittorrent:local"),
            "secret with spaces",
        )

    def test_lookup_returns_none_when_item_does_not_exist(self):
        self.store._run.return_value = subprocess.CompletedProcess([], 1, "", "")
        self.assertIsNone(self.store.lookup("aniyori", "missing"))

    def test_remove_reports_whether_an_item_was_removed(self):
        self.store._run.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.assertTrue(self.store.remove("aniyori", "qbittorrent:local"))
        self.store._run.return_value = subprocess.CompletedProcess([], 1, "", "")
        self.assertFalse(self.store.remove("aniyori", "qbittorrent:local"))

    def test_missing_secret_tool_fails_closed(self):
        with self.assertRaises(CredentialStoreUnavailable):
            SecretServiceCredentialStore(binary="")

    def test_credentials_with_line_breaks_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.store("aniyori", "account", "password\nsecond-line")

    def test_failed_store_is_not_silently_ignored(self):
        self.store._run.return_value = subprocess.CompletedProcess([], 1, "", "locked")
        with self.assertRaises(CredentialStoreUnavailable):
            self.store.store("aniyori", "account", "secret")


if __name__ == "__main__":
    unittest.main()
