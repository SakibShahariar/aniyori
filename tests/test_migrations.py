"""Tests for SQLite schema versioning and migrations."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from aniyori.storage import LibraryStorage


class StorageMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "library.sqlite3"

    def tearDown(self):
        self.temp_dir.cleanup()

    def schema_version(self):
        with sqlite3.connect(self.database) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_fresh_database_runs_initial_migration(self):
        storage = LibraryStorage(self.database)

        self.assertEqual(self.schema_version(), storage.LATEST_SCHEMA_VERSION)
        self.assertEqual(storage.list_entries(), [])

    def test_existing_unversioned_database_migrates_without_data_loss(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                CREATE TABLE anime (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    episodes_total INTEGER,
                    episodes_watched INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'planning',
                    provider TEXT,
                    provider_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, provider_id)
                )
                """
            )
            connection.execute(
                "INSERT INTO anime (title, episodes_watched) VALUES (?, ?)",
                ("Existing series", 7),
            )

        storage = LibraryStorage(self.database)

        self.assertEqual(self.schema_version(), storage.LATEST_SCHEMA_VERSION)
        entries = storage.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Existing series")
        self.assertEqual(entries[0].episodes_watched, 7)

    def test_migration_is_idempotent(self):
        LibraryStorage(self.database)
        LibraryStorage(self.database)

        self.assertEqual(self.schema_version(), LibraryStorage.LATEST_SCHEMA_VERSION)

    def test_newer_schema_version_is_rejected(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA user_version = 99")

        with self.assertRaisesRegex(RuntimeError, "newer than supported"):
            LibraryStorage(self.database)


if __name__ == "__main__":
    unittest.main()
