"""Small, UI-independent data models used by Aniyori."""

from dataclasses import dataclass, field
from enum import Enum


MAX_EPISODE_COUNT = 10_000


def parse_episode_count(value: str, *, optional: bool = False, field_name: str = "Episode count") -> int | None:
    """Parse a user-entered episode count with clear errors and a sanity limit."""
    text = str(value).strip()
    if not text and optional:
        return None
    if not text:
        raise ValueError(f"{field_name} is required.")
    try:
        count = int(text)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number.") from None
    if count < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    if count > MAX_EPISODE_COUNT:
        raise ValueError(f"{field_name} cannot exceed {MAX_EPISODE_COUNT:,}.")
    return count


class WatchStatus(str, Enum):
    PLANNING = "planning"
    WATCHING = "watching"
    COMPLETED = "completed"
    PAUSED = "paused"
    DROPPED = "dropped"


@dataclass(frozen=True, slots=True)
class AnimeEntry:
    """An anime in the user's library.

    Provider-specific identifiers are optional so entries can be represented
    before an account is connected or while importing local data.
    """

    title: str
    episodes_total: int | None = None
    episodes_watched: int = 0
    status: WatchStatus = WatchStatus.PLANNING
    provider: str | None = None
    provider_id: str | None = None
    cover_image: str | None = None
    storage_id: int | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Anime title must not be empty")
        if self.episodes_total is not None and self.episodes_total < 0:
            raise ValueError("Total episode count cannot be negative")
        if self.episodes_watched < 0:
            raise ValueError("Watched episode count cannot be negative")
        if self.episodes_total is not None and self.episodes_total > MAX_EPISODE_COUNT:
            raise ValueError(f"Total episode count cannot exceed {MAX_EPISODE_COUNT:,}.")
        if self.episodes_watched > MAX_EPISODE_COUNT:
            raise ValueError(f"Watched episode count cannot exceed {MAX_EPISODE_COUNT:,}.")
        if (
            self.episodes_total is not None
            and self.episodes_watched > self.episodes_total
        ):
            raise ValueError("Watched episodes cannot exceed the total")

    @property
    def progress_fraction(self) -> float | None:
        """Return progress from 0.0 to 1.0, or None if total is unknown."""
        if self.episodes_total in (None, 0):
            return None
        return self.episodes_watched / self.episodes_total

    @property
    def progress_label(self) -> str:
        if self.episodes_total is None:
            return f"{self.episodes_watched} / ? episodes"
        return f"{self.episodes_watched} / {self.episodes_total} episodes"
