"""Recon round 2: warm profile is in data/chrome-profile now. Load the home page,
map the search widget's fields, and dump interactive elements so we can script
a real TPE->LAX award search next.
"""
from __future__ import annotations

import json
import pathlib
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "chrome-profile"
OUT = ROOT / "data" / "recon"
OUT.mkdir(parents=True, exist_ok=True)

DUMP_JS = r"""
() => {
  const pick = el => ({
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type'),
    id: el.id || null,
    name: el.getAttribute('name'),
    role: el.getAttribute('role'),
    aria: el.getAttribute('aria-label'),
    ph: el.getAttribute('placeholder'),
    text: (el.innerText || '').trim().slice(0, 40) || null,
    datatest: el.getAttribute('data-testid') || el.getAttribute('data-test') || null,
  });
  const els = [...document.querySelectorAll('input,button,select,[role=combobox],[role=button],a[href*="search"]')];
  return els.map(pick).filter(e => e.aria || e.name || e.id || e.text || e.ph || e.datatest);
}
"""


def main() -> None:
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
        page.goto("https://www.alaskaair.com/", wait_until="domcontentloaded", timeout=60_000)
        time.sleep(6)

        # dismiss cookie banner if present
        for label in ("Dismiss", "Accept", "Close"):
            try:
                page.get_by_role("button", name=label, exact=False).first.click(timeout=1500)
                break
            except Exception:
                pass

        time.sleep(2)
        page.screenshot(path=str(OUT / "02-home-top.png"))  # viewport only
        try:
            els = page.evaluate(DUMP_JS)
        except Exception as e:
            els = [{"error": str(e)}]
        (OUT / "02-elements.json").write_text(json.dumps(els, indent=2))
        print(f"dumped {len(els)} elements -> data/recon/02-elements.json")

        # Also try the "Book" / flights tab area text
        try:
            print("PAGE TITLE:", page.title())
        except Exception:
            pass
        time.sleep(15)
        ctx.close()


if __name__ == "__main__":
    main()
