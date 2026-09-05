"""Playwright fetcher for the Alaska (Atmos Rewards) award pages.

Two server-rendered pages, hit directly (no widget interaction):

  MONTH CALENDAR — one load = a whole month of the lowest <cabin> award price
  per day (any routing, incl. connections):
    /search/calendar?O={o}&D={d}&OD={mid}&A={pax}&RT=false
      &RequestType=Calendar&ShoppingMethod=onlineaward
      &CM={yyyy-mm}&FareType={Main|Premium|Business|First}

  RESULTS — the full per-flight fare grid for one date, used only to *confirm*
  a candidate day the calendar flagged at/under target:
    /search/results?A={pax}&C=0&L=0&O={o}&D={d}&OD={yyyy-mm-dd}
      &RT=false&ShoppingMethod=onlineaward

So a full sweep is ~1 calendar load per route-month plus a handful of
confirmations, instead of one load per day.

We navigate with a real persistent-profile Chrome to satisfy Akamai, then parse
page.content() with lxml. One context is reused for the whole sweep. If Akamai
shows its "client challenge" we raise ChallengeRequired — never solve it.
"""
from __future__ import annotations

import random
import re
import time
from datetime import date, datetime, timedelta

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
CALENDAR_URL = (
    "https://www.alaskaair.com/search/calendar"
    "?O={o}&D={d}&OD={mid}&A={pax}&RT=false&RequestType=Calendar"
    "&ShoppingMethod=onlineaward&int=flightresultsmicrosite%3Aviewby-calendar"
    "&locale=en-us&CM={cm}&FareType={fare}"
)

# Alaska cabin label -> our vocabulary
_CABIN = {"main": "economy", "saver": "economy", "premium": "premium",
          "first": "first", "business": "business"}
# our vocabulary -> calendar FareType param
_FARETYPE = {"economy": "Main", "premium": "Premium",
             "business": "Business", "first": "First"}

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
                 confirm_candidates: bool = True,
                 headed_challenge_wait_s: int = 180) -> None:
        self.profile_dir = profile_dir
        self.headless = headless
        self.request_delay = request_delay
        self.nav_timeout_ms = nav_timeout_ms
        self.confirm_candidates = confirm_candidates
        self.headed_challenge_wait_s = headed_challenge_wait_s
        self._pw = None
        self._ctx = None
        self._page = None

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

        cal = self._calendar_scan(search, start, end)
        candidates = sorted(
            d for d, (mi, _tx) in cal.items()
            if start <= d <= end and mi is not None and mi <= search.max_miles
        )
        log.info("calendar_scan", search=search.name, days=len(cal),
                 candidates=len(candidates),
                 dates=[d.isoformat() for d in candidates][:10])

        out: list[AwardDay] = []
        for day in candidates:
            if self.confirm_candidates:
                out.extend(self._fetch_day(search, day))
            else:
                mi, tx = cal[day]
                out.append(AwardDay(
                    search_name=search.name, origin=search.origin,
                    destination=search.destination, depart_date=day,
                    cabin=search.cabin, carrier=search.carrier, miles=mi,
                    taxes_usd=tx, seats=None, nonstop=True,
                    raw={"source": "calendar", "unconfirmed": True},
                ))
            time.sleep(random.uniform(*self.request_delay))
        return out

    def _calendar_scan(self, search: Search, start: date,
                       end: date) -> dict[date, tuple[int | None, float | None]]:
        """One calendar page load per month spanning [start, end]."""
        fare = _FARETYPE.get(search.cabin, "Business")
        out: dict[date, tuple[int | None, float | None]] = {}
        month = start.replace(day=1)
        while month <= end:
            cm = month.strftime("%Y-%m")
            url = CALENDAR_URL.format(o=search.origin, d=search.destination,
                                      mid=f"{cm}-15", pax=search.passengers,
                                      cm=cm, fare=fare)
            try:
                self._page.goto(url, wait_until="domcontentloaded",
                                timeout=self.nav_timeout_ms)
                self._raise_if_challenged(url)
                try:
                    self._page.wait_for_selector('[data-testid="loaded-calendar"]',
                                                 timeout=20_000)
                except PWTimeout:
                    self._raise_if_challenged(url)
                    log.warning("calendar_no_grid", search=search.name, cm=cm)
                else:
                    for d, (mi, tx) in parse_calendar(self._page.content()).items():
                        if start <= d <= end:
                            out[d] = (mi, tx)
            except ChallengeRequired:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("calendar_nav_failed", search=search.name, cm=cm,
                            error=str(exc))
            month = _next_month(month)
            time.sleep(random.uniform(*self.request_delay))
        return out

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

    def _challenged(self) -> bool:
        try:
            blob = ((self._page.title() or "") + " "
                    + self._page.inner_text("body")[:3000]).lower()
        except Exception:
            return False
        return "challenge" in blob or any(m in blob for m in _CHALLENGE_MARKERS)

    def _raise_if_challenged(self, url: str) -> None:
        if not self._challenged():
            return
        # Headed run: give the human a chance to solve it in the visible window
        # before we bail and make the scheduler wait out a cooldown.
        if not self.headless and self.headed_challenge_wait_s > 0:
            log.warning("challenge_waiting", url=url,
                        wait_s=self.headed_challenge_wait_s)
            deadline = time.time() + self.headed_challenge_wait_s
            while self._challenged() and time.time() < deadline:
                time.sleep(3)
            if not self._challenged():
                # Akamai's redirect-back after solving doesn't reliably honor the
                # original query string (we've seen it settle on a default month
                # instead of the requested CM=/FareType=). Force a clean reload
                # of the exact URL rather than trusting whatever's on screen.
                try:
                    self._page.goto(url, wait_until="domcontentloaded",
                                    timeout=self.nav_timeout_ms)
                except Exception as exc:  # noqa: BLE001
                    log.warning("post_challenge_reload_failed", url=url, error=str(exc))
                if self._challenged():
                    raise ChallengeRequired(url)
                log.info("challenge_cleared")
                return
        raise ChallengeRequired(url)


def _next_month(d: date) -> date:
    return d.replace(year=d.year + 1, month=1, day=1) if d.month == 12 \
        else d.replace(month=d.month + 1, day=1)


# -- parsing (module-level so it can be unit-tested against saved HTML) --------
_CAL_LABEL = re.compile(
    r"(?:Selected,\s*)?\w+,\s*([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})\.\s*"
    r"(?:Fare:\s*([\d.]+)k\s*\+\s*\$([\d,]+)|Unavailable)"
)


def parse_calendar(html_text: str) -> dict[date, tuple[int | None, float | None]]:
    """Month-calendar page -> {date: (lowest_award_miles, taxes_usd)}.

    'Unavailable' days map to (None, None). The price is the lowest for the
    chosen FareType across *any* routing (nonstop or connecting).
    """
    tree = lxml_html.fromstring(html_text)
    grids = tree.cssselect('[data-testid="loaded-calendar"]')
    scope = grids[0] if grids else tree
    out: dict[date, tuple[int | None, float | None]] = {}

    for btn in scope.cssselect('button[role="gridcell"]'):
        label = _norm(btn.get("aria-label"))
        m = _CAL_LABEL.search(label)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%b %d, %Y").date()
        except ValueError:
            try:
                d = datetime.strptime(m.group(1), "%B %d, %Y").date()
            except ValueError:
                continue
        if m.group(2) is None:  # "Unavailable"
            out[d] = (None, None)
            continue
        miles = int(round(float(m.group(2)) * 1000))
        taxes = float(m.group(3).replace(",", "")) if m.group(3) else None
        out[d] = (miles, taxes)
    return out


def parse_results(search: Search, day: date, html_text: str) -> list[AwardDay]:
    tree = lxml_html.fromstring(html_text)
    out: list[AwardDay] = []
    seen: set[tuple] = set()  # collapse identical itinerary cards

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

            dedup_key = (fno_carrier, fno_num, cabin, miles, stops,
                         _parse_usd(ptext))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

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
