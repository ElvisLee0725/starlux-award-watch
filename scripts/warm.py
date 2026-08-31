"""Open the bot's Chrome profile and wait for the human to clear any Akamai
challenge. Run this whenever the monitor sends a 'CAPTCHA' alert.

    .venv/bin/python scripts/warm.py
"""
from __future__ import annotations

import pathlib
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "chrome-profile"
MARKERS = ("client challenge", "are you a robot", "enter the characters")


def challenged(page) -> bool:
    try:
        if "challenge" in (page.title() or "").lower():
            return True
        return any(m in page.inner_text("body")[:4000].lower() for m in MARKERS)
    except Exception:
        return False


def main() -> None:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=False,
            viewport={"width": 1440, "height": 900}, locale="en-US",
            timezone_id="America/Los_Angeles",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.alaskaair.com/search/results"
                  "?A=1&C=0&L=0&O=TPE&D=LAX&OD=2027-03-01&RT=false&ShoppingMethod=onlineaward",
                  wait_until="domcontentloaded", timeout=60_000)

        waited = 0
        while challenged(page) and waited < 600:
            if waited == 0:
                print(">>> Solve the CAPTCHA in the window. Waiting…", flush=True)
            time.sleep(3)
            waited += 3

        if challenged(page):
            print(">>> Still challenged after 10 min — giving up.", flush=True)
        else:
            print(">>> Clear. Profile is warm. Closing in 15s.", flush=True)
            time.sleep(15)
        ctx.close()


if __name__ == "__main__":
    main()
