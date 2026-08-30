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
    channel: Literal["sms"] = "sms"
    renotify_after_hours: float = 12
    on_price_drop: bool = True
    quiet_hours: tuple[int, int] | None = None


class Config(BaseModel):
    searches: list[Search] = Field(min_length=1)
    window: Window = Window()
    poll: Poll = Poll()
    alerts: Alerts = Alerts()


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    path = Path(path or os.environ.get("STARLUX_CONFIG", "config.yaml"))
    data = yaml.safe_load(path.read_text())
    return Config.model_validate(data)
