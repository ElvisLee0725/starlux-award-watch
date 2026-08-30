"""Playwright fallback: drive alaskaair.com award search in a headless browser
and read the flexible-date calendar out of the rendered page (or better, out of
the XHR responses Playwright can intercept).

TODO(recon): implement after we know the page flow and selectors / response URL.
Kept behind the optional 'browser' extra so the base install stays light.
"""
from __future__ import annotations

from datetime import date

from ..config import Search
from .base import AwardDay, Fetcher


class AlaskaBrowserFetcher(Fetcher):
    name = "alaska-browser"

    def __init__(self, request_delay: tuple[float, float] = (3.0, 8.0),
                 headless: bool = True) -> None:
        self.request_delay = request_delay
        self.headless = headless

    def fetch(self, search: Search, start: date, end: date) -> list[AwardDay]:
        raise NotImplementedError("AlaskaBrowserFetcher — see recon TODO.")
