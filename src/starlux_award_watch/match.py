"""Apply a Search's rules to fetched AwardDays."""
from __future__ import annotations

from .config import Search
from .fetch.base import AwardDay


def matches(search: Search, day: AwardDay) -> bool:
    if day.carrier != search.carrier:
        return False
    if day.cabin != search.cabin:
        return False
    if search.nonstop_only and not day.nonstop:
        return False
    if day.miles > search.max_miles:
        return False
    if (search.max_taxes_usd is not None
            and day.taxes_usd is not None
            and day.taxes_usd > search.max_taxes_usd):
        return False
    if day.seats is not None and day.seats < search.passengers:
        return False
    return True


def filter_hits(search: Search, days: list[AwardDay]) -> list[AwardDay]:
    return [d for d in days if matches(search, d)]
