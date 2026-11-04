"""Persistent, validated rules for excluding local media from recognition."""

from __future__ import annotations

import fnmatch
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, Mapping

FORMAT = "aniyori-recognition-exclusions"
VERSION = 1
KINDS = frozenset({"folder", "filename", "title", "release_group"})


class RecognitionExclusionError(ValueError):
    """Raised when a recognition exclusion is invalid or cannot be loaded."""


def _validate_rule(rule: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(rule, Mapping):
        raise RecognitionExclusionError("Each exclusion must be an object.")
    kind, pattern = rule.get("kind"), rule.get("pattern")
    if not isinstance(kind, str) or kind not in KINDS:
        raise RecognitionExclusionError("Exclusion type must be folder, filename, title, or release_group.")
    if not isinstance(pattern, str) or not pattern.strip() or len(pattern) > 512:
        raise RecognitionExclusionError("Exclusion pattern must contain 1–512 characters.")
    pattern = pattern.strip()
    if kind == "folder":
        path = Path(pattern).expanduser()
        if not path.is_absolute():
            raise RecognitionExclusionError("Excluded folder paths must be absolute.")
        pattern = str(path.resolve(strict=False))
    elif kind == "filename" and ("/" in pattern or "\\" in pattern):
        raise RecognitionExclusionError("Filename exclusions must match a filename, not a path.")
    return {"kind": kind, "pattern": pattern}


def default_recognition_exclusions_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "recognition-exclusions.json"


class RecognitionExclusionStore:
    """Atomically persist folder, filename, title, and release-group exclusions."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_recognition_exclusions_path()

    def list_rules(self) -> tuple[dict[str, str], ...]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RecognitionExclusionError("Saved recognition exclusions are invalid.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != FORMAT
            or isinstance(payload.get("version"), bool)
            or not isinstance(payload.get("version"), int)
            or payload.get("version") != VERSION
            or not isinstance(payload.get("rules"), list)
        ):
            raise RecognitionExclusionError("Saved recognition exclusions have an unsupported format.")
        rules = []
        seen = set()
        for raw in payload["rules"]:
            rule = _validate_rule(raw)
            key = (rule["kind"], rule["pattern"].casefold())
            if key in seen:
                raise RecognitionExclusionError("Duplicate recognition exclusions are not allowed.")
            seen.add(key)
            rules.append(rule)
        return tuple(rules)

    def save_rules(self, rules: Iterable[Mapping[str, object]]) -> None:
        prepared = []
        seen = set()
        for raw in rules:
            rule = _validate_rule(raw)
            key = (rule["kind"], rule["pattern"].casefold())
            if key in seen:
                raise RecognitionExclusionError("Duplicate recognition exclusions are not allowed.")
            seen.add(key)
            prepared.append(rule)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"format": FORMAT, "version": VERSION, "rules": prepared},
            ensure_ascii=False, indent=2,
        ) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".recognition-exclusions-", delete=False,
            ) as temporary:
                os.chmod(temporary.name, 0o600)
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def exclusion_reason(
    path: str | Path,
    parsed,
    best_match,
    rules: Iterable[Mapping[str, str]],
) -> str | None:
    """Return the first matching exclusion explanation, if any."""
    path = Path(path)
    for rule in rules:
        kind, pattern = rule["kind"], rule["pattern"]
        if kind == "folder":
            excluded_root = Path(pattern)
            try:
                if path.resolve(strict=False).is_relative_to(excluded_root):
                    return f"Excluded folder: {pattern}"
            except OSError:
                continue
        elif kind == "filename" and fnmatch.fnmatchcase(path.name.casefold(), pattern.casefold()):
            return f"Excluded filename pattern: {pattern}"
        elif kind == "title":
            names = []
            if parsed is not None:
                names.append(parsed.title)
            if best_match is not None:
                names.append(best_match.title)
            if any(fnmatch.fnmatchcase(name.casefold(), pattern.casefold()) for name in names):
                return f"Excluded anime title: {pattern}"
        elif kind == "release_group" and parsed is not None:
            group = parsed.release_group or ""
            if fnmatch.fnmatchcase(group.casefold(), pattern.casefold()):
                return f"Excluded release group: {pattern}"
    return None
