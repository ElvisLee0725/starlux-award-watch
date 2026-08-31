"""Recon round 3: drive a real award search and capture the results URL + APIs.

TPE -> LAX, one way, "Use points", date ~300 days out, plus the flexible-dates
calendar. Saves response bodies for anything on alaskaair.com/search or with
calendar/matrix/shop in the URL.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "chrome-profile"
OUT = ROOT / "data" / "recon"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = (dt.date.today() + dt.timedelta(days=300))
INTERESTING = ("/search/api", "calendar", "matrix", "shop", "flightresults",
               "availability", "flexible", "fareprep", "price")

log: list[str] = []
def note(m: str) -> None:
    print(m, flush=True)
    log.append(m)


def main() -> None:
    api_hits: list[dict] = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=False,
            viewport={"width": 1440, "height": 950}, locale="en-US",
            timezone_id="America/Los_Angeles",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(r):
            u = r.url
            if any(k in u.lower() for k in INTERESTING):
                rec = {"status": r.status, "method": r.request.method, "url": u,
                       "ct": r.headers.get("content-type", "")}
                try:
                    if "json" in rec["ct"]:
                        body = r.json()
                        rec["body_keys"] = list(body.keys()) if isinstance(body, dict) else f"list[{len(body)}]"
                        fn = OUT / f"body-{len(api_hits):02d}.json"
                        fn.write_text(json.dumps(body, indent=2)[:2_000_000])
                        rec["saved"] = fn.name
                except Exception as e:
                    rec["err"] = str(e)
                api_hits.append(rec)
                note(f"API {rec['status']} {rec['method']} {u[:130]}")
        page.on("response", on_response)

        note("home…")
        page.goto("https://www.alaskaair.com/", wait_until="domcontentloaded", timeout=60_000)
        time.sleep(5)
        for label in ("Dismiss", "Accept all", "Accept"):
            try:
                page.get_by_role("button", name=label).first.click(timeout=1200); break
            except Exception:
                pass

        # one way
        try:
            page.get_by_text("One way", exact=True).click(timeout=4000); note("clicked One way")
        except Exception as e:
            note(f"one-way fail: {e}")
        time.sleep(1)

        # From / To  (Auro comboboxes — try role, then label text)
        def fill_place(which: str, value: str):
            for how in (
                lambda: page.get_by_role("combobox", name=which),
                lambda: page.get_by_label(which, exact=False),
                lambda: page.get_by_placeholder(which),
                lambda: page.get_by_text(which, exact=True),
            ):
                try:
                    el = how()
                    el.click(timeout=2500)
                    page.keyboard.type(value, delay=90)
                    time.sleep(1.8)
                    page.keyboard.press("Enter")
                    note(f"{which} <- {value} via {how.__name__ if hasattr(how,'__name__') else how}")
                    return
                except Exception:
                    continue
            note(f"could not fill {which}")

        fill_place("From", "TPE")
        time.sleep(1)
        fill_place("To", "LAX")
        time.sleep(1)

        # Use points
        for how in (lambda: page.get_by_text("Use points", exact=True),
                    lambda: page.get_by_role("checkbox", name="Use points")):
            try:
                how().click(timeout=3000); note("checked Use points"); break
            except Exception:
                pass

        # Flexible dates
        for how in (lambda: page.get_by_text("Flexible dates", exact=True),
                    lambda: page.get_by_role("checkbox", name="Flexible dates")):
            try:
                how().click(timeout=3000); note("checked Flexible dates"); break
            except Exception:
                pass

        # Dates
        try:
            page.get_by_text("Dates", exact=True).click(timeout=4000)
            time.sleep(1.5)
            page.screenshot(path=str(OUT / "03a-datepicker.png"))
            # try typing into a visible date input
            filled = False
            for sel in ("input[type=text]", "auro-input input", "[role=textbox]"):
                try:
                    inp = page.locator(sel).last
                    inp.fill(TARGET.strftime("%m/%d/%Y"), timeout=2000)
                    filled = True
                    note(f"typed date {TARGET} into {sel}")
                    break
                except Exception:
                    continue
            if not filled:
                note("date typing failed; will rely on default/next screenshot")
            page.keyboard.press("Escape")
        except Exception as e:
            note(f"dates fail: {e}")

        time.sleep(1)
        page.screenshot(path=str(OUT / "03b-form-filled.png"))

        # Submit
        for how in (lambda: page.get_by_role("button", name="Search flights"),
                    lambda: page.get_by_text("Search flights", exact=True)):
            try:
                how().click(timeout=4000); note("submitted"); break
            except Exception:
                pass

        # wait for results
        for i in range(20):
            time.sleep(2)
            if "/search/results" in page.url or "book" in page.url:
                break
        note(f"RESULTS URL: {page.url}")
        time.sleep(8)
        page.screenshot(path=str(OUT / "03c-results.png"), full_page=True)
        (OUT / "03-results-url.txt").write_text(page.url)
        (OUT / "03-api-hits.json").write_text(json.dumps(api_hits, indent=2))
        (OUT / "03-log.txt").write_text("\n".join(log))
        note(f"{len(api_hits)} interesting API hits captured")
        time.sleep(10)
        ctx.close()


if __name__ == "__main__":
    main()
