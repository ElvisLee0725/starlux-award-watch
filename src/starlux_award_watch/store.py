"""SQLite state: what we've seen, and what we've already texted about.

Alert decision lives here so the scheduler stays dumb:
  - new (route, date, cabin, carrier) hit           -> alert
  - price dropped vs last alert                      -> alert (if on_price_drop)
  - still available >= renotify_after_hours later    -> alert again
  - otherwise                                        -> stay quiet
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .fetch.base import AwardDay

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    k            TEXT PRIMARY KEY,      -- AwardDay.key() joined by '|'
    miles        INTEGER NOT NULL,
    taxes_usd    REAL,
    seats        INTEGER,
    first_seen   REAL NOT NULL,
    last_seen    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    k             TEXT NOT NULL,
    miles         INTEGER NOT NULL,
    sent_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS alerts_k_time ON alerts (k, sent_at DESC);
CREATE TABLE IF NOT EXISTS meta (
    k  TEXT PRIMARY KEY,
    v  TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path = "data/state.db") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _k(day: AwardDay) -> str:
        return "|".join(day.key())

    def record_seen(self, day: AwardDay) -> None:
        now = time.time()
        k = self._k(day)
        self.db.execute(
            """
            INSERT INTO seen (k, miles, taxes_usd, seats, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(k) DO UPDATE SET
                miles=excluded.miles,
                taxes_usd=excluded.taxes_usd,
                seats=excluded.seats,
                last_seen=excluded.last_seen
            """,
            (k, day.miles, day.taxes_usd, day.seats, now, now),
        )
        self.db.commit()

    def _last_alert(self, k: str) -> tuple[int, float] | None:
        row = self.db.execute(
            "SELECT miles, sent_at FROM alerts WHERE k=? ORDER BY sent_at DESC LIMIT 1",
            (k,),
        ).fetchone()
        return (row[0], row[1]) if row else None

    def should_alert(self, day: AwardDay, *, renotify_after_hours: float,
                     on_price_drop: bool) -> bool:
        last = self._last_alert(self._k(day))
        if last is None:
            return True
        last_miles, last_time = last
        if on_price_drop and day.miles < last_miles:
            return True
        if (time.time() - last_time) >= renotify_after_hours * 3600:
            return True
        return False

    def record_alert(self, day: AwardDay) -> None:
        self.db.execute(
            "INSERT INTO alerts (k, miles, sent_at) VALUES (?, ?, ?)",
            (self._k(day), day.miles, time.time()),
        )
        self.db.commit()

    # -- meta (heartbeat state + counters) -----------------------------------
    def get_meta(self, k: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return row[0] if row else default

    def set_meta(self, k: str, v) -> None:
        self.db.execute(
            "INSERT INTO meta (k, v) VALUES (?, ?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, str(v)),
        )
        self.db.commit()

    def bump_meta(self, k: str, n: int = 1) -> int:
        new = int(self.get_meta(k, "0") or "0") + n
        self.set_meta(k, new)
        return new
