"""Small request-generation helper for discarding stale search responses."""


class SearchGeneration:
    """Track the newest request so older asynchronous results can be ignored."""

    def __init__(self):
        self._generation = 0

    def begin(self) -> int:
        """Start a new request and return its generation token."""
        self._generation += 1
        return self._generation

    def invalidate(self) -> None:
        """Invalidate every request started before this call."""
        self._generation += 1

    def is_current(self, generation: int) -> bool:
        """Return whether a response belongs to the newest request."""
        return generation == self._generation
