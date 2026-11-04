"""Tests for portable storage roots and isolated settings profiles."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from aniyori.services.profiles import (
    ProfileError, ProfileStore, configure_storage_environment,
)


class ProfileStoreTests(unittest.TestCase):
    def test_default_profile_preserves_standard_xdg_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = {"HOME": str(home)}
            context = configure_storage_environment(app_directory=home, environ=env)
            self.assertFalse(context.portable)
            self.assertEqual(Path(env["XDG_DATA_HOME"]), home / ".local/share")
            self.assertEqual(Path(env["XDG_CONFIG_HOME"]), home / ".config")
            self.assertEqual(context.active_profile, "Default")

    def test_named_profiles_are_isolated_and_switchable(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = {"HOME": str(home)}
            context = configure_storage_environment(app_directory=home, environ=env)
            store = ProfileStore(context.registry_path)
            created = store.create("Work Profile")
            self.assertEqual(created.profile_id, "work-profile")
            store.switch(created.profile_id)
            switched = configure_storage_environment(app_directory=home, environ=env)
            self.assertEqual(switched.active_profile, "Work Profile")
            self.assertIn("profiles/work-profile", env["XDG_DATA_HOME"])
            self.assertIn("profiles/work-profile", env["XDG_CONFIG_HOME"])
            self.assertIn("profiles/work-profile", env["XDG_CACHE_HOME"])

    def test_remove_profile_resets_active_and_removes_only_its_data(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = {"HOME": str(home)}
            context = configure_storage_environment(app_directory=home, environ=env)
            store = ProfileStore(context.registry_path)
            profile = store.create("Temporary")
            for key in ("ANIYORI_BASE_DATA_HOME", "ANIYORI_BASE_CONFIG_HOME", "ANIYORI_BASE_CACHE_HOME"):
                path = Path(env[key]) / "profiles" / profile.profile_id / "aniyori"
                path.mkdir(parents=True)
                (path / "sentinel").write_text("data", encoding="utf-8")
            store.switch(profile.profile_id)
            store.remove(profile.profile_id)
            self.assertEqual(store.active_profile().profile_id, "default")
            for key in ("ANIYORI_BASE_DATA_HOME", "ANIYORI_BASE_CONFIG_HOME", "ANIYORI_BASE_CACHE_HOME"):
                self.assertFalse((Path(env[key]) / "profiles" / profile.profile_id).exists())

    def test_portable_mode_uses_self_contained_data_config_and_cache_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app"
            app.mkdir()
            portable = Path(directory) / "portable-data"
            env = {"HOME": str(Path(directory) / "home"), "ANIYORI_PORTABLE_DIR": str(portable)}
            context = configure_storage_environment(app_directory=app, environ=env)
            self.assertTrue(context.portable)
            for key in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
                self.assertTrue(Path(env[key]).is_relative_to(portable))
            self.assertTrue(context.registry_path.is_relative_to(portable))

    def test_profiles_are_private_and_invalid_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            with self.assertRaises(ProfileError):
                store.create("../outside")
            profile = store.create("Personal")
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ProfileError):
                store.create("personal")
            with self.assertRaises(ProfileError):
                store.remove("default")
            self.assertEqual(profile.profile_id, "personal")

    def test_corrupt_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ProfileError, "unreadable"):
                ProfileStore(path).list_profiles()


if __name__ == "__main__":
    unittest.main()
