"""Bounded receiver retry policy; no Qt dependency for regression testing."""
from __future__ import annotations


def retry_delay(attempt: int, *, maximum: int = 5) -> int | None:
    """Seconds before retry number 1..maximum; None means stop retrying."""
    if maximum < 0 or attempt < 1 or attempt > maximum:
        return None
    return min(60, 5 * (2 ** (attempt - 1)))
