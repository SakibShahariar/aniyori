"""Tests for complete Aniyori backup creation and restore validation."""

import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from aniyori.backup import BackupError, create_backup, restore_backup


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "data" / "library.sqlite3"
        self.database.parent.mkdir()
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE anime (title TEXT NOT NULL)")
            connection.execute("INSERT INTO anime VALUES ('Frieren')")
            connection.execute(
                "CREATE TABLE watch_history (id INTEGER PRIMARY KEY, anime_title TEXT NOT NULL, episode INTEGER, action TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO watch_history (anime_title, episode, action) VALUES ('Frieren', 7, 'episode')"
            )
        self.config = self.root / "config" / "aniyori"
        self.config.mkdir(parents=True)
        (self.config / "feeds.json").write_text('{"feeds": []}', encoding="utf-8")
        (self.config / "rules.json").write_text('{"rules": []}', encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_backup_restores_database_and_all_regular_config_files(self):
        archive = self.root / "backup.zip"
        create_backup(self.database, self.config, archive)
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE anime SET title = 'Changed'")
        (self.config / "feeds.json").write_text("changed", encoding="utf-8")
        (self.config / "new.json").write_text("new setting", encoding="utf-8")

        restore_backup(archive, self.database, self.config)

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT title FROM anime").fetchone()[0], "Frieren")
            self.assertEqual(
                connection.execute(
                    "SELECT anime_title, episode, action FROM watch_history"
                ).fetchone(),
                ("Frieren", 7, "episode"),
            )
        self.assertEqual((self.config / "feeds.json").read_text(encoding="utf-8"), '{"feeds": []}')
        self.assertFalse((self.config / "new.json").exists())
        self.assertEqual((self.config / "rules.json").read_text(encoding="utf-8"), '{"rules": []}')
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)

    def test_restore_rejects_corrupt_archive_without_touching_existing_data(self):
        archive = self.root / "broken.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../outside", "bad")
        with self.assertRaises(BackupError):
            restore_backup(archive, self.database, self.config)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT title FROM anime").fetchone()[0], "Frieren")

    def test_restore_rejects_modified_backup_payload(self):
        archive = self.root / "tampered.zip"
        create_backup(self.database, self.config, archive)
        with zipfile.ZipFile(archive, "a") as output:
            output.writestr("config/feeds.json", "tampered")
        with self.assertRaises(BackupError):
            restore_backup(archive, self.database, self.config)

    def test_backup_requires_an_existing_database(self):
        with self.assertRaises(BackupError):
            create_backup(self.root / "missing.sqlite3", self.config, self.root / "missing.zip")


if __name__ == "__main__":
    unittest.main()
