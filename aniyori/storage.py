"""SQLite persistence for the local anime library."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .models import MAX_EPISODE_COUNT, AnimeEntry, WatchStatus


def default_database_path() -> Path:
    """Return the XDG data location without creating it until needed."""
    import os

    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    if not data_home.is_absolute():
        data_home = Path.home() / ".local/share"
    return data_home / "aniyori" / "library.sqlite3"


class LibraryStorage:
    """Store the local library in a small SQLite database."""

    LATEST_SCHEMA_VERSION = 2

    @staticmethod
    def _is_duplicate_catalogue_error(error: sqlite3.IntegrityError) -> bool:
        """Identify only the catalogue identity constraint, not all DB integrity errors."""
        return "UNIQUE constraint failed: anime.provider, anime.provider_id" in str(error)

    def __init__(self, database_path: str | Path | None = None):
        self.path = Path(database_path) if database_path else default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _migration_1(connection: sqlite3.Connection) -> None:
        """Create the initial library schema; safe for existing unversioned databases."""
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS anime (
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
            "CREATE INDEX IF NOT EXISTS anime_title_idx ON anime(title COLLATE NOCASE)"
        )

    @staticmethod
    def _migration_2(connection: sqlite3.Connection) -> None:
        """Add optional AniList cover URLs without disturbing existing library rows."""
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(anime)")
        }
        if "cover_image" not in columns:
            connection.execute("ALTER TABLE anime ADD COLUMN cover_image TEXT")

    def _initialize(self) -> None:
        migrations = {1: self._migration_1, 2: self._migration_2}
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > self.LATEST_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {version} is newer than supported "
                    f"version {self.LATEST_SCHEMA_VERSION}."
                )
            while version < self.LATEST_SCHEMA_VERSION:
                next_version = version + 1
                migration = migrations.get(next_version)
                if migration is None:
                    raise RuntimeError(f"Missing database migration {next_version}.")
                migration(connection)
                connection.execute(f"PRAGMA user_version = {next_version}")
                version = next_version

    @staticmethod
    def _to_entry(row: sqlite3.Row) -> AnimeEntry:
        return AnimeEntry(
            title=row["title"],
            storage_id=row["id"],
            episodes_total=row["episodes_total"],
            episodes_watched=row["episodes_watched"],
            status=WatchStatus(row["status"]),
            provider=row["provider"],
            provider_id=row["provider_id"],
            cover_image=row["cover_image"],
        )

    def list_entries(self) -> list[AnimeEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, episodes_total, episodes_watched, status, provider, provider_id, cover_image "
                "FROM anime ORDER BY title COLLATE NOCASE, id"
            ).fetchall()
        return [self._to_entry(row) for row in rows]

    def find_manual_title_matches(self, title: str) -> list[AnimeEntry]:
        """Find manual entries with the same case- and whitespace-insensitive title."""
        normalized_title = " ".join(title.split()).casefold()
        if not normalized_title:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, episodes_total, episodes_watched, status, provider, provider_id, cover_image
                FROM anime
                WHERE provider IS NULL AND provider_id IS NULL
                ORDER BY title COLLATE NOCASE, id
                """
            ).fetchall()
        return [
            self._to_entry(row)
            for row in rows
            if " ".join(row["title"].split()).casefold() == normalized_title
        ]

    def add(self, entry: AnimeEntry) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO anime
                        (title, episodes_total, episodes_watched, status, provider, provider_id, cover_image)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.title.strip(),
                        entry.episodes_total,
                        entry.episodes_watched,
                        entry.status.value,
                        entry.provider,
                        entry.provider_id,
                        entry.cover_image,
                    ),
                )
        except sqlite3.IntegrityError as error:
            if self._is_duplicate_catalogue_error(error):
                raise ValueError("This catalogue entry is already in your library.") from error
            raise

    def update_progress(self, storage_id: int, episodes_watched: int) -> bool:
        """Update progress for exactly one entry identified by its database ID."""
        if isinstance(storage_id, bool) or not isinstance(storage_id, int) or storage_id <= 0:
            raise ValueError("A valid storage ID is required.")
        if isinstance(episodes_watched, bool) or not isinstance(episodes_watched, int):
            raise ValueError("Watched episode count must be a whole number.")
        if episodes_watched < 0:
            raise ValueError("Watched episode count cannot be negative")
        if episodes_watched > MAX_EPISODE_COUNT:
            raise ValueError(
                f"Watched episode count cannot exceed {MAX_EPISODE_COUNT:,}."
            )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, episodes_total, status FROM anime WHERE id = ?",
                (storage_id,),
            ).fetchone()
            if row is None:
                return False
            total = row["episodes_total"]
            if total is not None and episodes_watched > total:
                raise ValueError("Watched episodes cannot exceed the total")

            current_status = row["status"]
            if total is not None and total > 0 and episodes_watched == total:
                status = "completed"
            elif current_status in ("paused", "dropped") or (
                current_status == "completed" and total is None
            ):
                status = current_status
            else:
                status = "watching"

            connection.execute(
                """
                UPDATE anime
                SET episodes_watched = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (episodes_watched, status, storage_id),
            )
            return True

    def update_entry(self, entry: AnimeEntry) -> bool:
        """Update editable fields for an existing entry identified by storage_id."""
        if entry.storage_id is None:
            raise ValueError("A storage ID is required to edit an anime.")
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE anime
                    SET title = ?, episodes_total = ?, episodes_watched = ?, status = ?,
                        provider = ?, provider_id = ?, cover_image = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (entry.title.strip(), entry.episodes_total, entry.episodes_watched,
                     entry.status.value, entry.provider, entry.provider_id,
                     entry.cover_image, entry.storage_id),
                )
                return cursor.rowcount > 0
        except sqlite3.IntegrityError as error:
            if self._is_duplicate_catalogue_error(error):
                raise ValueError("This catalogue entry is already in your library.") from error
            raise

    def remove(self, storage_id: int) -> bool:
        """Remove exactly one entry identified by its database ID."""
        if isinstance(storage_id, bool) or not isinstance(storage_id, int) or storage_id <= 0:
            raise ValueError("A valid storage ID is required.")
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM anime WHERE id = ?", (storage_id,))
            return cursor.rowcount > 0

    def restore(self, entry: AnimeEntry) -> None:
        """Restore a deleted entry with its original database ID."""
        storage_id = entry.storage_id
        if isinstance(storage_id, bool) or not isinstance(storage_id, int) or storage_id <= 0:
            raise ValueError("A valid storage ID is required to restore an anime.")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO anime
                        (id, title, episodes_total, episodes_watched, status, provider, provider_id, cover_image)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        storage_id,
                        entry.title.strip(),
                        entry.episodes_total,
                        entry.episodes_watched,
                        entry.status.value,
                        entry.provider,
                        entry.provider_id,
                        entry.cover_image,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "This entry could not be restored because its ID or catalogue entry is already in use."
            ) from error

    def replace_all(self, entries: Iterable[AnimeEntry]) -> None:
        """Replace the stored library atomically (useful for import/sync)."""
        with self._connect() as connection:
            connection.execute("DELETE FROM anime")
            connection.executemany(
                """
                INSERT INTO anime
                    (title, episodes_total, episodes_watched, status, provider, provider_id, cover_image)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.title.strip(),
                        entry.episodes_total,
                        entry.episodes_watched,
                        entry.status.value,
                        entry.provider,
                        entry.provider_id,
                        entry.cover_image,
                    )
                    for entry in entries
                ],
            )
