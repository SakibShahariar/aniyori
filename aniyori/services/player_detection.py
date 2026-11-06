"""Opt-in MPRIS playback recognition helpers and settings."""

from __future__ import annotations

from dataclasses import dataclass
import math
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlsplit

from .matching import match_release_filename

PLAYER_BUS_PREFIXES = (
    "org.mpris.MediaPlayer2.mpv",
    "org.mpris.MediaPlayer2.vlc",
)
SETTINGS_FORMAT = "aniyori-player-detection"
SETTINGS_VERSION = 1
COMPLETION_THRESHOLD = 0.90


@dataclass(frozen=True, slots=True)
class PlayerDetectionSettings:
    enabled: bool = False


def default_player_detection_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "player-detection.json"


class PlayerDetectionSettingsStore:
    """Persist the user's explicit player-detection opt-in privately."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_player_detection_path()

    def load(self) -> PlayerDetectionSettings:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return PlayerDetectionSettings()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Saved player detection settings are unreadable.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != SETTINGS_FORMAT
            or isinstance(payload.get("version"), bool)
            or payload.get("version") != SETTINGS_VERSION
            or not isinstance(payload.get("enabled"), bool)
        ):
            raise ValueError("Saved player detection settings are invalid.")
        return PlayerDetectionSettings(payload["enabled"])

    def save(self, settings: PlayerDetectionSettings) -> PlayerDetectionSettings:
        if not isinstance(settings, PlayerDetectionSettings) or not isinstance(settings.enabled, bool):
            raise ValueError("Player detection settings must contain a boolean enabled value.")
        payload = {
            "format": SETTINGS_FORMAT,
            "version": SETTINGS_VERSION,
            "enabled": settings.enabled,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".player-detection-", delete=False,
            ) as stream:
                json.dump(payload, stream, indent=2)
                stream.write("\n")
                temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return settings


def supported_player_names(names) -> tuple[str, ...]:
    """Return only mpv and VLC MPRIS bus names, including named instances."""
    result = set()
    for name in names:
        if not isinstance(name, str):
            continue
        if any(name == prefix or name.startswith(prefix + ".") for prefix in PLAYER_BUS_PREFIXES):
            result.add(name)
    return tuple(sorted(result))


def local_media_path(uri: str) -> Path | None:
    """Accept only local file URIs; never inspect remote URLs or shares."""
    if not isinstance(uri, str) or not uri:
        return None
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "file"
        or parsed.netloc.casefold() not in {"", "localhost"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        path = Path(unquote(parsed.path))
    except (TypeError, ValueError):
        return None
    if not path.is_absolute() or not path.is_file():
        return None
    return path


def match_playback_file(uri: str, entries) -> tuple[int, int] | None:
    """Return (library ID, episode) only for a confident, unambiguous match."""
    path = local_media_path(uri)
    if path is None:
        return None
    candidates = [
        {"id": entry.storage_id, "title": entry.title}
        for entry in entries
        if isinstance(getattr(entry, "storage_id", None), int)
        and not isinstance(entry.storage_id, bool)
        and entry.storage_id > 0
    ]
    result = match_release_filename(
        path.name,
        candidates,
        minimum_score=0.90,
        ambiguity_margin=0.08,
    )
    best = result.decision.best_match
    if result.status != "matched" or best is None or result.parsed is None:
        return None
    if isinstance(best.media_id, bool) or not isinstance(best.media_id, int):
        return None
    episode = result.parsed.episode
    if episode <= 0:
        return None
    return best.media_id, episode


def playback_finished(position_us, duration_us, *, threshold: float = COMPLETION_THRESHOLD) -> bool:
    """Require a known duration and near-complete playback before updating progress."""
    if (
        isinstance(position_us, bool)
        or not isinstance(position_us, (int, float))
        or isinstance(duration_us, bool)
        or not isinstance(duration_us, (int, float))
        or isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(position_us)
        or not math.isfinite(duration_us)
        or not math.isfinite(threshold)
        or not 0.0 < threshold <= 1.0
        or position_us < 0
        or duration_us <= 0
    ):
        return False
    return position_us / duration_us >= threshold
