"""Validated JSON and CSV import/export for local library entries."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping

from .models import AnimeEntry, WatchStatus


JSON_FORMAT_VERSION = 1
CSV_FIELDS = (
    "title",
    "episodes_total",
    "episodes_watched",
    "status",
    "provider",
    "provider_id",
    "cover_image",
)


def _entry_to_record(entry: AnimeEntry) -> dict[str, object]:
    return {
        "title": entry.title,
        "episodes_total": entry.episodes_total,
        "episodes_watched": entry.episodes_watched,
        "status": entry.status.value,
        "provider": entry.provider,
        "provider_id": entry.provider_id,
        "cover_image": entry.cover_image,
    }


def _record_to_entry(record: Mapping[str, object]) -> AnimeEntry:
    title = record.get("title")
    if not isinstance(title, str):
        raise ValueError("Each imported anime must have a text title.")

    def optional_text(field: str) -> str | None:
        value = record.get(field)
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError(f"Imported {field.replace('_', ' ')} must be text.")
        return value

    def optional_count(field: str) -> int | None:
        value = record.get(field)
        if value is None or value == "":
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Imported {field.replace('_', ' ')} must be a whole number.")
        return value

    total = optional_count("episodes_total")
    watched = optional_count("episodes_watched")
    if watched is None:
        watched = 0
    status_value = record.get("status", WatchStatus.PLANNING.value)
    if not isinstance(status_value, str):
        raise ValueError("Imported status must be text.")
    try:
        status = WatchStatus(status_value)
    except ValueError:
        raise ValueError(f"Unknown watch status: {status_value}") from None

    return AnimeEntry(
        title=title,
        episodes_total=total,
        episodes_watched=watched,
        status=status,
        provider=optional_text("provider"),
        provider_id=optional_text("provider_id"),
        cover_image=optional_text("cover_image"),
    )


def export_json(entries: Iterable[AnimeEntry]) -> str:
    """Serialize a complete library as a versioned UTF-8 JSON document."""
    payload = {
        "format": "aniyori-library",
        "version": JSON_FORMAT_VERSION,
        "entries": [_entry_to_record(entry) for entry in entries],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject ambiguous object fields instead of silently keeping the last value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"The JSON library backup contains a duplicate key: {key}")
        result[key] = value
    return result


def import_json(content: str) -> list[AnimeEntry]:
    """Validate a versioned JSON library export before returning any entries."""
    try:
        payload = json.loads(content, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as error:
        raise ValueError("The selected file is not valid JSON.") from error
    if not isinstance(payload, dict):
        raise ValueError("The JSON library backup must be an object.")
    if payload.get("format") != "aniyori-library":
        raise ValueError("This file is not an Aniyori library export.")
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != JSON_FORMAT_VERSION:
        raise ValueError("This library export uses an unsupported format version.")
    records = payload.get("entries")
    if not isinstance(records, list):
        raise ValueError("The library export must contain an entries list.")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("Every imported anime entry must be an object.")
    return [_record_to_entry(record) for record in records]


def export_csv(entries: Iterable[AnimeEntry]) -> str:
    """Serialize library entries as a portable CSV document."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for entry in entries:
        writer.writerow(_entry_to_record(entry))
    return output.getvalue()


def import_csv(content: str) -> list[AnimeEntry]:
    """Validate CSV rows before returning any entries."""
    try:
        reader = csv.DictReader(io.StringIO(content, newline=""))
        if reader.fieldnames is not None and len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("The CSV file contains duplicate column names.")
        if reader.fieldnames is None or not set(CSV_FIELDS).issubset(reader.fieldnames):
            raise ValueError("The CSV file is missing required library columns.")
        records = list(reader)
    except csv.Error as error:
        raise ValueError("The selected file is not valid CSV.") from error

    entries = []
    for row_number, record in enumerate(records, start=2):
        try:
            converted: dict[str, object] = dict(record)
            for field in ("episodes_total", "episodes_watched"):
                value = converted.get(field)
                converted[field] = None if value in (None, "") else int(value)
            entries.append(_record_to_entry(converted))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid CSV data on row {row_number}: {error}") from error
    return entries
