"""Helpers for resolving the system's local timezone with DST rules."""

from __future__ import annotations

import os
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_local_timezone() -> tzinfo:
    """Return the system timezone, preserving historical daylight-saving rules."""
    localtime = Path("/etc/localtime")
    try:
        with localtime.open("rb") as stream:
            return ZoneInfo.from_file(stream)
    except (OSError, ValueError):
        pass

    configured_zone = os.environ.get("TZ", "").lstrip(":")
    if configured_zone:
        try:
            return ZoneInfo(configured_zone)
        except (KeyError, OSError, ZoneInfoNotFoundError, ValueError):
            pass

    return datetime.now().astimezone().tzinfo or timezone.utc
