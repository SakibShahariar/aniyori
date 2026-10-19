"""Small, UI-independent data models used by Aniyori."""

from dataclasses import dataclass, field
from enum import Enum


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
    storage_id: int | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Anime title must not be empty")
        if self.episodes_total is not None and self.episodes_total < 0:
            raise ValueError("Total episode count cannot be negative")
        if self.episodes_watched < 0:
            raise ValueError("Watched episode count cannot be negative")
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
            return f"{self.episodes_watched} watched"
        return f"{self.episodes_watched} / {self.episodes_total} episodes"
