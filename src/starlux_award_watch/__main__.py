"""Entrypoint: `python -m starlux_award_watch [--once] [--dry-run]`."""
from __future__ import annotations

import argparse
import os

import structlog

from .config import load_config
from .fetch.api import AlaskaApiFetcher
from .notify import ConsoleNotifier, SmsNotifier
from .scheduler import Runner
from .store import Store

log = structlog.get_logger()


def _load_dotenv() -> None:
    path = ".env"
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
    args = ap.parse_args()

    _load_dotenv()
    cfg = load_config()

    fetcher = AlaskaApiFetcher(request_delay=cfg.poll.request_delay_seconds)
    store = Store()
    notifier = ConsoleNotifier() if args.dry_run else SmsNotifier()
    runner = Runner(cfg, fetcher, store, notifier)

    if args.once:
        lo, hi = runner._full_range()
        runner.run_pass(lo, hi, "once")
    else:
        runner.loop()


if __name__ == "__main__":
    main()
