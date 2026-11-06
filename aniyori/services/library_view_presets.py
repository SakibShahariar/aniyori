"""Persistent named presets for supported library-view settings."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path

from .library_layout import (
    DEFAULT_LAYOUTS,
    LibraryLayoutError,
    _normalize_layout,
)
from .library_sort import SORT_MODES


PRESET_FORMAT = "aniyori-library-view-presets"
PRESET_VERSION = 1
FILTERS = frozenset(
    {"all", "watching", "planning", "completed", "paused", "dropped"}
)
VIEWS = frozenset(DEFAULT_LAYOUTS)
MAX_PRESETS = 100
MAX_NAME_LENGTH = 48


class LibraryViewPresetError(ValueError):
    """Raised when a library-view preset cannot be validated or saved."""


def default_library_view_presets_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "library-view-presets.json"


def _normalize_name(value: str) -> str:
    if not isinstance(value, str):
        raise LibraryViewPresetError("Preset names must be text.")
    name = value.strip()
    if (
        not name
        or len(name) > MAX_NAME_LENGTH
        or re.fullmatch(r"[\w -]+", name, flags=re.UNICODE) is None
    ):
        raise LibraryViewPresetError(
            f"Use 1–{MAX_NAME_LENGTH} letters, numbers, spaces, hyphens, or underscores."
        )
    return name


def _normalize_preset(value, *, tolerant: bool = False) -> dict:
    if not isinstance(value, dict):
        raise LibraryViewPresetError("A library-view preset must be an object.")

    filter_name = value.get("filter", "all")
    if filter_name not in FILTERS:
        if tolerant:
            filter_name = "all"
        else:
            raise LibraryViewPresetError("The preset uses an unsupported library filter.")

    sort_mode = value.get("sort", "title")
    if sort_mode not in SORT_MODES:
        if tolerant:
            sort_mode = "title"
        else:
            raise LibraryViewPresetError("The preset uses an unsupported sort mode.")

    view = value.get("view", "list")
    if view not in VIEWS:
        if tolerant:
            view = "list"
        else:
            raise LibraryViewPresetError("The preset uses an unsupported library view.")

    raw_layouts = value.get("layouts")
    layouts = {}
    for layout_view in DEFAULT_LAYOUTS:
        try:
            if not isinstance(raw_layouts, dict):
                raise LibraryLayoutError("Missing layouts.")
            layouts[layout_view] = _normalize_layout(
                layout_view, raw_layouts.get(layout_view)
            )
        except LibraryLayoutError as error:
            if not tolerant:
                raise LibraryViewPresetError(str(error)) from error
            layouts[layout_view] = copy.deepcopy(DEFAULT_LAYOUTS[layout_view])

    return {
        "filter": filter_name,
        "sort": sort_mode,
        "view": view,
        "layouts": layouts,
    }


class LibraryViewPresetStore:
    """Atomically persist named filter/sort/view/layout combinations."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_library_view_presets_path()

    def load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"presets": [], "default": None}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LibraryViewPresetError("Saved library-view presets are unreadable.") from error

        if (
            not isinstance(payload, dict)
            or payload.get("format") != PRESET_FORMAT
            or isinstance(payload.get("version"), bool)
            or payload.get("version") != PRESET_VERSION
            or not isinstance(payload.get("presets"), list)
        ):
            raise LibraryViewPresetError("Saved library-view presets have an unsupported format.")

        presets = []
        names = set()
        for item in payload["presets"][:MAX_PRESETS]:
            if not isinstance(item, dict):
                continue
            try:
                name = _normalize_name(item.get("name"))
                key = name.casefold()
                if key in names:
                    continue
                preset = _normalize_preset(item.get("settings"), tolerant=True)
            except LibraryViewPresetError:
                continue
            names.add(key)
            presets.append({"name": name, "settings": preset})

        default = payload.get("default")
        if not isinstance(default, str) or default.casefold() not in names:
            default = None
        else:
            default = next(
                item["name"] for item in presets
                if item["name"].casefold() == default.casefold()
            )
        return {"presets": presets, "default": default}

    def _write(self, state: dict) -> None:
        payload = {
            "format": PRESET_FORMAT,
            "version": PRESET_VERSION,
            "default": state["default"],
            "presets": state["presets"],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".library-view-presets-",
                delete=False,
            ) as stream:
                stream.write(content)
                temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def list_presets(self) -> tuple[str, ...]:
        state = self.load()
        return tuple(
            item["name"]
            for item in sorted(
                state["presets"], key=lambda item: item["name"].casefold()
            )
        )

    def get_preset(self, name: str) -> dict:
        key = _normalize_name(name).casefold()
        for item in self.load()["presets"]:
            if item["name"].casefold() == key:
                return copy.deepcopy(item["settings"])
        raise LibraryViewPresetError("The selected preset no longer exists.")

    def save_preset(self, name: str, settings: dict) -> str:
        normalized_name = _normalize_name(name)
        normalized_settings = _normalize_preset(settings)
        state = self.load()
        if any(
            item["name"].casefold() == normalized_name.casefold()
            for item in state["presets"]
        ):
            raise LibraryViewPresetError("A preset with that name already exists.")
        if len(state["presets"]) >= MAX_PRESETS:
            raise LibraryViewPresetError(f"You can save up to {MAX_PRESETS} presets.")
        state["presets"].append({
            "name": normalized_name,
            "settings": normalized_settings,
        })
        self._write(state)
        return normalized_name

    def rename_preset(self, old_name: str, new_name: str) -> str:
        old_key = _normalize_name(old_name).casefold()
        normalized_name = _normalize_name(new_name)
        state = self.load()
        target = next(
            (item for item in state["presets"] if item["name"].casefold() == old_key),
            None,
        )
        if target is None:
            raise LibraryViewPresetError("The selected preset no longer exists.")
        if any(
            item is not target
            and item["name"].casefold() == normalized_name.casefold()
            for item in state["presets"]
        ):
            raise LibraryViewPresetError("A preset with that name already exists.")
        target["name"] = normalized_name
        if state["default"] and state["default"].casefold() == old_key:
            state["default"] = normalized_name
        self._write(state)
        return normalized_name

    def duplicate_preset(self, source_name: str, new_name: str) -> str:
        settings = self.get_preset(source_name)
        return self.save_preset(new_name, settings)

    def delete_preset(self, name: str) -> bool:
        key = _normalize_name(name).casefold()
        state = self.load()
        remaining = [
            item for item in state["presets"]
            if item["name"].casefold() != key
        ]
        if len(remaining) == len(state["presets"]):
            return False
        state["presets"] = remaining
        if state["default"] and state["default"].casefold() == key:
            state["default"] = None
        self._write(state)
        return True

    def set_default(self, name: str | None) -> str | None:
        state = self.load()
        if name is None:
            state["default"] = None
        else:
            key = _normalize_name(name).casefold()
            match = next(
                (item["name"] for item in state["presets"] if item["name"].casefold() == key),
                None,
            )
            if match is None:
                raise LibraryViewPresetError("The selected preset no longer exists.")
            state["default"] = match
        self._write(state)
        return state["default"]
