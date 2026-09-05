from datetime import date, timedelta

from starlux_award_watch.__main__ import far_range
from starlux_award_watch.config import Config

CFG = Config.model_validate({
    "searches": [dict(name="t", origin="TPE", destination="LAX", carrier="JX",
                      cabin="business", max_miles=75000, passengers=1,
                      nonstop_only=True)],
    "window": {"min_days_ahead": 1, "max_days_ahead": 331},
})

TODAY = date(2026, 9, 4)


def test_far_30_is_last_30_days_of_window():
    lo, hi = far_range(CFG, 30, today=TODAY)
    assert hi == TODAY + timedelta(days=331)
    assert lo == hi - timedelta(days=29)
    assert (hi - lo).days == 29


def test_far_clamps_to_min_days_ahead():
    # a huge --far shouldn't reach before min_days_ahead
    lo, hi = far_range(CFG, 10_000, today=TODAY)
    assert lo == TODAY + timedelta(days=1)
    assert hi == TODAY + timedelta(days=331)
