"""SQLite persistence for the local anime library."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone, tzinfo
from pathlib import Path
from typing import Iterable, Mapping

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

    LATEST_SCHEMA_VERSION = 4

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

    @staticmethod
    def _migration_3(connection: sqlite3.Connection) -> None:
        """Add a durable watch-history log without changing existing library rows."""
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS watch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER,
                anime_title TEXT NOT NULL,
                episode INTEGER,
                action TEXT NOT NULL CHECK(action IN ('episode', 'progress', 'status')),
                source TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS watch_history_created_idx ON watch_history(created_at DESC, id DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS watch_history_anime_idx ON watch_history(anime_title COLLATE NOCASE)"
        )

    @staticmethod
    def _migration_4(connection: sqlite3.Connection) -> None:
        """Add explicit per-episode watched state without rewriting legacy progress."""
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS episode_progress (
                anime_id INTEGER NOT NULL REFERENCES anime(id) ON DELETE CASCADE,
                episode INTEGER NOT NULL CHECK(episode > 0),
                watched INTEGER NOT NULL CHECK(watched IN (0, 1)),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(anime_id, episode)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS episode_progress_watched_idx "
            "ON episode_progress(anime_id, watched, episode)"
        )

    def _initialize(self) -> None:
        migrations = {1: self._migration_1, 2: self._migration_2, 3: self._migration_3, 4: self._migration_4}
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

    @staticmethod
    def _insert_history_event(
        connection: sqlite3.Connection,
        *,
        anime_id: int,
        anime_title: str,
        episode: int | None,
        action: str,
        source: str,
        details: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO watch_history
                (anime_id, anime_title, episode, action, source, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (anime_id, anime_title, episode, action, source, details),
        )

    def get_updated_at_map(self) -> dict[int, str]:
        """Return last-edit timestamps for stable library IDs."""
        with self._connect() as connection:
            rows = connection.execute("SELECT id, updated_at FROM anime").fetchall()
        return {int(row["id"]): str(row["updated_at"]) for row in rows if row["updated_at"]}

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

    def update_progress(self, storage_id: int, episodes_watched: int, *, source: str = "manual") -> bool:
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
                "SELECT id, title, episodes_total, episodes_watched, status FROM anime WHERE id = ?",
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
            if episodes_watched != row["episodes_watched"]:
                self._insert_history_event(
                    connection, anime_id=storage_id, anime_title=row["title"],
                    episode=episodes_watched,
                    action="episode" if episodes_watched == row["episodes_watched"] + 1 else "progress",
                    source=source,
                    details=f"{row['episodes_watched']} → {episodes_watched}",
                )
            if current_status != status:
                self._insert_history_event(
                    connection, anime_id=storage_id, anime_title=row["title"],
                    episode=None, action="status", source=source,
                    details=f"{current_status} → {status}",
                )
            return True

    def update_entry(self, entry: AnimeEntry) -> bool:
        """Update editable fields for an existing entry identified by storage_id."""
        if entry.storage_id is None:
            raise ValueError("A storage ID is required to edit an anime.")
        try:
            with self._connect() as connection:
                previous = connection.execute(
                    "SELECT title, episodes_watched, status FROM anime WHERE id = ?",
                    (entry.storage_id,),
                ).fetchone()
                if previous is None:
                    return False
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
                if previous["episodes_watched"] != entry.episodes_watched:
                    self._insert_history_event(
                        connection, anime_id=entry.storage_id, anime_title=entry.title,
                        episode=entry.episodes_watched, action="progress", source="manual",
                        details=f"{previous['episodes_watched']} → {entry.episodes_watched}",
                    )
                if previous["status"] != entry.status.value:
                    self._insert_history_event(
                        connection, anime_id=entry.storage_id, anime_title=entry.title,
                        episode=None, action="status", source="manual",
                        details=f"{previous['status']} → {entry.status.value}",
                    )
                return cursor.rowcount > 0
        except sqlite3.IntegrityError as error:
            if self._is_duplicate_catalogue_error(error):
                raise ValueError("This catalogue entry is already in your library.") from error
            raise

    def update_entries(self, entries: Iterable[AnimeEntry]) -> int:
        """Update multiple entries atomically by storage ID."""
        updates = tuple(entries)
        if not updates:
            return 0
        ids = [entry.storage_id for entry in updates]
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in ids):
            raise ValueError("Every bulk-updated entry must have a valid storage ID.")
        if len(set(ids)) != len(ids):
            raise ValueError("A bulk update cannot contain duplicate storage IDs.")
        try:
            with self._connect() as connection:
                for entry in updates:
                    previous = connection.execute(
                        "SELECT title, episodes_watched, status FROM anime WHERE id = ?",
                        (entry.storage_id,),
                    ).fetchone()
                    if previous is None:
                        raise ValueError(f"Library entry {entry.storage_id} no longer exists.")
                    cursor = connection.execute(
                        """
                        UPDATE anime
                        SET title = ?, episodes_total = ?, episodes_watched = ?, status = ?,
                            provider = ?, provider_id = ?, cover_image = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            entry.title.strip(), entry.episodes_total,
                            entry.episodes_watched, entry.status.value,
                            entry.provider, entry.provider_id, entry.cover_image,
                            entry.storage_id,
                        ),
                    )
                    if cursor.rowcount == 0:
                        raise ValueError(f"Library entry {entry.storage_id} no longer exists.")
                    if previous["episodes_watched"] != entry.episodes_watched:
                        self._insert_history_event(
                            connection, anime_id=entry.storage_id, anime_title=entry.title,
                            episode=entry.episodes_watched, action="progress", source="bulk",
                            details=f"{previous['episodes_watched']} → {entry.episodes_watched}",
                        )
                    if previous["status"] != entry.status.value:
                        self._insert_history_event(
                            connection, anime_id=entry.storage_id, anime_title=entry.title,
                            episode=None, action="status", source="bulk",
                            details=f"{previous['status']} → {entry.status.value}",
                        )
            return len(updates)
        except sqlite3.IntegrityError as error:
            if self._is_duplicate_catalogue_error(error):
                raise ValueError("The bulk update would create a duplicate catalogue entry.") from error
            raise

    def update_progress_many(self, updates: Mapping[int, int], *, source: str = "bulk") -> int:
        """Apply progress changes atomically, preserving paused and dropped states."""
        if not isinstance(updates, Mapping):
            raise ValueError("Bulk progress updates must be a mapping.")
        if not updates:
            return 0
        prepared = []
        for storage_id, episodes_watched in updates.items():
            if isinstance(storage_id, bool) or not isinstance(storage_id, int) or storage_id <= 0:
                raise ValueError("Every bulk-updated entry must have a valid storage ID.")
            if isinstance(episodes_watched, bool) or not isinstance(episodes_watched, int):
                raise ValueError("Watched episode count must be a whole number.")
            if episodes_watched < 0 or episodes_watched > MAX_EPISODE_COUNT:
                raise ValueError(
                    f"Watched episode count must be between 0 and {MAX_EPISODE_COUNT:,}."
                )
            prepared.append((storage_id, episodes_watched))
        with self._connect() as connection:
            current_rows = {}
            for storage_id, episodes_watched in prepared:
                row = connection.execute(
                    "SELECT title, episodes_total, episodes_watched, status FROM anime WHERE id = ?",
                    (storage_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Library entry {storage_id} no longer exists.")
                total = row["episodes_total"]
                if total is not None and episodes_watched > total:
                    raise ValueError(
                        f"Progress for library entry {storage_id} cannot exceed its total."
                    )
                current_rows[storage_id] = row
            for storage_id, episodes_watched in prepared:
                row = current_rows[storage_id]
                total = row["episodes_total"]
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
                if episodes_watched != row["episodes_watched"]:
                    self._insert_history_event(
                        connection, anime_id=storage_id, anime_title=row["title"],
                        episode=episodes_watched, action="progress", source=source,
                        details=f"{row['episodes_watched']} → {episodes_watched}",
                    )
                if current_status != status:
                    self._insert_history_event(
                        connection, anime_id=storage_id, anime_title=row["title"],
                        episode=None, action="status", source=source,
                        details=f"{current_status} → {status}",
                    )
        return len(prepared)

    def list_episode_progress(self, storage_id: int) -> dict[int, bool]:
        """Return explicit watched state keyed by episode number."""
        if isinstance(storage_id, bool) or not isinstance(storage_id, int) or storage_id <= 0:
            raise ValueError("A valid storage ID is required.")
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM anime WHERE id = ?", (storage_id,)).fetchone() is None:
                raise ValueError(f"Library entry {storage_id} no longer exists.")
            rows = connection.execute(
                "SELECT episode, watched FROM episode_progress WHERE anime_id = ? ORDER BY episode",
                (storage_id,),
            ).fetchall()
        return {int(row["episode"]): bool(row["watched"]) for row in rows}

    def set_episode_watched(
        self, storage_id: int, episode: int, watched: bool = True, *, source: str = "manual"
    ) -> int:
        """Set one episode's watched state and derive aggregate progress transactionally.

        On first use, legacy aggregate progress is represented as episodes 1..N watched.
        This preserves the existing count while making the unavoidable legacy assumption
        explicit and editable (including skipped episodes).
        """
        if isinstance(storage_id, bool) or not isinstance(storage_id, int) or storage_id <= 0:
            raise ValueError("A valid storage ID is required.")
        if isinstance(episode, bool) or not isinstance(episode, int) or not 1 <= episode <= MAX_EPISODE_COUNT:
            raise ValueError(f"Episode number must be between 1 and {MAX_EPISODE_COUNT:,}.")
        if not isinstance(watched, bool):
            raise ValueError("Watched state must be a boolean.")
        if not isinstance(source, str) or not source.strip() or len(source) > 64:
            raise ValueError("Watch-history source must contain 1–64 characters.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT title, episodes_total, episodes_watched, status FROM anime WHERE id = ?",
                (storage_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Library entry {storage_id} no longer exists.")
            if row["episodes_total"] is not None and episode > row["episodes_total"]:
                raise ValueError("Episode number cannot exceed the known episode total.")
            existing_count = connection.execute(
                "SELECT COUNT(*) FROM episode_progress WHERE anime_id = ?", (storage_id,)
            ).fetchone()[0]
            if not existing_count and row["episodes_watched"]:
                connection.executemany(
                    "INSERT INTO episode_progress(anime_id, episode, watched) VALUES (?, ?, 1)",
                    ((storage_id, number) for number in range(1, row["episodes_watched"] + 1)),
                )
            previous = connection.execute(
                "SELECT watched FROM episode_progress WHERE anime_id = ? AND episode = ?",
                (storage_id, episode),
            ).fetchone()
            was_watched = bool(previous["watched"]) if previous is not None else False
            connection.execute(
                """
                INSERT INTO episode_progress(anime_id, episode, watched)
                VALUES (?, ?, ?)
                ON CONFLICT(anime_id, episode) DO UPDATE SET
                    watched = excluded.watched, updated_at = CURRENT_TIMESTAMP
                """,
                (storage_id, episode, int(watched)),
            )
            progress = int(connection.execute(
                "SELECT COUNT(*) FROM episode_progress WHERE anime_id = ? AND watched = 1",
                (storage_id,),
            ).fetchone()[0])
            total = row["episodes_total"]
            current_status = row["status"]
            if total is not None and total > 0 and progress == total:
                status = "completed"
            elif current_status in ("paused", "dropped"):
                status = current_status
            elif current_status == "completed" and total is None:
                status = current_status
            else:
                status = "watching" if progress else "planning"
            connection.execute(
                "UPDATE anime SET episodes_watched = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (progress, status, storage_id),
            )
            if watched and not was_watched:
                detail = (
                    "Rewatched episode"
                    if previous is not None
                    else "Marked episode watched"
                )
                self._insert_history_event(
                    connection, anime_id=storage_id, anime_title=row["title"],
                    episode=episode, action="episode", source=source.strip(), details=detail,
                )
            elif was_watched and not watched:
                self._insert_history_event(
                    connection, anime_id=storage_id, anime_title=row["title"],
                    episode=episode, action="progress", source=source.strip(),
                    details="Marked episode unwatched",
                )
            if current_status != status:
                self._insert_history_event(
                    connection, anime_id=storage_id, anime_title=row["title"],
                    episode=None, action="status", source=source.strip(),
                    details=f"{current_status} → {status}",
                )
            return progress

    def remove_many(self, storage_ids: Iterable[int]) -> int:
        """Remove multiple entries atomically, ignoring repeated IDs."""
        ids = tuple(dict.fromkeys(storage_ids))
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in ids):
            raise ValueError("Every bulk-removed entry must have a valid storage ID.")
        if not ids:
            return 0
        with self._connect() as connection:
            removed = 0
            for storage_id in ids:
                cursor = connection.execute(
                    "DELETE FROM anime WHERE id = ?", (storage_id,)
                )
                removed += cursor.rowcount
        return removed

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

    def record_watch_event(
        self, storage_id: int, *, episode: int | None = None,
        action: str = "episode", source: str = "manual", details: str | None = None,
    ) -> int:
        """Record an explicit episode event (including future player integrations)."""
        if isinstance(storage_id, bool) or not isinstance(storage_id, int) or storage_id <= 0:
            raise ValueError("A valid storage ID is required.")
        if action not in {"episode", "progress", "status"}:
            raise ValueError("Watch-history action must be episode, progress, or status.")
        if episode is not None and (
            isinstance(episode, bool) or not isinstance(episode, int)
            or episode < 1 or episode > MAX_EPISODE_COUNT
        ):
            raise ValueError("Episode number must be a positive whole number.")
        if not isinstance(source, str) or not source.strip() or len(source) > 64:
            raise ValueError("Watch-history source must contain 1–64 characters.")
        if details is not None and (not isinstance(details, str) or len(details) > 500):
            raise ValueError("Watch-history details must be text up to 500 characters.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT title FROM anime WHERE id = ?", (storage_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Library entry {storage_id} no longer exists.")
            cursor = connection.execute(
                """
                INSERT INTO watch_history
                    (anime_id, anime_title, episode, action, source, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (storage_id, row["title"], episode, action, source.strip(), details),
            )
            return int(cursor.lastrowid)

    def list_watch_history(
        self, *, anime: str | None = None, date_filter: str | None = None,
        action: str | None = None, limit: int = 500,
    ) -> list[dict[str, object]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5000:
            raise ValueError("Watch-history limit must be between 1 and 5,000.")
        clauses = []
        parameters = []
        if anime:
            clauses.append("anime_title LIKE ? COLLATE NOCASE")
            parameters.append(f"%{anime.strip()}%")
        if date_filter:
            try:
                date.fromisoformat(date_filter)
            except (TypeError, ValueError):
                raise ValueError("History date must use YYYY-MM-DD.") from None
            clauses.append("date(created_at) = ?")
            parameters.append(date_filter)
        if action and action != "all":
            if action not in {"episode", "progress", "status"}:
                raise ValueError("Unknown watch-history action.")
            clauses.append("action = ?")
            parameters.append(action)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, anime_id, anime_title, episode, action, source, details, created_at "
                "FROM watch_history" + where + " ORDER BY created_at DESC, id DESC LIMIT ?",
                (*parameters, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_watch_history_for_year(
        self, year: int, *, local_timezone: tzinfo | None = None
    ) -> list[dict[str, object]]:
        """Return only events belonging to a local calendar year.

        SQLite CURRENT_TIMESTAMP values are UTC. Convert local year boundaries
        to UTC before querying so large histories are filtered by the indexed
        timestamp column rather than loading the entire history into memory.
        """
        if isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999:
            raise ValueError("Year must be a valid calendar year.")
        if local_timezone is None:
            local_timezone = datetime.now().astimezone().tzinfo or timezone.utc
        if not isinstance(local_timezone, tzinfo):
            raise ValueError("A valid local timezone is required.")

        try:
            start = datetime(year, 1, 1, tzinfo=local_timezone).astimezone(timezone.utc)
            if year == 9999:
                end_text = "9999-12-31 23:59:59.999999"
            else:
                end = datetime(year + 1, 1, 1, tzinfo=local_timezone).astimezone(timezone.utc)
                end_text = end.strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, ValueError) as error:
            raise ValueError("The selected year is outside the supported timezone range.") from error

        start_text = start.strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, anime_id, anime_title, episode, action, source, details, created_at "
                "FROM watch_history WHERE created_at >= ? AND created_at < ? "
                "ORDER BY created_at DESC, id DESC",
                (start_text, end_text),
            ).fetchall()
        return [dict(row) for row in rows]

    def remove_watch_history(self, event_ids: Iterable[int]) -> int:
        ids = tuple(dict.fromkeys(event_ids))
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in ids):
            raise ValueError("Every watch-history ID must be a positive integer.")
        if not ids:
            return 0
        with self._connect() as connection:
            removed = 0
            for event_id in ids:
                cursor = connection.execute("DELETE FROM watch_history WHERE id = ?", (event_id,))
                removed += cursor.rowcount
        return removed

    def prune_watch_history(self, before_date: str) -> int:
        try:
            date.fromisoformat(before_date)
        except (TypeError, ValueError):
            raise ValueError("Prune date must use YYYY-MM-DD.") from None
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM watch_history WHERE date(created_at) < ?", (before_date,)
            )
            return cursor.rowcount

    def clear_watch_history(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM watch_history")
            return cursor.rowcount

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
