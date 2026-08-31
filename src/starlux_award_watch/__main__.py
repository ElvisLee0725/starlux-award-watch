"""Entrypoint: `python -m starlux_award_watch [--once] [--dry-run] ...`."""
from __future__ import annotations

import argparse
import datetime as dt
import os

import structlog

from .config import load_config
from .fetch.browser import AlaskaBrowserFetcher
from .match import filter_hits
from .notify import ConsoleNotifier, make_notifier
from .scheduler import Runner
from .store import Store

log = structlog.get_logger()


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    ap = argparse.ArgumentParser(prog="starlux-award-watch")
    ap.add_argument("--once", action="store_true", help="run one full sweep and exit")
    ap.add_argument("--dry-run", action="store_true", help="never send SMS; print instead")
    ap.add_argument("--headed", action="store_true", help="force a visible browser window")
    ap.add_argument("--days", type=int, metavar="N",
                    help="cap the scan to the next N days (for testing)")
    ap.add_argument("--route", metavar="SUBSTR",
                    help="only run searches whose name contains SUBSTR")
    ap.add_argument("--test-sms", action="store_true",
                    help="send one test SMS via Twilio and exit")
    args = ap.parse_args()

    _load_dotenv()

    if args.test_sms:
        from .notify import make_notifier
        cfg = load_config()
        res = make_notifier(cfg.alerts.channel).send_text(
            "starlux-award-watch: test alert. If you got this, alerts work."
        )
        log.info("test_alert_sent", channel=cfg.alerts.channel, result=res)
        return

    cfg = load_config()

    if args.route:
        cfg.searches = [s for s in cfg.searches if args.route.lower() in s.name.lower()]
        if not cfg.searches:
            raise SystemExit(f"no search matches --route {args.route!r}")
    if args.days:
        cfg.window.max_days_ahead = min(cfg.window.max_days_ahead,
                                        cfg.window.min_days_ahead + args.days - 1)

    fetcher = AlaskaBrowserFetcher(
        profile_dir=cfg.browser.profile_dir,
        headless=cfg.browser.headless and not args.headed,
        request_delay=cfg.poll.request_delay_seconds,
        nav_timeout_ms=cfg.browser.nav_timeout_ms,
        shoulder_prefilter=cfg.browser.shoulder_prefilter,
    )
    store = Store()
    notifier = ConsoleNotifier() if args.dry_run else make_notifier(cfg.alerts.channel)
    runner = Runner(cfg, fetcher, store, notifier)

    try:
        if args.once:
            lo, hi = runner._full_range()
            log.info("once", start=str(lo), end=str(hi),
                     searches=[s.name for s in cfg.searches])
            runner.run_pass(lo, hi, "once")
        else:
            runner.loop()
    finally:
        fetcher.close()
        store.close()


if __name__ == "__main__":
    main()


# convenience for ad-hoc checks: `python -m starlux_award_watch.probe` style
def probe(route_substr: str, days: int = 3) -> None:  # pragma: no cover
    _load_dotenv()
    cfg = load_config()
    cfg.searches = [s for s in cfg.searches if route_substr.lower() in s.name.lower()]
    f = AlaskaBrowserFetcher(profile_dir=cfg.browser.profile_dir, headless=False)
    today = dt.date.today()
    try:
        for s in cfg.searches:
            rows = f.fetch(s, today + dt.timedelta(days=1), today + dt.timedelta(days=days))
            print(f"\n{s.name}: {len(rows)} rows")
            for r in rows:
                mark = "  <<< HIT" if filter_hits(s, [r]) else ""
                print(f"  {r.depart_date} {r.raw['flight']:>7} {r.cabin:9} "
                      f"{r.miles:>7,} +${r.taxes_usd or 0:.0f} "
                      f"nonstop={r.nonstop} seats={r.seats}{mark}")
    finally:
        f.close()
