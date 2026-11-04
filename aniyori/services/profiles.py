"""Portable storage roots and isolated named application profiles."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


PROFILE_FORMAT = "aniyori-profiles"
PROFILE_VERSION = 1
_PROFILE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ProfileError(ValueError):
    """Raised when a profile registry or operation is invalid."""


@dataclass(frozen=True, slots=True)
class Profile:
    profile_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ProfileContext:
    portable: bool
    portable_directory: Path | None
    active_profile: str
    active_name: str
    registry_path: Path
    data_home: Path
    config_home: Path
    cache_home: Path


def _absolute_home(env: dict, key: str, fallback: Path) -> Path:
    raw = env.get(key)
    path = Path(raw).expanduser() if raw else fallback
    return path if path.is_absolute() else fallback


def _default_registry(env: dict) -> Path:
    config_home = _absolute_home(env, "XDG_CONFIG_HOME", Path.home() / ".config")
    return config_home / "aniyori" / "profiles.json"


def configure_storage_environment(
    *, app_directory: str | Path | None = None, environ=None
) -> ProfileContext:
    """Set XDG roots before importing services so the selected profile is isolated.

    Portable mode is enabled by a .aniyori-portable marker beside the application,
    or by ANIYORI_PORTABLE_DIR. Its data/config/cache roots live beside the app.
    The default profile deliberately keeps the standard XDG paths for compatibility.
    """
    env = os.environ if environ is None else environ
    home = Path(env.get("HOME") or Path.home()).expanduser()
    data_home = _absolute_home(env, "XDG_DATA_HOME", home / ".local" / "share")
    config_home = _absolute_home(env, "XDG_CONFIG_HOME", home / ".config")
    cache_home = _absolute_home(env, "XDG_CACHE_HOME", home / ".cache")
    app_dir = Path(app_directory).resolve() if app_directory else Path(__file__).resolve().parents[2]
    marker = app_dir / ".aniyori-portable"
    portable_override = env.get("ANIYORI_PORTABLE_DIR")
    portable = marker.is_file() or bool(portable_override)
    portable_directory = None
    if portable:
        portable_directory = (
            Path(portable_override).expanduser().resolve()
            if portable_override else (app_dir / "portable-data").resolve()
        )
        if not portable_directory.is_absolute():
            raise ProfileError("Portable data directory must be an absolute path.")
        data_home = portable_directory / "data"
        config_home = portable_directory / "config"
        cache_home = portable_directory / "cache"
        try:
            for root in (data_home, config_home, cache_home):
                root.mkdir(parents=True, exist_ok=True)
                probe = root / ".aniyori-write-test"
                probe.touch(exist_ok=True)
                probe.unlink(missing_ok=True)
        except OSError as error:
            raise ProfileError(
                "Portable mode requires a writable directory beside the application."
            ) from error

    registry_path = config_home / "aniyori" / "profiles.json"
    env["ANIYORI_PROFILE_REGISTRY"] = str(registry_path)
    env["ANIYORI_BASE_DATA_HOME"] = str(data_home)
    env["ANIYORI_BASE_CONFIG_HOME"] = str(config_home)
    env["ANIYORI_BASE_CACHE_HOME"] = str(cache_home)
    env["ANIYORI_PORTABLE_MODE"] = "1" if portable else "0"

    store = ProfileStore(registry_path, environ=env)
    profiles, active_id = store._read()
    selected = next(item for item in profiles if item.profile_id == active_id)
    if active_id != "default":
        data_home = data_home / "profiles" / active_id
        config_home = config_home / "profiles" / active_id
        cache_home = cache_home / "profiles" / active_id
    env["XDG_DATA_HOME"] = str(data_home)
    env["XDG_CONFIG_HOME"] = str(config_home)
    env["XDG_CACHE_HOME"] = str(cache_home)
    return ProfileContext(
        portable, portable_directory, active_id, selected.name, registry_path,
        data_home, config_home, cache_home,
    )


class ProfileStore:
    """Manage profile names and active selection in a registry outside profile data."""

    def __init__(self, path: str | Path | None = None, *, environ=None):
        self.environ = os.environ if environ is None else environ
        self.path = Path(path) if path is not None else Path(
            self.environ.get("ANIYORI_PROFILE_REGISTRY") or _default_registry(self.environ)
        )

    def _read(self) -> tuple[tuple[Profile, ...], str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return (Profile("default", "Default"),), "default"
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProfileError("The saved profile registry is unreadable.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != PROFILE_FORMAT
            or isinstance(payload.get("version"), bool)
            or payload.get("version") != PROFILE_VERSION
            or not isinstance(payload.get("profiles"), list)
            or not isinstance(payload.get("active"), str)
        ):
            raise ProfileError("The saved profile registry has an unsupported format.")
        profiles = []
        seen_ids = set()
        seen_names = set()
        for item in payload["profiles"]:
            if not isinstance(item, dict):
                raise ProfileError("Saved profiles must be objects.")
            profile_id, name = item.get("id"), item.get("name")
            if (
                not isinstance(profile_id, str) or not _PROFILE_ID.fullmatch(profile_id)
                or not isinstance(name, str) or not name.strip() or len(name.strip()) > 40
            ):
                raise ProfileError("A saved profile has an invalid ID or name.")
            if profile_id in seen_ids or name.casefold() in seen_names:
                raise ProfileError("Profile IDs and names must be unique.")
            profiles.append(Profile(profile_id, name.strip()))
            seen_ids.add(profile_id)
            seen_names.add(name.casefold())
        if not profiles or "default" not in seen_ids or payload["active"] not in seen_ids:
            raise ProfileError("The profile registry must contain an active Default profile.")
        return tuple(profiles), payload["active"]

    def _write(self, profiles: tuple[Profile, ...], active: str) -> None:
        payload = {
            "format": PROFILE_FORMAT,
            "version": PROFILE_VERSION,
            "active": active,
            "profiles": [{"id": item.profile_id, "name": item.name} for item in profiles],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".profiles-", delete=False,
            ) as stream:
                stream.write(content)
                temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def list_profiles(self) -> tuple[Profile, ...]:
        return self._read()[0]

    def active_profile(self) -> Profile:
        profiles, active = self._read()
        return next(item for item in profiles if item.profile_id == active)

    def create(self, name: str) -> Profile:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,39}", name.strip()):
            raise ProfileError("Profile names must be 1–40 letters, numbers, spaces, '_' or '-'.")
        profiles, active = self._read()
        if any(item.name.casefold() == name.strip().casefold() for item in profiles):
            raise ProfileError("A profile with this name already exists.")
        slug = re.sub(r"[^a-z0-9]+", "-", name.strip().casefold()).strip("-")
        profile_id = slug
        suffix = 2
        ids = {item.profile_id for item in profiles}
        while profile_id in ids:
            profile_id = slug + "-" + str(suffix)
            suffix += 1
        created = Profile(profile_id, name.strip())
        self._write((*profiles, created), active)
        return created

    def switch(self, profile_id: str) -> Profile:
        profiles, _active = self._read()
        selected = next((item for item in profiles if item.profile_id == profile_id), None)
        if selected is None:
            raise ProfileError("The selected profile does not exist.")
        self._write(profiles, selected.profile_id)
        return selected

    def remove(self, profile_id: str) -> tuple[Profile, ...]:
        profiles, active = self._read()
        if profile_id == "default":
            raise ProfileError("The Default profile cannot be removed.")
        if not any(item.profile_id == profile_id for item in profiles):
            raise ProfileError("The selected profile does not exist.")
        updated = tuple(item for item in profiles if item.profile_id != profile_id)
        next_active = "default" if active == profile_id else active
        self._write(updated, next_active)
        roots = (
            Path(self.environ.get("ANIYORI_BASE_DATA_HOME", Path.home() / ".local/share")),
            Path(self.environ.get("ANIYORI_BASE_CONFIG_HOME", Path.home() / ".config")),
            Path(self.environ.get("ANIYORI_BASE_CACHE_HOME", Path.home() / ".cache")),
        )
        for root in roots:
            parent = root / "profiles"
            target = parent / profile_id
            if target.is_symlink():
                target.unlink(missing_ok=True)
            elif target.exists():
                if target.resolve().parent != parent.resolve():
                    raise ProfileError("Refusing to remove a profile directory outside its profile root.")
                shutil.rmtree(target)
        return updated
