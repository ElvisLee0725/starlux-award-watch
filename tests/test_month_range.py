from datetime import date

import pytest

from starlux_award_watch.__main__ import month_range
from starlux_award_watch.config import Config

CFG = Config.model_validate({
    "searches": [dict(name="t", origin="TPE", destination="LAX", carrier="JX",
                      cabin="business", max_miles=75000, passengers=1,
                      nonstop_only=True)],
    "window": {"min_days_ahead": 1, "max_days_ahead": 331},
})

TODAY = date(2026, 10, 10)  # window: 2026-10-11 .. 2027-09-06


def test_later_month_this_year_is_whole_month():
    assert month_range(CFG, 12, today=TODAY) == (date(2026, 12, 1), date(2026, 12, 31))


def test_earlier_month_rolls_to_next_year():
    assert month_range(CFG, 3, today=TODAY) == (date(2027, 3, 1), date(2027, 3, 31))
    assert month_range(CFG, 2, today=TODAY) == (date(2027, 2, 1), date(2027, 2, 28))


def test_current_month_is_remaining_days():
    assert month_range(CFG, 10, today=TODAY) == (date(2026, 10, 11), date(2026, 10, 31))


def test_month_clipped_at_far_edge():
    assert month_range(CFG, 9, today=TODAY) == (date(2027, 9, 1), date(2027, 9, 6))


def test_month_outside_window_raises():
    short = CFG.model_copy(deep=True)
    short.window.max_days_ahead = 60  # ends 2026-12-09
    with pytest.raises(ValueError):
        month_range(short, 3, today=TODAY)


def test_last_day_of_month_rolls_past_current_month():
    # on Oct 31 with min 1 day ahead, "October" can't be booked this year
    with pytest.raises(ValueError):
        month_range(CFG, 10, today=date(2026, 10, 31))
