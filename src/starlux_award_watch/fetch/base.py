"""Fetcher interface and the normalized result type every backend returns."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date

from ..config import Search


@dataclass(frozen=True, slots=True)
class AwardDay:
    """One bookable day for one search, as read off the Alaska award calendar."""

    search_name: str
    origin: str
    destination: str
    depart_date: date
    cabin: str
    carrier: str            # operating carrier code, e.g. "JX"
    miles: int              # per-person award price
    taxes_usd: float | None
    seats: int | None       # remaining award seats at this price, if known
    nonstop: bool
    raw: dict                # backend payload for this day, for debugging

    def key(self) -> tuple[str, str, str, str, str]:
        return (self.origin, self.destination, self.depart_date.isoformat(),
                self.cabin, self.carrier)


class Fetcher(abc.ABC):
    """Return the award-calendar days for a search across a date range.

    Implementations must not raise on 'no availability' — return [] instead.
    They may raise on transport/anti-bot failures so the scheduler can back off.
    """

    name: str

    @abc.abstractmethod
    def fetch(self, search: Search, start: date, end: date) -> list[AwardDay]:
        ...
