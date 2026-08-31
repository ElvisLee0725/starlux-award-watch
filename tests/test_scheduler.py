"""Runner date-range / quiet-hours / dedup-alert logic, with a fake fetcher."""
from datetime import date, timedelta

from starlux_award_watch.config import Config
from starlux_award_watch.fetch.base import AwardDay
from starlux_award_watch.scheduler import Runner
from starlux_award_watch.store import Store

CFG = {
    "searches": [dict(name="TPE->LAX", origin="TPE", destination="LAX",
                      carrier="JX", cabin="business", max_miles=75000,
                      passengers=1, nonstop_only=True)],
    "window": {"min_days_ahead": 2, "max_days_ahead": 100},
    "poll": {"far_edge_days": 10},
}


class FakeFetcher:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def fetch(self, search, start, end):
        self.calls.append((start, end))
        return [r for r in self.rows if start <= r.depart_date <= end]


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def send(self, day):
        self.sent.append(day)
        return "rec"

    def send_text(self, body):
        self.sent.append(body)
        return "rec"


def _hit(d: date, miles=75000):
    return AwardDay(search_name="TPE->LAX", origin="TPE", destination="LAX",
                    depart_date=d, cabin="business", carrier="JX", miles=miles,
                    taxes_usd=55.0, seats=1, nonstop=True, raw={"flight": "JX 2"})


def _runner(tmp_path, rows):
    cfg = Config.model_validate(CFG)
    store = Store(tmp_path / "s.db")
    fetch = FakeFetcher(rows)
    note = RecordingNotifier()
    return Runner(cfg, fetch, store, note), fetch, note, store


def test_full_and_far_edge_ranges(tmp_path):
    r, *_ = _runner(tmp_path, [])
    today = date.today()
    lo, hi = r._full_range()
    assert lo == today + timedelta(days=2)
    assert hi == today + timedelta(days=100)
    elo, ehi = r._far_edge_range()
    assert ehi == today + timedelta(days=100)
    assert elo == today + timedelta(days=90)


def test_alert_fires_once_then_silent(tmp_path):
    d = date.today() + timedelta(days=30)
    r, fetch, note, store = _runner(tmp_path, [_hit(d)])
    lo, hi = r._full_range()
    r.run_pass(lo, hi, "t")
    r.run_pass(lo, hi, "t")
    assert len(note.sent) == 1
    store.close()


def test_alert_refires_on_price_drop(tmp_path):
    d = date.today() + timedelta(days=30)
    r, fetch, note, store = _runner(tmp_path, [_hit(d, 75000)])
    lo, hi = r._full_range()
    r.run_pass(lo, hi, "t")
    fetch.rows = [_hit(d, 70000)]          # cheaper now
    r.run_pass(lo, hi, "t")
    assert len(note.sent) == 2
    store.close()


def test_quiet_hours_wraps_midnight(tmp_path):
    r, *_ = _runner(tmp_path, [])
    r.cfg.alerts.quiet_hours = (23, 7)
    assert r._in_quiet_hours.__self__ is r  # bound
    # 23<=h<7 wrap: hour 2 quiet, hour 12 not — check the logic directly
    import time as _t
    from unittest.mock import patch
    with patch.object(_t, "localtime", lambda: _t.struct_time((2026, 1, 1, 2, 0, 0, 0, 1, 0))):
        assert r._in_quiet_hours() is True
    with patch.object(_t, "localtime", lambda: _t.struct_time((2026, 1, 1, 12, 0, 0, 0, 1, 0))):
        assert r._in_quiet_hours() is False
