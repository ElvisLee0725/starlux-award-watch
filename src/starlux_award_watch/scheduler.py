"""Polling loop: full sweeps of the whole window plus frequent far-edge passes."""
from __future__ import annotations

import random
import time
from datetime import date, timedelta

import structlog

from .config import Config
from .fetch.base import AwardDay, Fetcher
from .match import filter_hits
from .store import Store

log = structlog.get_logger()


class Runner:
    def __init__(self, cfg: Config, fetcher: Fetcher, store: Store, notifier) -> None:
        self.cfg = cfg
        self.fetcher = fetcher
        self.store = store
        self.notifier = notifier

    # -- date ranges -------------------------------------------------------
    def _full_range(self) -> tuple[date, date]:
        today = date.today()
        return (today + timedelta(days=self.cfg.window.min_days_ahead),
                today + timedelta(days=self.cfg.window.max_days_ahead))

    def _far_edge_range(self) -> tuple[date, date]:
        today = date.today()
        end = today + timedelta(days=self.cfg.window.max_days_ahead)
        start = end - timedelta(days=self.cfg.poll.far_edge_days)
        return (start, end)

    # -- one pass --------------------------------------------------------------
    def run_pass(self, start: date, end: date, label: str) -> None:
        for search in self.cfg.searches:
            try:
                days = self.fetcher.fetch(search, start, end)
            except Exception as exc:  # noqa: BLE001 — log and keep other searches alive
                log.warning("fetch_failed", search=search.name, pass_=label, error=str(exc))
                continue

            for day in days:
                self.store.record_seen(day)

            for hit in filter_hits(search, days):
                self._maybe_alert(hit)

            lo, hi = self.cfg.poll.request_delay_seconds
            time.sleep(random.uniform(lo, hi))

    def _maybe_alert(self, hit: AwardDay) -> None:
        if not self.store.should_alert(
            hit,
            renotify_after_hours=self.cfg.alerts.renotify_after_hours,
            on_price_drop=self.cfg.alerts.on_price_drop,
        ):
            return
        if self._in_quiet_hours():
            log.info("suppressed_quiet_hours", key=hit.key())
            return
        sid = self.notifier.send(hit)
        self.store.record_alert(hit)
        log.info("alert_sent", key=hit.key(), miles=hit.miles, sid=sid)

    def _in_quiet_hours(self) -> bool:
        qh = self.cfg.alerts.quiet_hours
        if not qh:
            return False
        start_h, end_h = qh
        now_h = time.localtime().tm_hour
        if start_h <= end_h:
            return start_h <= now_h < end_h
        return now_h >= start_h or now_h < end_h

    def _jitter(self, minutes: float) -> float:
        j = self.cfg.poll.jitter_pct
        return minutes * random.uniform(1 - j, 1 + j) * 60

    # -- main loop ----------------------------------------------------------
    def loop(self) -> None:
        next_full = 0.0
        next_edge = 0.0
        while True:
            now = time.monotonic()
            if now >= next_full:
                lo, hi = self._full_range()
                log.info("full_sweep_start", start=str(lo), end=str(hi))
                self.run_pass(lo, hi, "full")
                next_full = time.monotonic() + self._jitter(self.cfg.poll.full_sweep_minutes)
            if now >= next_edge:
                lo, hi = self._far_edge_range()
                log.info("far_edge_start", start=str(lo), end=str(hi))
                self.run_pass(lo, hi, "edge")
                next_edge = time.monotonic() + self._jitter(self.cfg.poll.far_edge_minutes)
            time.sleep(min(next_full, next_edge) - time.monotonic())
