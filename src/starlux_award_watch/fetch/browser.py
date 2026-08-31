"""Playwright fetcher for the Alaska (Atmos Rewards) award results page.

We hit the results URL directly (no widget interaction needed):

    https://www.alaskaair.com/search/results
        ?A={pax}&C=0&L=0&O={origin}&D={dest}&OD={yyyy-mm-dd}
        &RT=false&ShoppingMethod=onlineaward

The flight list is server-rendered into the HTML, so we navigate with a real
(persistent-profile) Chrome to satisfy Akamai, then parse page.content() with
lxml. One browser context is reused for a whole sweep.

If Akamai shows its "client challenge" we raise ChallengeRequired so the
scheduler can alert the human and back off — we never try to solve it.
"""
from __future__ import annotations

import random
import re
import time
from datetime import date, timedelta

import structlog
from lxml import html as lxml_html
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from ..config import Search
from .base import AwardDay, Fetcher

log = structlog.get_logger()

RESULTS_URL = (
    "https://www.alaskaair.com/search/results"
    "?A={pax}&C=0&L=0&O={o}&D={d}&OD={od}&RT=false&ShoppingMethod=onlineaward"
)

# Alaska cabin label -> our vocabulary
_CABIN = {"main": "economy", "saver": "economy", "premium": "premium",
          "first": "first", "business": "business"}

_CHALLENGE_MARKERS = ("client challenge", "are you a robot",
                      "enter the characters seen in the image")


class ChallengeRequired(RuntimeError):
    """Akamai served a CAPTCHA; a human must clear it in the profile browser."""

    def __init__(self, url: str) -> None:
        super().__init__(f"Akamai challenge at {url}")
        self.url = url


def _parse_miles(text: str) -> int | None:
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*k", text, re.I)
    if m:
        return int(round(float(m.group(1).replace(",", "")) * 1000))
    m = re.search(r"\b(\d[\d,]{3,})\b", text)  # bare "45000"
    return int(m.group(1).replace(",", "")) if m else None


def _parse_usd(text: str) -> float | None:
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", text)
    return float(m.group(1).replace(",", "")) if m else None


def _parse_seats(text: str) -> int | None:
    m = re.search(r"last\s+(\d+)\s+seat", text, re.I)
    return int(m.group(1)) if m else None


class AlaskaBrowserFetcher(Fetcher):
    name = "alaska-browser"

    def __init__(self, profile_dir: str, headless: bool = True,
                 request_delay: tuple[float, float] = (3.0, 8.0),
                 nav_timeout_ms: int = 45_000,
                 shoulder_prefilter: bool = True) -> None:
        self.profile_dir = profile_dir
        self.headless = headless
        self.request_delay = request_delay
        self.nav_timeout_ms = nav_timeout_ms
        self.shoulder_prefilter = shoulder_prefilter
        self._pw = None
        self._ctx = None
        self._page = None
        self._last_shoulder: dict[str, int | None] = {}

    # -- lifecycle -------------------------------------------------------------
    def _ensure(self):
        if self._page is not None:
            return
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            channel="chrome",
            headless=self.headless,
            viewport={"width": 1440, "height": 950},
            locale="en-US",
            timezone_id="America/Los_Angeles",
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self._page.set_default_timeout(self.nav_timeout_ms)
        self._page.on("response", self._capture_shoulder)

    def _capture_shoulder(self, resp) -> None:
        if "shoulderDates" not in resp.url:
            return
        try:
            data = resp.json()
        except Exception:
            return
        rows = data.get("calendarDates") or data.get("shoulderDates") or []
        got: dict[str, int | None] = {}
        for r in rows:
            d = r.get("date")
            if d:
                got[d] = r.get("awardPoints")
        if got:
            self._last_shoulder = got

    def close(self):
        for obj, meth in ((self._ctx, "close"), (self._pw, "stop")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass
        self._pw = self._ctx = self._page = None

    # -- Fetcher API --------------------------------------------------------
    def fetch(self, search: Search, start: date, end: date) -> list[AwardDay]:
        self._ensure()
        out: list[AwardDay] = []

        skip: set[date] = set()
        if self.shoulder_prefilter and (end - start).days >= 20:
            cheapest = self._cheapest_by_date(search, start, end)
            for d, mi in cheapest.items():
                # business can't be cheaper than the cheapest cabin shown, so if
                # even that is over target, no point loading the full page.
                if mi is not None and mi > search.max_miles:
                    skip.add(d)
            log.info("shoulder_prefilter", search=search.name,
                     covered=len(cheapest), skipped=len(skip))

        day = start
        while day <= end:
            if day in skip:
                day += timedelta(days=1)
                continue
            out.extend(self._fetch_day(search, day))
            day += timedelta(days=1)
            time.sleep(random.uniform(*self.request_delay))
        return out

    def _cheapest_by_date(self, search: Search, start: date,
                          end: date) -> dict[date, int | None]:
        """Harvest the 31-day 'shoulderDates' strip in ~28-day strides so we
        learn the cheapest award per day with ~1 page load per month."""
        out: dict[date, int | None] = {}
        center = start + timedelta(days=15)
        while center <= end + timedelta(days=15):
            self._last_shoulder = {}
            url = RESULTS_URL.format(pax=search.passengers, o=search.origin,
                                     d=search.destination, od=center.isoformat())
            try:
                self._page.goto(url, wait_until="domcontentloaded",
                                timeout=self.nav_timeout_ms)
                self._raise_if_challenged(url)
                self._page.wait_for_timeout(3500)  # let shoulderDates POST land
            except ChallengeRequired:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("shoulder_nav_failed", center=str(center), error=str(exc))
            for ds, mi in self._last_shoulder.items():
                try:
                    out[date.fromisoformat(ds)] = mi
                except ValueError:
                    continue
            center += timedelta(days=28)
            time.sleep(random.uniform(*self.request_delay))
        return {d: v for d, v in out.items() if start <= d <= end}

    # -- one day ------------------------------------------------------------
    def _fetch_day(self, search: Search, day: date) -> list[AwardDay]:
        page = self._page
        url = RESULTS_URL.format(pax=search.passengers, o=search.origin,
                                 d=search.destination, od=day.isoformat())
        page.goto(url, wait_until="domcontentloaded", timeout=self.nav_timeout_ms)
        self._raise_if_challenged(url)

        try:
            page.wait_for_selector('[data-testid="flight-card-fares-v2"]', timeout=20_000)
        except PWTimeout:
            self._raise_if_challenged(url)
            body = (page.inner_text("body")[:2000] if page else "").lower()
            if "no flights" in body or "we couldn't find" in body or "no results" in body:
                return []
            log.warning("no_fare_grid", search=search.name, day=str(day), url=url)
            return []

        return parse_results(search, day, page.content())

    def _raise_if_challenged(self, url: str) -> None:
        page = self._page
        try:
            blob = ((page.title() or "") + " " + page.inner_text("body")[:3000]).lower()
        except Exception:
            return
        if "challenge" in blob or any(m in blob for m in _CHALLENGE_MARKERS):
            raise ChallengeRequired(url)


# -- parsing (module-level so it can be unit-tested against saved HTML) --------
def parse_results(search: Search, day: date, html_text: str) -> list[AwardDay]:
    tree = lxml_html.fromstring(html_text)
    out: list[AwardDay] = []

    for grp in tree.cssselect('[data-testid="flight-card-fares-v2"]'):
        labelled = grp.get("aria-labelledby", "")
        idx = labelled.rsplit("-", 1)[-1] if labelled else None
        if idx is None:
            continue
        card = _closest(grp, f"flight-card-{idx}")
        if card is None:
            continue

        stops = _stops(card, idx)
        fno_carrier, fno_num = _flight_number(card)
        dep_code, arr_code = _airport_codes(card)
        dep_time = _text1(card, '[data-testid="departure-time"]')
        arr_time = _text1(card, '[data-testid="arrival-time"]')

        for tile in card.cssselect("button.fare-tile"):
            cls = " ".join(tile.get("class", "").split())
            mcab = re.search(r"fare-tile--(\w+)", cls)
            cos = _text1(tile, ".cos-primary") or (mcab.group(1) if mcab else "")
            cabin = _CABIN.get(cos.strip().lower(), cos.strip().lower())
            if cabin != search.cabin:
                continue

            price_el = tile.cssselect('[data-testid="award-price"]')
            if not price_el:
                continue  # Unavailable / sold out
            ptext = _norm(price_el[0].text_content())
            miles = _parse_miles(ptext)
            if miles is None:
                continue

            out.append(AwardDay(
                search_name=search.name,
                origin=dep_code or search.origin,
                destination=arr_code or search.destination,
                depart_date=day,
                cabin=cabin,
                carrier=(fno_carrier or "").upper(),
                miles=miles,
                taxes_usd=_parse_usd(ptext),
                seats=_parse_seats(_norm(tile.text_content())),
                nonstop=(stops == 0),
                raw={"flight": f"{fno_carrier} {fno_num}".strip(),
                     "stops": stops, "dep": dep_time, "arr": arr_time,
                     "price_text": ptext},
            ))
    return out


# -- lxml helpers -----------------------------------------------------------
def _closest(el, testid: str):
    node = el
    while node is not None:
        if node.get("data-testid") == testid:
            return node
        node = node.getparent()
    # fall back: search whole tree
    root = el.getroottree().getroot()
    found = root.cssselect(f'[data-testid="{testid}"]')
    return found[0] if found else None


def _stops(card, idx: str) -> int:
    for d in card.cssselect(f'[data-testid^="flight-details-{idx}-stops-"]'):
        m = re.search(r"stops-(\d+)$", d.get("data-testid", ""))
        if m:
            return int(m.group(1))
    txt = _norm(card.text_content()).lower()
    if "nonstop" in txt:
        return 0
    m = re.search(r"(\d+)\s+stop", txt)
    return int(m.group(1)) if m else 0


def _flight_number(card) -> tuple[str, str]:
    fn = _text1(card, ".flight-number")
    if fn:
        m = re.match(r"([A-Z0-9]{2})\s*(\d+)", fn.strip())
        if m:
            return m.group(1), m.group(2)
    disc = _text1(card, ".disclosure-text") or ""
    m = re.search(r"\b([A-Z0-9]{2})\s*(\d+)\s*[—-]\s*Operated by", disc)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def _airport_codes(card) -> tuple[str, str]:
    codes = [_norm(e.text_content()) for e in card.cssselect(".airport-code")]
    codes = [c for c in codes if re.fullmatch(r"[A-Z]{3}", c or "")]
    if len(codes) >= 2:
        return codes[0], codes[-1]
    return "", ""


def _text1(scope, css: str) -> str | None:
    els = scope.cssselect(css)
    return _norm(els[0].text_content()) if els else None


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()
