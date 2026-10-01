from datetime import date

from starlux_award_watch.notify import (
    format_alert, format_title, route_endpoint,
)
from starlux_award_watch.fetch.base import AwardDay

COLORS = {"SFO": "#0091ff", "LAX": "#e5484d"}


def _day(o="TPE", d="SFO", miles=75000):
    return AwardDay(search_name="t", origin=o, destination=d,
                    depart_date=date(2027, 7, 19), cabin="business", carrier="JX",
                    miles=miles, taxes_usd=26.0, seats=1, nonstop=True,
                    raw={"flight": "JX 12"})


def test_route_endpoint_is_the_non_hub_airport():
    assert route_endpoint(_day("TPE", "SFO")) == "SFO"
    assert route_endpoint(_day("SFO", "TPE")) == "SFO"


def test_plain_body_has_no_html():
    body = format_alert(_day())
    assert "<font" not in body and "TPE->SFO" in body


def test_body_includes_departure_and_arrival_time_when_known():
    day = AwardDay(search_name="t", origin="TPE", destination="SFO",
                   depart_date=date(2027, 7, 19), cabin="business", carrier="JX",
                   miles=75000, taxes_usd=26.0, seats=1, nonstop=True,
                   raw={"flight": "JX 12", "dep": "8:05 pm", "arr": "5:05 pm"})
    body = format_alert(day)
    assert "8:05 pm → 5:05 pm" in body


def test_body_omits_time_line_when_unknown():
    body = format_alert(_day())  # raw has no dep/arr keys
    assert "→" not in body


def test_html_body_colours_route_line_by_endpoint():
    body = format_alert(_day("SFO", "TPE"), html=True, route_colors=COLORS)
    assert '<font color="#0091ff">SFO->TPE</font>' in body
    assert body.startswith("STARLUX JX 12 business")


def test_unmapped_route_falls_back_to_grey():
    body = format_alert(_day("TPE", "JFK"), html=True, route_colors=COLORS)
    assert '<font color="#8b8d98">TPE->JFK</font>' in body


def test_title_one_line():
    assert format_title(_day("SFO", "TPE")) == "SFO→TPE 19 Jul · 75k"
