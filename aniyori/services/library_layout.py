"""Validated, persistent per-view library layout preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


LAYOUT_FORMAT = "aniyori-library-layout"
LAYOUT_VERSION = 1
COLUMNS = ("title", "status", "progress", "source", "airing")
DEFAULT_LAYOUTS = {
    "list": {
        "order": list(COLUMNS),
        "visible": list(COLUMNS),
        "widths": {"title": 300, "status": 100, "progress": 120, "source": 150, "airing": 170},
    },
    "grid": {
        "order": list(COLUMNS),
        "visible": list(COLUMNS),
        "widths": {"card_width": 220},
    },
}


class LibraryLayoutError(ValueError):
    """Raised when a saved library layout is invalid."""


def default_library_layout_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "library-layout.json"


def _normalize_layout(view: str, value) -> dict:
    if view not in DEFAULT_LAYOUTS:
        raise LibraryLayoutError("Unknown library view.")
    if not isinstance(value, dict):
        raise LibraryLayoutError("A library layout must be an object.")
    order = value.get("order")
    visible = value.get("visible")
    widths = value.get("widths")
    if (
        not isinstance(order, list)
        or len(order) != len(COLUMNS)
        or set(order) != set(COLUMNS)
        or not isinstance(visible, list)
        or not visible
        or len(set(visible)) != len(visible)
        or any(column not in COLUMNS for column in visible)
        or "title" not in visible
        or not isinstance(widths, dict)
    ):
        raise LibraryLayoutError("Library layout columns are invalid; the title column must remain visible.")
    if view == "list":
        if set(widths) != set(COLUMNS):
            raise LibraryLayoutError("List column widths must be defined for every column.")
        for column, width in widths.items():
            if isinstance(width, bool) or not isinstance(width, int) or not 80 <= width <= 500:
                raise LibraryLayoutError("List column widths must be between 80 and 500 pixels.")
    else:
        width = widths.get("card_width")
        if set(widths) != {"card_width"} or isinstance(width, bool) or not isinstance(width, int) or not 160 <= width <= 360:
            raise LibraryLayoutError("Grid card width must be between 160 and 360 pixels.")
    return {
        "order": list(order),
        "visible": list(visible),
        "widths": dict(widths),
    }


class LibraryLayoutStore:
    """Persist independent list and grid layouts atomically with private permissions."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_library_layout_path()

    def load_all(self) -> dict[str, dict]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {
                view: {
                    "order": list(layout["order"]),
                    "visible": list(layout["visible"]),
                    "widths": dict(layout["widths"]),
                }
                for view, layout in DEFAULT_LAYOUTS.items()
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LibraryLayoutError("Saved library layout is unreadable.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != LAYOUT_FORMAT
            or isinstance(payload.get("version"), bool)
            or payload.get("version") != LAYOUT_VERSION
            or not isinstance(payload.get("views"), dict)
            or set(payload["views"]) != set(DEFAULT_LAYOUTS)
        ):
            raise LibraryLayoutError("Saved library layout has an unsupported format.")
        return {
            view: _normalize_layout(view, payload["views"].get(view))
            for view in DEFAULT_LAYOUTS
        }

    def save(self, view: str, layout: dict) -> dict:
        normalized = _normalize_layout(view, layout)
        current = self.load_all()
        current[view] = normalized
        payload = {
            "format": LAYOUT_FORMAT,
            "version": LAYOUT_VERSION,
            "views": current,
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".library-layout-", delete=False,
            ) as stream:
                stream.write(content)
                temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return normalized

    def reset(self, view: str) -> dict:
        if view not in DEFAULT_LAYOUTS:
            raise LibraryLayoutError("Unknown library view.")
        return self.save(view, DEFAULT_LAYOUTS[view])
