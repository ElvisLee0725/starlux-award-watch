"""Heartbeat digest: startup send, interval gating, counter reset."""
from datetime import date, timedelta

from starlux_award_watch.config import Config
from starlux_award_watch.scheduler import Runner, _human_dur
from starlux_award_watch.store import Store

CFG = {
    "searches": [dict(name="TPE->LAX", origin="TPE", destination="LAX",
                      carrier="JX", cabin="business", max_miles=75000,
                      passengers=1, nonstop_only=True)],
    "window": {"min_days_ahead": 2, "max_days_ahead": 60},
    "alerts": {"heartbeat_hours": 24, "heartbeat_priority": -1},
}


class Rec:
    def __init__(self):
        self.msgs = []

    def send(self, day):  # unused here
        return "x"

    def send_text(self, body, priority=0):
        self.msgs.append((priority, body))
        return "rec"


def _runner(tmp_path, cfg_over=None):
    data = {**CFG, **(cfg_over or {})}
    cfg = Config.model_validate(data)
    store = Store(tmp_path / "s.db")
    note = Rec()
    return Runner(cfg, object(), store, note), store, note


def test_human_dur():
    assert _human_dur(10) == "10s"
    assert _human_dur(300) == "5m"
    assert _human_dur(7200) == "2h"
    assert _human_dur(3 * 86400) == "3d"


def test_first_call_sends_startup_digest(tmp_path):
    r, store, note = _runner(tmp_path)
    r._heartbeat_if_due()
    assert len(note.msgs) == 1
    prio, body = note.msgs[0]
    assert prio == -1
    assert "monitor is live" in body
    assert store.get_meta("hb_last") is not None


def test_second_call_within_interval_is_silent(tmp_path):
    r, store, note = _runner(tmp_path)
    r._heartbeat_if_due()
    r._heartbeat_if_due()
    assert len(note.msgs) == 1


def test_disabled_when_hours_zero(tmp_path):
    r, store, note = _runner(tmp_path, {"alerts": {"heartbeat_hours": 0}})
    r._heartbeat_if_due()
    assert note.msgs == []


def test_counters_reset_after_send(tmp_path):
    r, store, note = _runner(tmp_path)
    for _ in range(3):
        store.bump_meta("hb_passes")
    store.bump_meta("hb_hits")
    r._heartbeat_if_due()
    assert store.get_meta("hb_passes") == "0"
    assert store.get_meta("hb_hits") == "0"


def test_due_again_after_interval(tmp_path):
    import time
    r, store, note = _runner(tmp_path)
    r._heartbeat_if_due()
    store.set_meta("hb_last", time.time() - 25 * 3600)  # 25h ago
    r._heartbeat_if_due()
    assert len(note.msgs) == 2
    assert "still watching" in note.msgs[1][1]
