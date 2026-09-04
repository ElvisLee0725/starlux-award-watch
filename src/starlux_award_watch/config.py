"""Load and validate config.yaml."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

Cabin = Literal["economy", "premium", "business", "first"]


class Search(BaseModel):
    name: str
    origin: str
    destination: str
    carrier: str = "JX"
    cabin: Cabin = "business"
    max_miles: int
    max_taxes_usd: float | None = None
    passengers: int = 1
    nonstop_only: bool = True

    @field_validator("origin", "destination", "carrier")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class Window(BaseModel):
    min_days_ahead: int = 1
    max_days_ahead: int = 331


class Poll(BaseModel):
    full_sweep_minutes: int = 120
    far_edge_minutes: int = 20
    far_edge_days: int = 21
    jitter_pct: float = 0.3
    request_delay_seconds: tuple[float, float] = (3.0, 8.0)


class Alerts(BaseModel):
    channel: Literal["pushover", "sms", "console"] = "pushover"
    renotify_after_hours: float = 12
    on_price_drop: bool = True
    quiet_hours: tuple[int, int] | None = None
    # Pushover priority for a hit: 2 = emergency (re-alerts every `retry_s`
    # until you ack, up to `expire_s`); 1 = high; 0 = normal.
    pushover_priority: int = 2
    pushover_retry_s: int = 60
    pushover_expire_s: int = 3600
    # "still alive" digest so silence means "no seats", not "process/Mac dead".
    heartbeat_hours: float = 24     # 0 = off; also sends one on startup
    heartbeat_priority: int = -1    # -1 = quiet (no sound/vibration)
    # Colour the route line in the Pushover body, keyed by the non-TPE airport.
    route_colors: dict[str, str] = Field(default_factory=lambda: {
        "LAX": "#e5484d", "ONT": "#f76b15", "SFO": "#0091ff",
        "SEA": "#30a46c", "PHX": "#f5a623",
    })


class Browser(BaseModel):
    profile_dir: str = "data/chrome-profile"
    headless: bool = False
    nav_timeout_ms: int = 45_000
    challenge_cooldown_minutes: float = 30
    # Headed runs: seconds to wait for a human to clear an Akamai challenge in
    # the visible window before giving up (0 = never wait). Headless always
    # gives up immediately.
    headed_challenge_wait_s: int = 180
    # After the month calendar flags a day at/under target, load that day's full
    # results page to confirm it's the nonstop carrier we want (not a cheaper
    # partner connection). Turn off for calendar-only (coarser, faster) alerts.
    confirm_candidates: bool = True


class Config(BaseModel):
    searches: list[Search] = Field(min_length=1)
    window: Window = Window()
    poll: Poll = Poll()
    alerts: Alerts = Alerts()
    browser: Browser = Browser()


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    path = Path(path or os.environ.get("STARLUX_CONFIG", "config.yaml"))
    data = yaml.safe_load(path.read_text())
    return Config.model_validate(data)
