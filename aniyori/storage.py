"""SQLite persistence for the local anime library."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .models import AnimeEntry, WatchStatus


def default_database_path() -> Path:
    """Return the XDG data location without creating it until needed."""
    import os

    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "aniyori" / "library.sqlite3"


class LibraryStorage:
    """Store the local library in a small SQLite database."""

    def __init__(self, database_path: str | Path | None = None):
        self.path = Path(database_path) if database_path else default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
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
    def _to_entry(row: sqlite3.Row) -> AnimeEntry:
        return AnimeEntry(
            title=row["title"],
            storage_id=row["id"],
            episodes_total=row["episodes_total"],
            episodes_watched=row["episodes_watched"],
            status=WatchStatus(row["status"]),
            provider=row["provider"],
            provider_id=row["provider_id"],
        )

    def list_entries(self) -> list[AnimeEntry]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, episodes_total, episodes_watched, status, provider, provider_id "
                "FROM anime ORDER BY title COLLATE NOCASE, id"
            ).fetchall()
        return [self._to_entry(row) for row in rows]

    def add(self, entry: AnimeEntry) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO anime
                        (title, episodes_total, episodes_watched, status, provider, provider_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.title.strip(),
                        entry.episodes_total,
                        entry.episodes_watched,
                        entry.status.value,
                        entry.provider,
                        entry.provider_id,
                    ),
                )
        except sqlite3.IntegrityError as error:
            if entry.provider and entry.provider_id:
                raise ValueError("This catalogue entry is already in your library.") from error
            raise

    def update_progress(self, entry_id: int | str, episodes_watched: int) -> bool:
        """Update one entry by database ID; title strings remain supported for compatibility."""
        if episodes_watched < 0:
            raise ValueError("Watched episode count cannot be negative")
        with self._connect() as connection:
            if isinstance(entry_id, int):
                row = connection.execute(
                    "SELECT id, episodes_total FROM anime WHERE id = ?", (entry_id,)
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT id, episodes_total FROM anime "
                    "WHERE title = ? COLLATE NOCASE ORDER BY id LIMIT 1",
                    (entry_id,),
                ).fetchone()
            if row is None:
                return False
            total = row["episodes_total"]
            if total is not None and episodes_watched > total:
                raise ValueError("Watched episodes cannot exceed the total")
            status = "completed" if total is not None and total > 0 and episodes_watched == total else "watching"
            connection.execute(
                """
                UPDATE anime
                SET episodes_watched = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (episodes_watched, status, row["id"]),
            )
            return True

    def remove(self, entry_id: int | str) -> bool:
        """Remove one entry by database ID; title strings remain supported."""
        with self._connect() as connection:
            if isinstance(entry_id, int):
                cursor = connection.execute("DELETE FROM anime WHERE id = ?", (entry_id,))
            else:
                cursor = connection.execute(
                    "DELETE FROM anime WHERE id = (SELECT id FROM anime "
                    "WHERE title = ? COLLATE NOCASE ORDER BY id LIMIT 1)",
                    (entry_id,),
                )
            return cursor.rowcount > 0

    def replace_all(self, entries: Iterable[AnimeEntry]) -> None:
        """Replace the stored library atomically (useful for import/sync)."""
        with self._connect() as connection:
            connection.execute("DELETE FROM anime")
            connection.executemany(
                """
                INSERT INTO anime
                    (title, episodes_total, episodes_watched, status, provider, provider_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.title.strip(),
                        entry.episodes_total,
                        entry.episodes_watched,
                        entry.status.value,
                        entry.provider,
                        entry.provider_id,
                    )
                    for entry in entries
                ],
            )
