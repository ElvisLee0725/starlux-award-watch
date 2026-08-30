"""Direct JSON scrape of the Alaska award / flexible-date calendar.

TODO(recon): fill in once we've captured the real endpoint from alaskaair.com
devtools. We need:
  - the request URL + method for the miles-per-day grid
  - required query params / JSON body (origin, dest, month, award=true, pax, cabin)
  - headers / cookies Akamai wants (may need curl_cffi impersonate="chrome")
  - the response shape: where per-day miles, taxes, seat count, and operating
    carrier live

Until then this backend reports itself unavailable so the scheduler falls back
to the Playwright backend.
"""
from __future__ import annotations

from datetime import date

from ..config import Search
from .base import AwardDay, Fetcher


class NotYetImplemented(RuntimeError):
    pass


class AlaskaApiFetcher(Fetcher):
    name = "alaska-api"

    def __init__(self, request_delay: tuple[float, float] = (3.0, 8.0)) -> None:
        self.request_delay = request_delay

    def fetch(self, search: Search, start: date, end: date) -> list[AwardDay]:
        raise NotYetImplemented(
            "AlaskaApiFetcher needs the captured endpoint — see recon TODO."
        )
