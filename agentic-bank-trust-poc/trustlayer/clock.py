"""Deterministic clock so runs, audit trails and tests are reproducible."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


class Clock:
    """A fake clock. Every read advances time by one second, so audit
    timestamps are strictly increasing without any real waiting."""

    def __init__(self, start: Optional[datetime] = None) -> None:
        self._now = start or datetime(2026, 11, 4, 9, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self._now
        self._now = self._now + timedelta(seconds=1)
        return current

    def peek(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        self._now = self._now + timedelta(**kwargs)
