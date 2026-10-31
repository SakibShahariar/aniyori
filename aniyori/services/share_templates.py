"""Safe, configurable share-message templates."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from string import Formatter
from typing import Mapping


TEMPLATE_FORMAT = "aniyori-share-template"
TEMPLATE_VERSION = 1
DEFAULT_SHARE_TEMPLATE = (
    "{title} — Episode {episode}/{total_episodes} "
    "({progress}%) · {status}"
)
ALLOWED_FIELDS = frozenset(
    {"title", "episode", "total_episodes", "progress", "status", "timestamp"}
)
_CONDITIONAL = re.compile(
    r"\[\[if\s+([a-z_][a-z0-9_]*)\]\](.*?)\[\[/if\]\]",
    re.DOTALL,
)
_FUNCTION = re.compile(
    r"\[\[(upper|lower|title|default):([a-z_][a-z0-9_]*)(?::([^\]]*))?\]\]"
)
_CONDITIONAL_MARKER = re.compile(r"\[\[/?if\b[^\]]*\]\]")


class ShareTemplateError(ValueError):
    """Raised when a share template is invalid or cannot be rendered."""


def _expand_conditionals(template: str, values: Mapping[str, object]) -> str:
    def replace(match):
        field, body = match.groups()
        if field not in ALLOWED_FIELDS:
            raise ShareTemplateError(f"Unknown conditional field: {field}")
        if "[[if " in body or "[[/if]]" in body:
            raise ShareTemplateError("Nested share-template conditionals are not supported.")
        value = values.get(field)
        return body if value not in (None, "", False) else ""

    expanded = _CONDITIONAL.sub(replace, template)
    if _CONDITIONAL_MARKER.search(expanded):
        raise ShareTemplateError("Unmatched conditional template marker.")
    return expanded


def validate_share_template(template: str) -> None:
    """Validate fields, conditionals, and supported formatting functions."""
    if not isinstance(template, str):
        raise ShareTemplateError("Share template must be text.")
    for match in _FUNCTION.finditer(template):
        if match.group(2) not in ALLOWED_FIELDS:
            raise ShareTemplateError(f"Unknown template field: {match.group(2)}")
    for match in _CONDITIONAL.finditer(template):
        if match.group(1) not in ALLOWED_FIELDS:
            raise ShareTemplateError(f"Unknown conditional field: {match.group(1)}")
        if "[[if " in match.group(2) or "[[/if]]" in match.group(2):
            raise ShareTemplateError("Nested share-template conditionals are not supported.")
    without_functions = _FUNCTION.sub("", template)
    without_conditionals = _CONDITIONAL.sub(lambda match: match.group(2), without_functions)
    if _CONDITIONAL_MARKER.search(without_conditionals):
        raise ShareTemplateError("Unmatched conditional template marker.")
    if "[[" in without_conditionals or "]]" in without_conditionals:
        raise ShareTemplateError("Invalid formatting function. Use upper, lower, title, or default.")
    try:
        for _literal, field, format_spec, conversion in Formatter().parse(
            without_conditionals
        ):
            if field is None:
                continue
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", field):
                raise ShareTemplateError(f"Invalid template field: {field}")
            if field not in ALLOWED_FIELDS:
                raise ShareTemplateError(f"Unknown template field: {field}")
            if conversion not in (None, "s", "r", "a"):
                raise ShareTemplateError(f"Unsupported conversion for {field}.")
            if "{" in format_spec or "}" in format_spec:
                raise ShareTemplateError("Nested format fields are not supported.")
    except ValueError as error:
        if isinstance(error, ShareTemplateError):
            raise
        raise ShareTemplateError(f"Malformed template: {error}") from error


def render_share_template(template: str, values: Mapping[str, object]) -> str:
    """Render a template without evaluating expressions or accessing attributes."""
    validate_share_template(template)
    expanded = _expand_conditionals(template, values)

    def apply_function(match):
        function, field, fallback = match.groups()
        value = values.get(field)
        if function == "default":
            return str(value) if value not in (None, "") else (fallback or "")
        if value in (None, ""):
            return ""
        rendered = str(value)
        if function == "upper":
            return rendered.upper()
        if function == "lower":
            return rendered.lower()
        return rendered.title()

    expanded = _FUNCTION.sub(apply_function, expanded)
    try:
        return expanded.format_map(
            {field: values.get(field) if values.get(field) is not None else ""
             for field in ALLOWED_FIELDS}
        )
    except (KeyError, ValueError, TypeError, IndexError) as error:
        raise ShareTemplateError(f"Could not render share template: {error}") from error


def share_context_for_entry(entry, *, now: datetime | None = None) -> dict[str, object]:
    """Build the supported share variables from a local library entry."""
    timestamp = now or datetime.now().astimezone()
    progress = (
        f"{entry.progress_fraction * 100:.0f}"
        if entry.progress_fraction is not None
        else ""
    )
    return {
        "title": entry.title,
        "episode": entry.episodes_watched,
        "total_episodes": entry.episodes_total if entry.episodes_total is not None else "",
        "progress": progress,
        "status": entry.status.value,
        "timestamp": timestamp.isoformat(timespec="minutes"),
    }


def default_share_template_path() -> Path:
    """Return the XDG configuration path without creating it."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "share-template.json"


class ShareTemplateStore:
    """Persist one validated share template using an atomic config-file update."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_share_template_path()

    def load(self) -> str:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return DEFAULT_SHARE_TEMPLATE
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ShareTemplateError("Saved share template configuration is invalid.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != TEMPLATE_FORMAT
            or payload.get("version") != TEMPLATE_VERSION
            or not isinstance(payload.get("template"), str)
        ):
            raise ShareTemplateError("Saved share template configuration is malformed.")
        validate_share_template(payload["template"])
        return payload["template"]

    def save(self, template: str) -> None:
        validate_share_template(template)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            {"format": TEMPLATE_FORMAT, "version": TEMPLATE_VERSION, "template": template},
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".share-template-", delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
