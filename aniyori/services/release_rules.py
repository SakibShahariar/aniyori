"""Ordered, persistent rules for classifying incoming anime releases."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile
import uuid
from typing import Any


RULE_FORMAT = "aniyori-release-rules"
RULE_VERSION = 1
RULE_FIELDS = ("title", "release_group", "resolution", "source", "episode", "keywords")
RULE_ACTIONS = ("include", "exclude", "prefer")


class ReleaseRuleError(ValueError):
    """Raised when a saved or user-supplied release rule is invalid."""


@dataclass(frozen=True, slots=True)
class ReleaseRule:
    """One ordered match rule for a release attribute."""

    rule_id: str
    name: str
    field: str
    value: str
    action: str
    priority: int = 0
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ReleaseRuleDecision:
    """The first matching rule and its user-readable classification."""

    status: str
    rule_id: str | None = None
    rule_name: str | None = None
    reason: str | None = None


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseRuleError(f"Saved release rules contain duplicate key: {key}.")
        result[key] = value
    return result


def _validate_rule(rule: ReleaseRule) -> ReleaseRule:
    if not isinstance(rule, ReleaseRule):
        raise ReleaseRuleError("Rules must be ReleaseRule values.")
    for field, value, limit in (
        ("rule_id", rule.rule_id, 64),
        ("name", rule.name, 80),
        ("value", rule.value, 200),
    ):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ReleaseRuleError(f"Rule {field.replace('_', ' ')} must be non-empty text (max {limit} characters).")
    if rule.field not in RULE_FIELDS:
        raise ReleaseRuleError("Unsupported release rule field.")
    if rule.action not in RULE_ACTIONS:
        raise ReleaseRuleError("Unsupported release rule action.")
    if isinstance(rule.priority, bool) or not isinstance(rule.priority, int) or rule.priority < 0:
        raise ReleaseRuleError("Rule priority must be a nonnegative integer.")
    if not isinstance(rule.enabled, bool):
        raise ReleaseRuleError("Rule enabled state must be a boolean.")
    value = rule.value.strip()
    if rule.field == "episode":
        if not value.isdecimal() or int(value) <= 0:
            raise ReleaseRuleError("Episode rules must use a positive whole number.")
        value = str(int(value))
    return replace(
        rule, rule_id=rule.rule_id.strip(), name=rule.name.strip(),
        value=value,
    )


def normalize_release_rules(rules: Iterable[ReleaseRule]) -> tuple[ReleaseRule, ...]:
    """Validate rules, reject duplicate IDs, and order them by priority."""
    if isinstance(rules, (str, bytes)):
        raise ReleaseRuleError("Rules must be an iterable of rule values.")
    normalized = tuple(_validate_rule(rule) for rule in rules)
    ids = [rule.rule_id for rule in normalized]
    if len(ids) != len(set(ids)):
        raise ReleaseRuleError("Release rule IDs must be unique.")
    return tuple(sorted(normalized, key=lambda rule: (rule.priority, rule.rule_id)))


def _matches(rule: ReleaseRule, release: Mapping[str, Any]) -> bool:
    if rule.field == "keywords":
        values = (
            release.get("title", ""),
            release.get("release_group", ""),
            release.get("resolution", ""),
            release.get("source", ""),
            release.get("summary", ""),
            *release.get("categories", ()),
        )
        haystack = " ".join(str(value) for value in values if value is not None).casefold()
        return rule.value.casefold() in haystack
    raw = release.get(rule.field)
    if raw is None:
        return False
    if rule.field == "episode":
        try:
            return int(raw) == int(rule.value)
        except (TypeError, ValueError, OverflowError):
            return False
    return rule.value.casefold() in str(raw).casefold()


def evaluate_release_rules(
    release: Mapping[str, Any],
    rules: Iterable[ReleaseRule],
) -> ReleaseRuleDecision:
    """Apply enabled rules in order; the first match determines the outcome."""
    if not isinstance(release, Mapping):
        raise ReleaseRuleError("Release metadata must be an object.")
    normalized = normalize_release_rules(rules)
    for rule in normalized:
        if not rule.enabled or not _matches(rule, release):
            continue
        status = {
            "include": "wanted",
            "exclude": "discarded",
            "prefer": "preferred",
        }[rule.action]
        return ReleaseRuleDecision(
            status=status,
            rule_id=rule.rule_id,
            rule_name=rule.name,
            reason=f"{status.title()} by rule “{rule.name}” ({rule.field}: {rule.value}).",
        )
    return ReleaseRuleDecision(status="unmatched")


def default_release_rules_path() -> Path:
    """Return the XDG configuration path without creating it."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "release-rules.json"


class ReleaseRuleStore:
    """Persist validated, ordered release rules atomically."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_release_rules_path()

    def load(self) -> tuple[ReleaseRule, ...]:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        try:
            payload = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
        except ReleaseRuleError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReleaseRuleError("Saved release rules are invalid JSON.") from error
        version = payload.get("version") if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get("format") != RULE_FORMAT
            or isinstance(version, bool)
            or not isinstance(version, int)
            or version != RULE_VERSION
            or not isinstance(payload.get("rules"), list)
        ):
            raise ReleaseRuleError("Saved release rules have an unsupported format.")
        rules = []
        for item in payload["rules"]:
            if not isinstance(item, dict):
                raise ReleaseRuleError("Saved release rules must be objects.")
            try:
                rules.append(ReleaseRule(**item))
            except TypeError as error:
                raise ReleaseRuleError("Saved release rule fields are invalid.") from error
        return normalize_release_rules(rules)

    def save(self, rules: Iterable[ReleaseRule]) -> tuple[ReleaseRule, ...]:
        normalized = normalize_release_rules(rules)
        payload = {
            "format": RULE_FORMAT,
            "version": RULE_VERSION,
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "field": rule.field,
                    "value": rule.value,
                    "action": rule.action,
                    "priority": rule.priority,
                    "enabled": rule.enabled,
                }
                for rule in normalized
            ],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".release-rules-", delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return normalized

    def add(
        self, name: str, field: str, value: str, action: str,
        *, enabled: bool = True,
    ) -> tuple[ReleaseRule, ...]:
        rules = self.load()
        priority = max((rule.priority for rule in rules), default=-1) + 1
        rule = ReleaseRule(uuid.uuid4().hex, name, field, value, action, priority, enabled)
        return self.save((*rules, rule))

    def update(self, rule_id: str, **changes: Any) -> tuple[ReleaseRule, ...]:
        allowed = {"name", "field", "value", "action", "priority", "enabled"}
        if set(changes) - allowed:
            raise ReleaseRuleError("Unsupported release rule update field.")
        rules = list(self.load())
        index = next((i for i, rule in enumerate(rules) if rule.rule_id == rule_id), None)
        if index is None:
            raise ReleaseRuleError("The release rule was not found.")
        rules[index] = replace(rules[index], **changes)
        return self.save(rules)

    def remove(self, rule_id: str) -> tuple[ReleaseRule, ...]:
        rules = list(self.load())
        remaining = [rule for rule in rules if rule.rule_id != rule_id]
        if len(remaining) == len(rules):
            raise ReleaseRuleError("The release rule was not found.")
        return self.save(remaining)

    def reorder(self, rule_ids: Iterable[str]) -> tuple[ReleaseRule, ...]:
        current = self.load()
        requested = tuple(rule_ids)
        by_id = {rule.rule_id: rule for rule in current}
        if len(requested) != len(by_id) or set(requested) != set(by_id):
            raise ReleaseRuleError("Reordering must include every configured rule exactly once.")
        return self.save(replace(by_id[rule_id], priority=index) for index, rule_id in enumerate(requested))
