"""Persistent in-app notifications, deduplication, and user preferences."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid
from typing import Iterable


NOTIFICATION_FORMAT = "aniyori-notifications"
NOTIFICATION_VERSION = 1
MAX_NOTIFICATIONS = 1000
EVENT_TYPES = ("release_match", "download_failure", "webhook_error", "backup")
SEVERITIES = ("info", "warning", "error")


class NotificationError(ValueError):
    """Raised when notification data or preferences are invalid."""


@dataclass(frozen=True, slots=True)
class Notification:
    notification_id: str
    event_type: str
    severity: str
    title: str
    message: str
    created_at: str
    dedupe_key: str | None = None
    dismissed: bool = False


@dataclass(frozen=True, slots=True)
class NotificationPreferences:
    enabled_events: tuple[str, ...] = EVENT_TYPES
    desktop_notifications: bool = False
    minimum_severity: str = "info"


def default_notification_path() -> Path:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    return config_home / "aniyori" / "notifications.json"


def _normalize_notification(item: Notification) -> Notification:
    if not isinstance(item, Notification):
        raise NotificationError("Notification entries must be Notification values.")
    if not isinstance(item.notification_id, str) or not item.notification_id:
        raise NotificationError("Notification IDs must be non-empty text.")
    if item.event_type not in EVENT_TYPES:
        raise NotificationError("Unknown notification event type.")
    if item.severity not in SEVERITIES:
        raise NotificationError("Unknown notification severity.")
    if not isinstance(item.title, str) or not item.title.strip() or len(item.title) > 160:
        raise NotificationError("Notification titles must contain 1–160 characters.")
    if not isinstance(item.message, str) or len(item.message) > 2000:
        raise NotificationError("Notification messages must contain at most 2,000 characters.")
    if not isinstance(item.created_at, str):
        raise NotificationError("Notification timestamps must be ISO-8601 text.")
    try:
        datetime.fromisoformat(item.created_at)
    except ValueError as error:
        raise NotificationError("Notification timestamp must be ISO-8601.") from error
    if item.dedupe_key is not None and (
        not isinstance(item.dedupe_key, str) or not item.dedupe_key or len(item.dedupe_key) > 512
    ):
        raise NotificationError("Notification deduplication keys must contain 1–512 characters.")
    if not isinstance(item.dismissed, bool):
        raise NotificationError("Notification dismissed state must be a boolean.")
    return Notification(
        item.notification_id, item.event_type, item.severity, item.title.strip(),
        item.message, item.created_at, item.dedupe_key, item.dismissed,
    )


class NotificationStore:
    """Atomically persist bounded notification history and event preferences."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_notification_path()

    def _read(self):
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return [], NotificationPreferences()
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NotificationError("Saved notifications are invalid JSON.") from error
        if (
            not isinstance(payload, dict)
            or payload.get("format") != NOTIFICATION_FORMAT
            or isinstance(payload.get("version"), bool)
            or payload.get("version") != NOTIFICATION_VERSION
            or not isinstance(payload.get("notifications"), list)
            or not isinstance(payload.get("preferences"), dict)
        ):
            raise NotificationError("Saved notifications have an unsupported format.")
        raw_preferences = payload["preferences"]
        enabled = raw_preferences.get("enabled_events")
        desktop = raw_preferences.get("desktop_notifications")
        minimum_severity = raw_preferences.get("minimum_severity", "info")
        if (
            not isinstance(enabled, list)
            or any(value not in EVENT_TYPES for value in enabled)
            or len(set(enabled)) != len(enabled)
            or not isinstance(desktop, bool)
            or minimum_severity not in SEVERITIES
        ):
            raise NotificationError("Saved notification preferences are invalid.")
        preferences = NotificationPreferences(tuple(enabled), desktop, minimum_severity)
        notifications = []
        seen_ids = set()
        for raw_item in payload["notifications"]:
            if not isinstance(raw_item, dict):
                raise NotificationError("Saved notification entries must be objects.")
            try:
                item = _normalize_notification(Notification(**raw_item))
            except TypeError as error:
                raise NotificationError("Saved notification entry has invalid fields.") from error
            if item.notification_id in seen_ids:
                raise NotificationError("Saved notification IDs must be unique.")
            seen_ids.add(item.notification_id)
            notifications.append(item)
        if len(notifications) > MAX_NOTIFICATIONS:
            notifications = notifications[-MAX_NOTIFICATIONS:]
        return notifications, preferences

    def _write(self, notifications, preferences):
        payload = {
            "format": NOTIFICATION_FORMAT,
            "version": NOTIFICATION_VERSION,
            "preferences": {
                "enabled_events": list(preferences.enabled_events),
                "desktop_notifications": preferences.desktop_notifications,
                "minimum_severity": preferences.minimum_severity,
            },
            "notifications": [asdict(item) for item in notifications[-MAX_NOTIFICATIONS:]],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".notifications-", delete=False,
            ) as stream:
                stream.write(content)
                temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def preferences(self) -> NotificationPreferences:
        return self._read()[1]

    def save_preferences(self, preferences: NotificationPreferences) -> NotificationPreferences:
        if not isinstance(preferences, NotificationPreferences):
            raise NotificationError("Preferences must be NotificationPreferences.")
        if (
            not isinstance(preferences.enabled_events, tuple)
            or any(value not in EVENT_TYPES for value in preferences.enabled_events)
            or len(set(preferences.enabled_events)) != len(preferences.enabled_events)
            or not isinstance(preferences.desktop_notifications, bool)
            or preferences.minimum_severity not in SEVERITIES
        ):
            raise NotificationError("Notification preferences contain invalid values.")
        notifications, _previous = self._read()
        self._write(notifications, preferences)
        return preferences

    def add(
        self, event_type: str, severity: str, title: str, message: str,
        *, dedupe_key: str | None = None, created_at: str | None = None,
    ) -> Notification | None:
        notifications, preferences = self._read()
        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        item = _normalize_notification(Notification(
            uuid.uuid4().hex, event_type, severity, title, message,
            timestamp, dedupe_key, False,
        ))
        if event_type not in preferences.enabled_events:
            return None
        if SEVERITIES.index(item.severity) < SEVERITIES.index(preferences.minimum_severity):
            return None
        if dedupe_key is not None and any(
            existing.dedupe_key == dedupe_key for existing in notifications
        ):
            return None
        notifications.append(item)
        self._write(notifications, preferences)
        return item

    def list(self, *, include_dismissed: bool = True, limit: int = 200) -> tuple[Notification, ...]:
        if not isinstance(include_dismissed, bool):
            raise NotificationError("include_dismissed must be a boolean.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_NOTIFICATIONS:
            raise NotificationError(f"Notification limit must be between 1 and {MAX_NOTIFICATIONS}.")
        notifications, _preferences = self._read()
        if not include_dismissed:
            notifications = [item for item in notifications if not item.dismissed]
        return tuple(reversed(notifications[-limit:]))

    def dismiss(self, notification_ids: Iterable[str]) -> int:
        ids = tuple(dict.fromkeys(notification_ids))
        if any(not isinstance(value, str) or not value for value in ids):
            raise NotificationError("Notification IDs must be non-empty text.")
        notifications, preferences = self._read()
        found = set()
        updated = []
        for item in notifications:
            if item.notification_id in ids and not item.dismissed:
                item = Notification(
                    item.notification_id, item.event_type, item.severity,
                    item.title, item.message, item.created_at, item.dedupe_key, True,
                )
                found.add(item.notification_id)
            updated.append(item)
        self._write(updated, preferences)
        return len(found)

    def clear_dismissed(self) -> int:
        notifications, preferences = self._read()
        updated = [item for item in notifications if not item.dismissed]
        removed = len(notifications) - len(updated)
        self._write(updated, preferences)
        return removed
