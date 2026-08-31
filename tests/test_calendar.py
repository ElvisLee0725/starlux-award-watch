"""Parse the saved TPE->ONT Business month calendar (CM=2026-11)."""
from datetime import date
from pathlib import Path

import pytest

from starlux_award_watch.fetch.browser import parse_calendar

FIXTURE = Path(__file__).parent / "fixtures" / "calendar_tpe_ont_business.html"


@pytest.fixture(scope="module")
def cal():
    return parse_calendar(FIXTURE.read_text())


def test_covers_whole_month(cal):
    days = sorted(cal)
    assert days[0] == date(2026, 11, 1)
    assert days[-1] == date(2026, 11, 30)
    assert len(days) == 30


def test_known_prices(cal):
    assert cal[date(2026, 11, 1)] == (130000, 76.0)
    assert cal[date(2026, 11, 2)] == (175000, 55.0)
    assert cal[date(2026, 11, 12)] == (110000, 76.0)
    assert cal[date(2026, 11, 26)] == (200000, 67.0)


def test_selected_day_still_parses(cal):
    # aria-label for Nov 15 is prefixed "Selected, "
    assert cal[date(2026, 11, 15)] == (130000, 76.0)


def test_unavailable_days_are_none(cal):
    assert cal[date(2026, 11, 28)] == (None, None)
    assert cal[date(2026, 11, 30)] == (None, None)


def test_no_business_saver_this_month(cal):
    # nothing at/under 75k on TPE->ONT business in Nov 2026
    assert min(mi for mi, _ in cal.values() if mi is not None) == 110000
