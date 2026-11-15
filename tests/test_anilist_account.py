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



class AniListAuthenticatedClientTests(unittest.TestCase):
    def test_viewer_request_uses_bearer_token(self):
        import io
        from unittest.mock import patch
        from aniyori.services.anilist import AniListClient

        payload = {"data": {"Viewer": {"id": 42, "name": "AniUser", "siteUrl": "https://anilist.co/user/AniUser"}}}
        response = io.BytesIO(json.dumps(payload).encode("utf-8"))
        with patch("aniyori.services.anilist.urlopen", return_value=response) as request:
            viewer = AniListClient(access_token="jwt.token.signature").get_viewer()
        sent_request = request.call_args.args[0]
        self.assertEqual(sent_request.get_header("Authorization"), "Bearer jwt.token.signature")
        self.assertEqual(viewer["id"], 42)
        self.assertEqual(viewer["name"], "AniUser")

    def test_account_requests_require_a_token(self):
        from aniyori.services.anilist import AniListClient, AniListError

        client = AniListClient()
        with self.assertRaises(AniListError):
            client.get_viewer()
        with self.assertRaises(AniListError):
            client.get_user_library(42)
        with self.assertRaises(AniListError):
            client.save_media_list_entry(21, "CURRENT", 2)

    def test_user_library_flattens_lists_and_normalises_media(self):
        from unittest.mock import patch
        from aniyori.services.anilist import AniListClient

        payload = {
            "MediaListCollection": {
                "lists": [
                    {"entries": [{
                        "mediaId": 21, "status": "CURRENT", "progress": 4,
                        "score": 8, "updatedAt": 1700000000,
                        "media": {
                            "id": 21, "title": {"english": "Example", "romaji": "Example"},
                            "episodes": 12, "coverImage": {"large": "https://img.test/cover.jpg"},
                        },
                    }]},
                    {"entries": [{
                        "mediaId": 22, "status": "PLANNING", "progress": 0,
                        "score": 0, "updatedAt": 1700000001,
                        "media": {"id": 22, "title": {"romaji": "Next"}, "episodes": 24},
                    }]},
                ],
            },
        }
        client = AniListClient(access_token="token")
        with patch.object(client, "_request", return_value=payload) as request:
            entries = client.get_user_library(42)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[1], {"userId": 42})
        self.assertEqual([item["media_id"] for item in entries], [21, 22])
        self.assertEqual(entries[0]["media"]["title"], "Example")
        self.assertEqual(entries[0]["progress"], 4)
        self.assertEqual(entries[1]["status"], "PLANNING")

    def test_user_library_accepts_empty_collection(self):
        from unittest.mock import patch
        from aniyori.services.anilist import AniListClient

        client = AniListClient(access_token="token")
        with patch.object(client, "_request", return_value={"MediaListCollection": None}):
            self.assertEqual(client.get_user_library(42), [])

    def test_user_library_rejects_malformed_and_duplicate_entries(self):
        from unittest.mock import patch
        from aniyori.services.anilist import AniListClient, AniListError

        client = AniListClient(access_token="token")
        malformed = (
            {"MediaListCollection": []},
            {"MediaListCollection": {"lists": [None]}},
            {"MediaListCollection": {"lists": [{"entries": [None]}]}},
            {"MediaListCollection": {"lists": [{"entries": [{
                "mediaId": 21, "status": "UNKNOWN", "progress": 0,
                "updatedAt": 1, "media": {"id": 21},
            }]}]}},
        )
        for payload in malformed:
            with self.subTest(payload=payload), patch.object(client, "_request", return_value=payload):
                with self.assertRaises(AniListError):
                    client.get_user_library(42)
        duplicate = {"MediaListCollection": {"lists": [
            {"entries": [
                {"mediaId": 21, "status": "CURRENT", "progress": 1, "updatedAt": 1, "media": {"id": 21}},
            ]},
            {"entries": [
                {"mediaId": 21, "status": "CURRENT", "progress": 1, "updatedAt": 1, "media": {"id": 21}},
            ]},
        ]}}
        with patch.object(client, "_request", return_value=duplicate):
            with self.assertRaises(AniListError):
                client.get_user_library(42)

    def test_save_media_list_entry_validates_and_confirms_mutation(self):
        from unittest.mock import patch
        from aniyori.services.anilist import AniListClient, AniListError

        client = AniListClient(access_token="token")
        response = {"SaveMediaListEntry": {
            "id": 10, "mediaId": 21, "status": "CURRENT",
            "progress": 4, "updatedAt": 1700000000,
        }}
        with patch.object(client, "_request", return_value=response) as request:
            result = client.save_media_list_entry(21, "CURRENT", 4)
        self.assertEqual(result, response["SaveMediaListEntry"])
        self.assertEqual(request.call_args.args[1], {
            "mediaId": 21, "status": "CURRENT", "progress": 4,
        })
        with patch.object(client, "_request", return_value={"SaveMediaListEntry": None}):
            with self.assertRaises(AniListError):
                client.save_media_list_entry(21, "CURRENT", 4)
        for args in ((True, "CURRENT", 1), (21, "UNKNOWN", 1), (21, "CURRENT", -1), (21, "CURRENT", True)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                client.save_media_list_entry(*args)



class AniListImportMappingTests(unittest.TestCase):
    def test_import_maps_remote_status_progress_and_cover(self):
        from aniyori.models import WatchStatus
        from aniyori.services.anilist_account import import_entry_from_anilist

        entry = import_entry_from_anilist({
            "media_id": 21, "status": "CURRENT", "progress": 4,
            "media": {
                "id": 21, "title": "Example Anime", "episodes": 12,
                "cover_image": "https://img.test/cover.jpg",
            },
        })
        self.assertEqual(entry.title, "Example Anime")
        self.assertEqual(entry.provider, "anilist")
        self.assertEqual(entry.provider_id, "21")
        self.assertEqual(entry.episodes_total, 12)
        self.assertEqual(entry.episodes_watched, 4)
        self.assertEqual(entry.status, WatchStatus.WATCHING)
        self.assertEqual(entry.cover_image, "https://img.test/cover.jpg")

    def test_import_maps_all_supported_list_statuses(self):
        from aniyori.models import WatchStatus
        from aniyori.services.anilist_account import import_entry_from_anilist

        expected = {
            "CURRENT": WatchStatus.WATCHING,
            "PLANNING": WatchStatus.PLANNING,
            "COMPLETED": WatchStatus.COMPLETED,
            "PAUSED": WatchStatus.PAUSED,
            "DROPPED": WatchStatus.DROPPED,
            "REPEATING": WatchStatus.WATCHING,
        }
        for remote_status, local_status in expected.items():
            with self.subTest(status=remote_status):
                entry = import_entry_from_anilist({
                    "media_id": 21, "status": remote_status, "progress": 0,
                    "media": {"id": 21, "title": "Example"},
                })
                self.assertEqual(entry.status, local_status)

    def test_import_preserves_progress_when_total_is_unknown_or_inconsistent(self):
        from aniyori.services.anilist_account import import_entry_from_anilist

        for total in (None, 0, -1, 10_001, 3):
            with self.subTest(total=total):
                entry = import_entry_from_anilist({
                    "media_id": 21, "status": "CURRENT", "progress": 4,
                    "media": {"id": 21, "title": "Example", "episodes": total},
                })
                self.assertEqual(entry.episodes_watched, 4)
                self.assertIsNone(entry.episodes_total)

    def test_import_rejects_invalid_remote_identity_status_and_progress(self):
        from aniyori.services.anilist_account import import_entry_from_anilist

        base = {
            "media_id": 21, "status": "CURRENT", "progress": 2,
            "media": {"id": 21, "title": "Example", "episodes": 12},
        }
        variants = (
            {"media_id": 0},
            {"media_id": True},
            {"status": "UNKNOWN"},
            {"progress": True},
            {"progress": -1},
            {"progress": 10_001},
            {"media": {"id": 21, "title": "  "}},
        )
        for changes in variants:
            candidate = {**base, **changes}
            with self.subTest(changes=changes), self.assertRaises(AniListAccountError):
                import_entry_from_anilist(candidate)



class AniListSyncPlanningTests(unittest.TestCase):
    def test_sync_plan_separates_imports_conflicts_local_only_and_unchanged(self):
        from aniyori.models import AnimeEntry, WatchStatus
        from aniyori.services.anilist_account import build_sync_plan

        local = [
            AnimeEntry(
                title="Unchanged", episodes_total=12, episodes_watched=4,
                status=WatchStatus.WATCHING, provider="anilist", provider_id="21",
            ),
            AnimeEntry(
                title="Conflict", episodes_total=24, episodes_watched=2,
                status=WatchStatus.WATCHING, provider="anilist", provider_id="22",
            ),
            AnimeEntry(
                title="Local only", episodes_total=12, episodes_watched=1,
                status=WatchStatus.PLANNING, provider="anilist", provider_id="23",
            ),
            AnimeEntry(title="Manual", episodes_total=12),
        ]
        remote = [
            {"media_id": 21, "status": "CURRENT", "progress": 4, "media": {"id": 21}},
            {"media_id": 22, "status": "CURRENT", "progress": 5, "media": {"id": 22}},
            {"media_id": 24, "status": "PLANNING", "progress": 0, "media": {"id": 24}},
        ]
        plan = build_sync_plan(local, remote)
        self.assertEqual(plan["unchanged"], 1)
        self.assertEqual([item["media_id"] for item in plan["imports"]], [24])
        self.assertEqual(len(plan["conflicts"]), 1)
        self.assertEqual(plan["conflicts"][0]["local"].provider_id, "22")
        self.assertEqual(plan["conflicts"][0]["remote"]["progress"], 5)
        self.assertEqual([item.provider_id for item in plan["local_only"]], ["23"])

    def test_sync_plan_treats_repeating_as_watching_for_local_comparison(self):
        from aniyori.models import AnimeEntry, WatchStatus
        from aniyori.services.anilist_account import build_sync_plan

        local = [AnimeEntry(
            title="Repeat", episodes_watched=2, status=WatchStatus.WATCHING,
            provider="anilist", provider_id="21",
        )]
        plan = build_sync_plan(local, [
            {"media_id": 21, "status": "REPEATING", "progress": 2, "media": {"id": 21}},
        ])
        self.assertEqual(plan["unchanged"], 1)
        self.assertEqual(plan["conflicts"], ())

    def test_sync_plan_rejects_duplicate_or_malformed_remote_ids(self):
        from aniyori.services.anilist_account import build_sync_plan

        duplicate = [
            {"media_id": 21, "status": "CURRENT", "progress": 0},
            {"media_id": 21, "status": "CURRENT", "progress": 0},
        ]
        with self.assertRaises(AniListAccountError):
            build_sync_plan([], duplicate)
        for remote in (
            [{"media_id": True, "status": "CURRENT", "progress": 0}],
            [{"media_id": 21, "status": [], "progress": 0}],
            [{"media_id": 21, "status": "CURRENT", "progress": True}],
        ):
            with self.subTest(remote=remote), self.assertRaises(AniListAccountError):
                build_sync_plan([], remote)

    def test_local_status_maps_to_supported_anilist_statuses(self):
        from aniyori.models import AnimeEntry, WatchStatus
        from aniyori.services.anilist_account import anilist_status_for_local

        expected = {
            WatchStatus.PLANNING: "PLANNING",
            WatchStatus.WATCHING: "CURRENT",
            WatchStatus.COMPLETED: "COMPLETED",
            WatchStatus.PAUSED: "PAUSED",
            WatchStatus.DROPPED: "DROPPED",
        }
        for local_status, remote_status in expected.items():
            with self.subTest(status=local_status):
                self.assertEqual(
                    anilist_status_for_local(AnimeEntry(title="Example", status=local_status)),
                    remote_status,
                )



class AniListSyncResolutionTests(unittest.TestCase):
    def test_local_sync_payload_maps_status_and_progress(self):
        from aniyori.models import AnimeEntry, WatchStatus
        from aniyori.services.anilist_account import local_entry_sync_payload

        entry = AnimeEntry(
            title="Example", episodes_watched=7, status=WatchStatus.PAUSED,
            provider="anilist", provider_id="123",
        )
        self.assertEqual(local_entry_sync_payload(entry), {
            "media_id": 123, "status": "PAUSED", "progress": 7,
        })

    def test_local_sync_payload_rejects_unlinked_or_malformed_entries(self):
        from aniyori.models import AnimeEntry
        from aniyori.services.anilist_account import local_entry_sync_payload

        for entry in (
            AnimeEntry(title="Manual"),
            AnimeEntry(title="Bad ID", provider="anilist", provider_id="abc"),
        ):
            with self.subTest(entry=entry), self.assertRaises(AniListAccountError):
                local_entry_sync_payload(entry)

    def test_remote_resolution_preserves_local_database_identity(self):
        from aniyori.models import AnimeEntry, WatchStatus
        from aniyori.services.anilist_account import local_entry_from_remote

        existing = AnimeEntry(
            title="Old title", episodes_watched=1, status=WatchStatus.PLANNING,
            provider="anilist", provider_id="21", storage_id=99,
        )
        remote = {
            "media_id": 21, "status": "CURRENT", "progress": 5,
            "media": {
                "id": 21, "title": "Updated title", "episodes": 12,
                "cover_image": "https://img.test/cover.jpg",
            },
        }
        updated = local_entry_from_remote(remote, existing)
        self.assertEqual(updated.storage_id, 99)
        self.assertEqual(updated.title, "Updated title")
        self.assertEqual(updated.episodes_watched, 5)
        self.assertEqual(updated.status, WatchStatus.WATCHING)

    def test_remote_resolution_rejects_a_different_provider_id(self):
        from aniyori.models import AnimeEntry
        from aniyori.services.anilist_account import local_entry_from_remote

        existing = AnimeEntry(
            title="Example", provider="anilist", provider_id="22", storage_id=99,
        )
        remote = {
            "media_id": 21, "status": "CURRENT", "progress": 0,
            "media": {"id": 21, "title": "Example"},
        }
        with self.assertRaises(AniListAccountError):
            local_entry_from_remote(remote, existing)


if __name__ == "__main__":
    unittest.main()
