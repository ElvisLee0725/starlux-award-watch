from datetime import date

from starlux_award_watch.config import Search
from starlux_award_watch.fetch.base import AwardDay
from starlux_award_watch.match import matches


def _day(**over):
    base = dict(
        search_name="t", origin="TPE", destination="LAX", depart_date=date(2026, 11, 1),
        cabin="business", carrier="JX", miles=75000, taxes_usd=90.0, seats=1,
        nonstop=True, raw={},
    )
    base.update(over)
    return AwardDay(**base)


def _search(**over):
    base = dict(name="t", origin="TPE", destination="LAX", carrier="JX",
                cabin="business", max_miles=75000, max_taxes_usd=200,
                passengers=1, nonstop_only=True)
    base.update(over)
    return Search(**base)


def test_exact_target_matches():
    assert matches(_search(), _day())


def test_over_target_rejected():
    assert not matches(_search(), _day(miles=175000))


def test_wrong_carrier_rejected():
    assert not matches(_search(), _day(carrier="CX"))


def test_connection_rejected_when_nonstop_only():
    assert not matches(_search(), _day(nonstop=False))


def test_too_few_seats_rejected():
    assert not matches(_search(passengers=2), _day(seats=1))


def test_high_taxes_rejected():
    assert not matches(_search(max_taxes_usd=100), _day(taxes_usd=250))
