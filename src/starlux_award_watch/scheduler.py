"""Polling loop: full sweeps of the whole window plus frequent far-edge passes."""
from __future__ import annotations

import random
import time
from datetime import date, timedelta

import structlog

from .config import Config
from .fetch.base import AwardDay, Fetcher
from .fetch.browser import ChallengeRequired
from .match import filter_hits
from .store import Store

log = structlog.get_logger()


def _human_dur(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 90:
        return f"{s}s"
    m = s // 60
    if m < 90:
        return f"{m}m"
    h = m // 60
    if h < 36:
        return f"{h}h"
    return f"{h // 24}d"


def _human_ago(seconds: float) -> str:
    return _human_dur(seconds) + " ago"


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
        earliest = today + timedelta(days=self.cfg.window.min_days_ahead)
        start = max(earliest, end - timedelta(days=self.cfg.poll.far_edge_days))
        return (start, end)

    # -- one pass --------------------------------------------------------------
    def run_pass(self, start: date, end: date, label: str) -> bool:
        """Returns True if the pass completed without a CAPTCHA abort."""
        self.store.bump_meta("hb_passes")
        for i, search in enumerate(self.cfg.searches):
            if i:  # brief gap between searches; per-page pacing lives in the fetcher
                time.sleep(random.uniform(*self.cfg.poll.request_delay_seconds))
            try:
                days = self.fetcher.fetch(search, start, end)
            except ChallengeRequired as exc:
                self.store.bump_meta("hb_captchas")
                cooldown = self.cfg.browser.challenge_cooldown_minutes
                log.warning("captcha", search=search.name, url=exc.url, cooldown_min=cooldown)
                try:
                    self.notifier.send_text(
                        f"starlux-award-watch hit an Alaska CAPTCHA.\n"
                        f"Run: python scripts/warm.py  and solve it.\n{exc.url}\n"
                        f"Pausing {cooldown:g} min.",
                        priority=0,
                    )
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(cooldown * 60)
                return False  # abort this pass; next tick starts fresh
            except Exception as exc:  # noqa: BLE001 — log and keep other searches alive
                self.store.bump_meta("hb_errors")
                log.warning("fetch_failed", search=search.name, pass_=label, error=str(exc))
                continue

            for day in days:
                self.store.record_seen(day)

            for hit in filter_hits(search, days):
                self._maybe_alert(hit)

        if label == "full":
            self.store.set_meta("last_sweep_ok", time.time())
            self.store.bump_meta("hb_full_sweeps")
        return True

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
        self.store.bump_meta("hb_hits")
        log.info("alert_sent", key=hit.key(), miles=hit.miles, sid=sid)

    # -- heartbeat --------------------------------------------------------------
    def _heartbeat_if_due(self) -> None:
        hours = self.cfg.alerts.heartbeat_hours
        if not hours:
            return
        now = time.time()
        last = float(self.store.get_meta("hb_last", "0") or "0")
        if last and (now - last) < hours * 3600:
            return

        g = lambda k: self.store.get_meta(k, "0") or "0"  # noqa: E731
        last_sweep = self.store.get_meta("last_sweep_ok")
        ago = _human_ago(now - float(last_sweep)) if last_sweep else "not yet"
        window = "since start" if not last else f"in the last {_human_dur(now - last)}"
        lines = [
            "starting up — monitor is live." if not last else "still watching.",
            f"last full sweep: {ago}",
            f"{window}: {g('hb_full_sweeps')} sweeps, {g('hb_passes')} passes, "
            f"{g('hb_hits')} hits, {g('hb_captchas')} CAPTCHAs, {g('hb_errors')} errors",
            f"routes: {len(self.cfg.searches)}",
        ]
        try:
            self.notifier.send_text("\n".join(lines),
                                    priority=self.cfg.alerts.heartbeat_priority)
        except Exception as exc:  # noqa: BLE001
            log.warning("heartbeat_failed", error=str(exc))
            return
        self.store.set_meta("hb_last", now)
        for k in ("hb_passes", "hb_full_sweeps", "hb_hits", "hb_captchas", "hb_errors"):
            self.store.set_meta(k, "0")
        log.info("heartbeat_sent")

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
    def loop(self, max_cycles: int | None = None) -> None:
        next_full = 0.0
        next_edge = 0.0
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
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
            self._heartbeat_if_due()

            cycles += 1
            nap = min(next_full, next_edge) - time.monotonic()
            if nap > 0:
                # wake at least hourly so a slept-through deadline fires promptly
                time.sleep(min(nap, 3600))
