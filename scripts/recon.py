"""One-off recon: open alaskaair.com in a headed, persistent-profile Chrome,
let the human clear any Akamai challenge, then dump network + screenshots so we
can find the award-calendar endpoint.

Run:  .venv/bin/python scripts/recon.py
A Chrome window opens. If you see a CAPTCHA, solve it; the script waits.
"""
from __future__ import annotations

import json
import pathlib
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "chrome-profile"
OUT = ROOT / "data" / "recon"
PROFILE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

CHALLENGE_MARKERS = ("client challenge", "are you a robot", "enter the characters")


def looks_like_challenge(page) -> bool:
    try:
        title = (page.title() or "").lower()
        if "challenge" in title:
            return True
        body = page.inner_text("body")[:4000].lower()
        return any(m in body for m in CHALLENGE_MARKERS)
    except Exception:
        return False


def wait_out_challenge(page, seconds: int = 300) -> None:
    deadline = time.time() + seconds
    warned = False
    while looks_like_challenge(page) and time.time() < deadline:
        if not warned:
            print(">>> CAPTCHA / challenge visible — solve it in the window. Waiting…", flush=True)
            warned = True
        time.sleep(3)
    if looks_like_challenge(page):
        print(">>> Still challenged after wait; continuing anyway.", flush=True)
    elif warned:
        print(">>> Challenge cleared, thanks.", flush=True)


def main() -> None:
    requests: list[dict] = []
    responses: list[dict] = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            channel="chrome",
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/Los_Angeles",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        page.on("request", lambda r: requests.append(
            {"method": r.method, "url": r.url, "type": r.resource_type}))

        def on_response(r):
            ct = r.headers.get("content-type", "")
            if "json" in ct or "/api/" in r.url or "graphql" in r.url.lower():
                responses.append({"status": r.status, "url": r.url, "ct": ct})
        page.on("response", on_response)

        print("Loading alaskaair.com …", flush=True)
        page.goto("https://www.alaskaair.com/", wait_until="domcontentloaded", timeout=60_000)
        wait_out_challenge(page)
        time.sleep(3)
        page.screenshot(path=str(OUT / "01-home.png"), full_page=True)
        (OUT / "01-home.html").write_text(page.content())

        print(f"\nCaptured {len(requests)} requests, {len(responses)} json/api responses.", flush=True)
        (OUT / "requests.json").write_text(json.dumps(requests, indent=2))
        (OUT / "responses.json").write_text(json.dumps(responses, indent=2))

        print("Leaving the window open 20s for a look…", flush=True)
        time.sleep(20)
        ctx.close()


if __name__ == "__main__":
    main()
