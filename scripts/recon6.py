"""Recon 6: dump a results-page HTML and locate the embedded flight/fare data,
so we know whether to parse the DOM or an inline JSON island (and whether a
plain curl_cffi request with warm cookies could work instead of Playwright).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "chrome-profile"
OUT = ROOT / "data" / "recon"

OD = (dt.date.today() + dt.timedelta(days=120)).isoformat()
URL = (f"https://www.alaskaair.com/search/results?A=1&C=0&L=0&O=TPE&D=LAX"
       f"&OD={OD}&RT=false&ShoppingMethod=onlineaward")


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=False,
            viewport={"width": 1440, "height": 950}, locale="en-US",
            timezone_id="America/Los_Angeles",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        shoulder = {}
        def on_response(r):
            if "shoulderDates" in r.url:
                try:
                    shoulder.update(r.json())
                except Exception:
                    pass
        page.on("response", on_response)

        print("goto", URL, flush=True)
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        # wait for flight cards to render
        for _ in range(20):
            time.sleep(1.5)
            if page.locator("text=Operated by").count() > 0:
                break
        time.sleep(3)

        html = page.content()
        (OUT / "r6-results.html").write_text(html)
        print("saved r6-results.html", len(html), flush=True)

        # cookies (for a later curl_cffi test)
        cookies = ctx.cookies()
        (OUT / "r6-cookies.json").write_text(json.dumps(cookies, indent=2))
        ck = "; ".join(f"{c['name']}={c['value']}" for c in cookies
                       if c["domain"].endswith("alaskaair.com"))
        (OUT / "r6-cookie-header.txt").write_text(ck)
        print(f"saved {len(cookies)} cookies", flush=True)

        # look for inline JSON islands
        for pat, label in [
            (r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', "application/json script"),
            (r'__sveltekit[^=]*=\s*({.*?});', "sveltekit assignment"),
            (r'type="application/ld\+json"', "ld+json"),
            (r'\\"awardPoints\\"|"awardPoints"', "awardPoints token"),
            (r'"fareType"|"cabin"|"Business"', "fare tokens"),
            (r'"flightSegments"\s*:\s*\[[^\]]', "flightSegments non-empty"),
            (r'kaiser|ita|solutionSet|solutionId', "engine tokens"),
        ]:
            hits = list(re.finditer(pat, html, re.S))
            print(f"  [{label}] {len(hits)} match(es)", flush=True)
            if hits and label in ("application/json script", "sveltekit assignment",
                                  "flightSegments non-empty"):
                seg = hits[0].group(0)[:600]
                print("    sample:", seg.replace("\n", " ")[:400], flush=True)

        # dump visible flight rows via DOM text
        try:
            rows = page.locator("xpath=//*[contains(text(),'Operated by')]/ancestor::*[self::li or self::article or self::div][1]")
            n = min(rows.count(), 4)
            for i in range(n):
                print(f"--- row {i} ---\n{rows.nth(i).inner_text()[:500]}", flush=True)
        except Exception as e:
            print("row dump fail:", e, flush=True)

        print("SHOULDER sample:", json.dumps(shoulder.get("calendarDates", [])[:3], indent=2), flush=True)
        (OUT / "r6-done.txt").write_text("done")
        time.sleep(5)
        ctx.close()


if __name__ == "__main__":
    main()
