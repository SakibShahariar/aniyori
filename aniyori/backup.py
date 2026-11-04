"""Validated full local-data backup and restore for Aniyori."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

BACKUP_FORMAT = "aniyori-full-backup"
BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 256 * 1024 * 1024


class BackupError(ValueError):
    """Raised when a backup cannot be created or safely restored."""


def default_config_dir() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def create_backup(
    database_path: str | Path,
    config_dir: str | Path,
    destination: str | Path,
) -> Path:
    """Write a consistent SQLite snapshot and regular config files to a ZIP."""
    database_path = Path(database_path)
    config_dir = Path(config_dir)
    destination = Path(destination)
    if not database_path.is_file():
        raise BackupError("The Aniyori library database does not exist.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    contents: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".aniyori-backup-") as temp_dir:
        snapshot = Path(temp_dir) / "library.sqlite3"
        try:
            source = sqlite3.connect(database_path)
            target = sqlite3.connect(snapshot)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            contents["library.sqlite3"] = snapshot.read_bytes()
        except sqlite3.Error as error:
            raise BackupError(f"Could not snapshot the library database: {error}") from error

        if config_dir.exists():
            for path in sorted(config_dir.rglob("*")):
                if path.is_symlink() or not path.is_file():
                    continue
                relative = path.relative_to(config_dir).as_posix()
                if not relative or relative.startswith("../"):
                    continue
                try:
                    contents[f"config/{relative}"] = path.read_bytes()
                except OSError as error:
                    raise BackupError(f"Could not read configuration file {relative}: {error}") from error

        total = sum(len(content) for content in contents.values())
        if total > MAX_BACKUP_BYTES:
            raise BackupError("The backup exceeds the 256 MiB safety limit.")
        manifest = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "files": {name: _sha256(content) for name, content in sorted(contents.items())},
        }
        contents["manifest.json"] = (
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")

        temporary_archive = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=".aniyori-backup-",
                suffix=".zip", delete=False,
            ) as temporary:
                temporary_archive = Path(temporary.name)
            os.chmod(temporary_archive, 0o600)
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in contents.items():
                    archive.writestr(name, content)
            os.replace(temporary_archive, destination)
            os.chmod(destination, 0o600)
        except (OSError, zipfile.BadZipFile) as error:
            raise BackupError(f"Could not write the backup archive: {error}") from error
        finally:
            if temporary_archive is not None:
                temporary_archive.unlink(missing_ok=True)
    return destination


def _read_backup(archive_path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise BackupError("The backup contains duplicate file paths.")
            total = 0
            contents = {}
            for info in infos:
                path = PurePosixPath(info.filename)
                if (
                    path.is_absolute()
                    or not path.parts
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or "\\" in info.filename
                    or info.is_dir()
                    or info.flag_bits & 0x1
                ):
                    raise BackupError("The backup contains an unsafe file path or entry.")
                if info.file_size > MAX_BACKUP_BYTES:
                    raise BackupError("A backup file exceeds the safety limit.")
                total += info.file_size
                if total > MAX_BACKUP_BYTES:
                    raise BackupError("The backup exceeds the 256 MiB safety limit.")
                if info.filename != "manifest.json" and (
                    info.filename != "library.sqlite3"
                    and not info.filename.startswith("config/")
                ):
                    raise BackupError("The backup contains an unexpected file.")
                contents[info.filename] = archive.read(info)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, BackupError):
            raise
        raise BackupError("The selected file is not a valid Aniyori backup.") from error

    try:
        manifest = json.loads(contents.pop("manifest.json"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupError("The backup manifest is missing or invalid.") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != BACKUP_FORMAT
        or isinstance(manifest.get("version"), bool)
        or not isinstance(manifest.get("version"), int)
        or manifest.get("version") != BACKUP_VERSION
        or not isinstance(manifest.get("files"), dict)
        or "library.sqlite3" not in contents
        or set(manifest["files"]) != set(contents)
    ):
        raise BackupError("The backup format or file manifest is unsupported.")
    for name, content in contents.items():
        if manifest["files"].get(name) != _sha256(content):
            raise BackupError(f"Backup integrity check failed for {name}.")
    return contents


def restore_backup(
    archive_path: str | Path,
    database_path: str | Path,
    config_dir: str | Path,
) -> None:
    """Validate and stage every file before replacing the database/config tree."""
    contents = _read_backup(Path(archive_path))
    database_path = Path(database_path)
    config_dir = Path(config_dir)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config_dir.parent.mkdir(parents=True, exist_ok=True)

    db_stage_dir = Path(tempfile.mkdtemp(dir=database_path.parent, prefix=".aniyori-restore-db-"))
    config_stage_dir = Path(tempfile.mkdtemp(dir=config_dir.parent, prefix=".aniyori-restore-config-"))
    db_stage = db_stage_dir / database_path.name
    config_stage = config_stage_dir / config_dir.name
    config_stage.mkdir()
    db_backup = database_path.with_name(f".{database_path.name}.restore-backup")
    config_backup = config_dir.with_name(f".{config_dir.name}.restore-backup")
    db_moved = config_moved = db_installed = config_installed = False
    try:
        db_stage.write_bytes(contents["library.sqlite3"])
        os.chmod(db_stage, 0o600)
        try:
            connection = sqlite3.connect(db_stage)
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()
            finally:
                connection.close()
            if not result or result[0] != "ok":
                raise BackupError("The backup database failed SQLite integrity validation.")
        except sqlite3.Error as error:
            raise BackupError("The backup does not contain a valid SQLite database.") from error

        for name, content in contents.items():
            if name == "library.sqlite3":
                continue
            relative = PurePosixPath(name).relative_to("config")
            target = config_stage.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            os.chmod(target, 0o600)

        if db_backup.exists() or config_backup.exists():
            raise BackupError("A previous restore recovery file exists; inspect it before restoring.")
        if database_path.exists():
            os.replace(database_path, db_backup)
            db_moved = True
        if config_dir.exists():
            os.replace(config_dir, config_backup)
            config_moved = True
        os.replace(db_stage, database_path)
        db_installed = True
        os.replace(config_stage, config_dir)
        config_installed = True
    except Exception:
        if config_installed and config_dir.exists():
            shutil.rmtree(config_dir)
        if db_installed and database_path.exists():
            database_path.unlink(missing_ok=True)
        if config_moved and config_backup.exists():
            os.replace(config_backup, config_dir)
        if db_moved and db_backup.exists():
            os.replace(db_backup, database_path)
        raise
    else:
        if db_moved:
            try:
                db_backup.unlink(missing_ok=True)
            except OSError:
                pass
        if config_moved:
            shutil.rmtree(config_backup, ignore_errors=True)
    finally:
        shutil.rmtree(db_stage_dir, ignore_errors=True)
        shutil.rmtree(config_stage_dir, ignore_errors=True)
