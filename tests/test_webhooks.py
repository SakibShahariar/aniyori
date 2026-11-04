"""Tests for safe webhook configuration and isolated HTTP delivery."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from aniyori.services.webhooks import (
    Webhook, WebhookError, WebhookStore, deliver_webhooks,
)


class WebhookStoreTests(unittest.TestCase):
    def test_add_update_disable_remove_and_private_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "webhooks.json"
            store = WebhookStore(path)
            saved = store.add("Home automation", "https://example.org/hook",
                              {"X-Api-Key": "secret-value"})
            self.assertEqual(len(saved), 1)
            self.assertEqual(store.load(), saved)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            changed = store.update(saved[0].webhook_id, enabled=False)
            self.assertFalse(changed[0].enabled)
            self.assertEqual(store.remove(saved[0].webhook_id), ())

    def test_rejects_unsafe_urls_and_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            store = WebhookStore(Path(directory) / "hooks.json")
            for url in ("file:///etc/passwd", "https://user:pass@example.org/hook",
                        "https://example.org/hook#fragment", "https://example.org:bad/hook"):
                with self.subTest(url=url), self.assertRaises(WebhookError):
                    store.add("bad", url)
            for headers in ({"Host": "evil.example"}, {"Content-Length": "1"},
                            {"X-Test": "bad\r\nInjected: yes"}):
                with self.subTest(headers=headers), self.assertRaises(WebhookError):
                    store.add("bad", "https://example.org/hook", headers)

    def test_rejects_duplicate_ids_and_corrupt_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hooks.json"
            store = WebhookStore(path)
            item = Webhook("a" * 32, "one", "https://example.org")
            with self.assertRaisesRegex(WebhookError, "unique"):
                store.save([item, item])
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(WebhookError, "invalid JSON"):
                store.load()

    def test_delivers_json_to_enabled_hooks_and_skips_disabled(self):
        hooks = (
            Webhook("a" * 32, "enabled", "https://example.org/hook", True,
                    {"X-Api-Key": "token"}),
            Webhook("b" * 32, "disabled", "https://example.org/off", False),
        )
        response = MagicMock()
        response.status = 204
        response.getcode.return_value = 204
        response.__enter__.return_value = response
        client = MagicMock()
        client.open.return_value = response
        results = deliver_webhooks(hooks, {"event": "watch", "episode": 3}, opener=client)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        request = client.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"event": "watch", "episode": 3})
        self.assertEqual(request.get_header("X-api-key"), "token")

    def test_one_endpoint_failure_does_not_prevent_later_delivery(self):
        hooks = (
            Webhook("a" * 32, "broken", "https://example.org/broken"),
            Webhook("b" * 32, "healthy", "https://example.org/healthy"),
        )
        response = MagicMock()
        response.status = 200
        response.getcode.return_value = 200
        response.__enter__.return_value = response
        client = MagicMock()
        client.open.side_effect = [OSError("offline"), response]
        results = deliver_webhooks(hooks, {"event": "status"}, opener=client)
        self.assertEqual([item.success for item in results], [False, True])

    def test_payload_and_timeout_validation(self):
        with self.assertRaises(ValueError):
            deliver_webhooks((), {}, timeout=0)
        with self.assertRaises(WebhookError):
            deliver_webhooks((), {"data": "x" * (65 * 1024)})


if __name__ == "__main__":
    unittest.main()
