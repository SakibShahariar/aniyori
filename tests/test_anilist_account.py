"""Offline tests for desktop AniList OAuth helpers and settings."""

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from aniyori.services.anilist_account import (
    AUTH_PIN_REDIRECT_URI,
    AniListAccountError,
    AniListAccountSettingsStore,
    build_authorization_url,
    parse_access_token,
    validate_client_id,
)


def jwt_with_payload(payload):
    encode = lambda value: base64.urlsafe_b64encode(
        json.dumps(value).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{encode({'alg': 'none'})}.{encode(payload)}.signature"


class AniListOAuthHelperTests(unittest.TestCase):
    def test_client_id_is_numeric_and_normalized(self):
        self.assertEqual(validate_client_id(" 12345 "), "12345")
        for value in ("", "0", "-1", "abc", "12 34", "1.2", None):
            with self.subTest(value=value):
                with self.assertRaises(AniListAccountError):
                    validate_client_id(value)

    def test_authorization_url_uses_implicit_grant(self):
        url = build_authorization_url("12345")
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "anilist.co")
        self.assertEqual(parsed.path, "/api/v2/oauth/authorize")
        self.assertEqual(parse_qs(parsed.query), {
            "client_id": ["12345"], "response_type": ["token"],
        })
        self.assertEqual(AUTH_PIN_REDIRECT_URI, "https://anilist.co/api/v2/oauth/pin")

    def test_parse_raw_access_token_and_url_fragment(self):
        token = jwt_with_payload({"exp": 2000})
        self.assertEqual(parse_access_token(token, now=1000), token)
        url = f"{AUTH_PIN_REDIRECT_URI}#access_token={token}&token_type=Bearer"
        self.assertEqual(parse_access_token(url, now=1000), token)

    def test_parse_accepts_access_token_in_query_string(self):
        token = jwt_with_payload({"exp": 2000})
        url = f"https://example.test/callback?access_token={token}"
        self.assertEqual(parse_access_token(url, now=1000), token)

    def test_parse_rejects_malformed_or_expired_tokens(self):
        invalid = (
            "", "not-a-jwt", "one.two", "a.b.c",
            jwt_with_payload({"exp": "2000"}),
            jwt_with_payload({}),
            jwt_with_payload({"exp": 1000}),
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(AniListAccountError):
                    parse_access_token(value, now=1000)

    def test_parse_rejects_urls_without_access_token(self):
        with self.assertRaisesRegex(AniListAccountError, "does not contain"):
            parse_access_token("https://anilist.co/api/v2/oauth/pin", now=1000)


class AniListAccountSettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "anilist-account.json"
        self.store = AniListAccountSettingsStore(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_settings_return_safe_defaults(self):
        self.assertEqual(self.store.load(), {
            "client_id": "", "viewer_id": None, "viewer_name": None,
        })

    def test_save_and_reload_public_client_id_and_account_label(self):
        self.store.save(client_id="12345", viewer_id=42, viewer_name="AniUser")
        self.assertEqual(self.store.load(), {
            "client_id": "12345", "viewer_id": 42, "viewer_name": "AniUser",
        })
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertNotIn("access_token", self.path.read_text(encoding="utf-8"))

    def test_save_rejects_invalid_account_metadata(self):
        for kwargs in (
            {"client_id": "bad"},
            {"client_id": "123", "viewer_id": True},
            {"client_id": "123", "viewer_id": 0},
            {"client_id": "123", "viewer_name": ""},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(AniListAccountError):
                    self.store.save(**kwargs)

    def test_invalid_settings_file_fails_closed(self):
        self.path.write_text('{"client_id": "123"}', encoding="utf-8")
        with self.assertRaises(AniListAccountError):
            self.store.load()


if __name__ == "__main__":
    unittest.main()
