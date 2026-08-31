"""Recon round 4: fill the search widget with coordinate clicks + keyboard,
screenshotting every step. Goal: reach the results page and capture the
award-pricing / calendar API call and the results URL format.
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

TARGET = dt.date.today() + dt.timedelta(days=300)
INTERESTING = ("/search/api", "calendar", "matrix", "shop", "flightresults",
               "availability", "flexible", "fareprep", "price", "results", "graphql")

log: list[str] = []
def note(m):
    print(m, flush=True); log.append(str(m))


def main():
    api_hits = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=False,
            viewport={"width": 1440, "height": 950}, locale="en-US",
            timezone_id="America/Los_Angeles",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(r):
            u = r.url.lower()
            if any(k in u for k in INTERESTING) and "cdn.jsdelivr" not in u and ".svg" not in u:
                rec = {"status": r.status, "method": r.request.method, "url": r.url,
                       "ct": r.headers.get("content-type", "")}
                try:
                    if "json" in rec["ct"]:
                        body = r.json()
                        n = len(api_hits)
                        (OUT / f"r4-body-{n:02d}.json").write_text(json.dumps(body, indent=2)[:3_000_000])
                        rec["saved"] = f"r4-body-{n:02d}.json"
                        rec["shape"] = (list(body.keys()) if isinstance(body, dict)
                                        else f"list[{len(body)}]")
                except Exception as e:
                    rec["err"] = str(e)[:200]
                api_hits.append(rec)
                note(f"API {rec['status']} {rec['method']} {r.url[:150]}")
        page.on("response", on_response)

        page.goto("https://www.alaskaair.com/", wait_until="domcontentloaded", timeout=60_000)
        time.sleep(6)
        try:
            page.get_by_role("button", name="Dismiss").first.click(timeout=1500)
        except Exception:
            pass

        def shot(name):
            page.screenshot(path=str(OUT / f"r4-{name}.png"))
            note(f"shot {name}")

        shot("00-loaded")

        # One way
        page.mouse.click(236, 358); time.sleep(0.8); note("click One way")

        # From pill
        page.mouse.click(231, 418); time.sleep(1.0)
        page.keyboard.type("TPE", delay=110); time.sleep(2.2)
        shot("01-from-typed")
        page.keyboard.press("ArrowDown"); time.sleep(0.4)
        page.keyboard.press("Enter"); time.sleep(1.0)
        shot("02-from-picked")

        # To pill
        page.mouse.click(545, 418); time.sleep(1.0)
        page.keyboard.type("LAX", delay=110); time.sleep(2.2)
        shot("03-to-typed")
        page.keyboard.press("ArrowDown"); time.sleep(0.4)
        page.keyboard.press("Enter"); time.sleep(1.0)
        shot("04-to-picked")

        # Use points  (checkbox near x=338 y=688)
        page.mouse.click(338, 688); time.sleep(0.6); note("click Use points")

        # Dates
        page.mouse.click(388, 534); time.sleep(1.5)
        shot("05-datepicker")
        typed = False
        for ph in ("mm/dd/yyyy", "MM/DD/YYYY", "Depart"):
            try:
                loc = page.get_by_placeholder(ph).first
                loc.fill(TARGET.strftime("%m/%d/%Y"), timeout=1800)
                typed = True; note(f"typed date via placeholder {ph}")
                break
            except Exception:
                continue
        if not typed:
            # click a day cell: navigate forward ~10 months then pick day 15
            for _ in range(10):
                try:
                    page.get_by_role("button", name="Next month").first.click(timeout=800)
                    time.sleep(0.25)
                except Exception:
                    break
            shot("06-datepicker-advanced")
            try:
                page.get_by_role("button", name="15").first.click(timeout=1500)
                note("clicked day 15")
            except Exception as e:
                note(f"day click fail: {e}")
        page.keyboard.press("Escape"); time.sleep(0.6)
        shot("07-form-ready")

        # Search flights button
        page.mouse.click(388, 865); time.sleep(1.0); note("click Search flights (coord)")
        try:
            page.get_by_role("button", name="Search flights").first.click(timeout=2500)
            note("click Search flights (role)")
        except Exception:
            pass

        for _ in range(25):
            time.sleep(2)
            if "results" in page.url.lower() or "/book" in page.url.lower():
                break
        note(f"RESULTS URL: {page.url}")
        time.sleep(8)
        shot("08-results")
        try:
            page.screenshot(path=str(OUT / "r4-08-results-full.png"), full_page=True)
        except Exception:
            pass

        (OUT / "r4-results-url.txt").write_text(page.url)
        (OUT / "r4-api-hits.json").write_text(json.dumps(api_hits, indent=2))
        (OUT / "r4-log.txt").write_text("\n".join(log))
        note(f"DONE — {len(api_hits)} api hits")
        time.sleep(8)
        ctx.close()


if __name__ == "__main__":
    main()
