"""Parse the saved TPE->LAX award results page (captured 2026, OD 2026-12-28)."""
from datetime import date
from pathlib import Path

import pytest

from starlux_award_watch.config import Search
from starlux_award_watch.fetch.browser import (
    _parse_miles, _parse_seats, _parse_usd, parse_results,
)

FIXTURE = Path(__file__).parent / "fixtures" / "results_tpe_lax_award.html"
DAY = date(2026, 12, 28)


@pytest.fixture(scope="module")
def html_text():
    return FIXTURE.read_text()


def _search(**over):
    base = dict(name="TPE->LAX biz", origin="TPE", destination="LAX", carrier="JX",
                cabin="business", max_miles=75000, max_taxes_usd=200,
                passengers=1, nonstop_only=True)
    base.update(over)
    return Search(**base)


@pytest.mark.parametrize("text,expected", [
    ("45k points pts + $55", 45000),
    ("175k pts + $55", 175000),
    ("37.5k pts + $54", 37500),
    ("1,000k", 1000000),
])
def test_parse_miles(text, expected):
    assert _parse_miles(text) == expected


def test_parse_usd_and_seats():
    assert _parse_usd("175k pts + $1,082") == 1082.0
    assert _parse_usd("70k pts + $60") == 60.0
    assert _parse_seats("Refundable last 6 seats One way") == 6
    assert _parse_seats("no scarcity here") is None


def test_business_fares_extracted(html_text):
    days = parse_results(_search(), DAY, html_text)
    assert days, "expected at least one business fare parsed"
    assert all(d.cabin == "business" for d in days)
    # every parsed row on this page is a Starlux (JX) flight
    assert all(d.carrier == "JX" for d in days)


def test_nonstop_jx2_business_is_175k(html_text):
    days = parse_results(_search(), DAY, html_text)
    nonstop = [d for d in days if d.nonstop]
    assert len(nonstop) == 1, "exactly one nonstop TPE-LAX Starlux flight on this page"
    jx2 = nonstop[0]
    assert jx2.miles == 175000
    assert jx2.taxes_usd == 55.0
    assert jx2.raw["flight"] == "JX 2"
    assert jx2.origin == "TPE" and jx2.destination == "LAX"


def test_matcher_rejects_this_page(html_text):
    """On 2026-12-28 the saver seat is gone (175k) -> no hit at <=75k."""
    from starlux_award_watch.match import filter_hits

    s = _search()
    hits = filter_hits(s, parse_results(s, DAY, html_text))
    assert hits == []
