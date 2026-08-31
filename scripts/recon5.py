"""Recon round 5:
  A) Try constructed award results URLs directly (skip the widget entirely).
  B) Enumerate the real search-form controls (roles/ids) piercing shadow DOM.
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

OD = (dt.date.today() + dt.timedelta(days=120)).isoformat()
CANDIDATE_URLS = [
    f"https://www.alaskaair.com/search/results?A=1&C=0&L=0&O=TPE&D=LAX&OD={OD}&RT=false&ShoppingMethod=onlineaward",
    f"https://www.alaskaair.com/search/results?A=1&O=TPE&D=LAX&OD={OD}&RT=false&awardType=MilesOnly",
    f"https://www.alaskaair.com/booking/search-results?origin=TPE&destination=LAX&departureDate={OD}&tripType=OneWay&fareType=award&adults=1",
]
INTERESTING = ("/search/api", "/booking/api", "calendar", "matrix", "shop",
               "flightresults", "availability", "flexible", "price", "results",
               "graphql", "offers", "fare")

log = []
def note(m):
    print(m, flush=True); log.append(str(m))


ENUM_JS = r"""
() => {
  const out = [];
  const visit = (root) => {
    root.querySelectorAll('input,button,select,[role],auro-combobox,auro-input,auro-datepicker,auro-menu,auro-checkbox').forEach(el => {
      out.push({
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        name: el.getAttribute('name'),
        role: el.getAttribute('role'),
        type: el.getAttribute('type'),
        aria: el.getAttribute('aria-label'),
        ph: el.getAttribute('placeholder'),
        slot: el.getAttribute('slot'),
        text: (el.textContent || '').trim().slice(0,45) || null,
      });
      if (el.shadowRoot) visit(el.shadowRoot);
    });
  };
  visit(document);
  return out;
}
"""


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
            if any(k in u for k in INTERESTING) and "jsdelivr" not in u and not u.endswith(".svg"):
                rec = {"status": r.status, "method": r.request.method, "url": r.url,
                       "ct": r.headers.get("content-type", "")}
                try:
                    if "json" in rec["ct"]:
                        body = r.json()
                        n = len(api_hits)
                        (OUT / f"r5-body-{n:02d}.json").write_text(json.dumps(body, indent=2)[:3_000_000])
                        rec["saved"] = f"r5-body-{n:02d}.json"
                        rec["shape"] = list(body.keys()) if isinstance(body, dict) else f"list[{len(body)}]"
                except Exception as e:
                    rec["err"] = str(e)[:150]
                api_hits.append(rec)
                note(f"API {rec['status']} {rec['method']} {r.url[:160]}")
        page.on("response", on_response)

        # ---- A) constructed URLs ----
        for i, url in enumerate(CANDIDATE_URLS):
            note(f"\n--- candidate {i}: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as e:
                note(f"goto err: {e}"); continue
            time.sleep(10)
            note(f"landed: {page.url}")
            page.screenshot(path=str(OUT / f"r5-cand{i}.png"))
            body_txt = ""
            try:
                body_txt = page.inner_text("body")[:600].replace("\n", " ")
            except Exception:
                pass
            note(f"body head: {body_txt}")

        # ---- B) enumerate form ----
        note("\n--- enumerate form on home ---")
        page.goto("https://www.alaskaair.com/", wait_until="domcontentloaded", timeout=60_000)
        time.sleep(6)
        try:
            page.get_by_role("button", name="Dismiss").first.click(timeout=1500)
            time.sleep(1)
        except Exception:
            pass
        page.screenshot(path=str(OUT / "r5-home.png"))
        try:
            els = page.evaluate(ENUM_JS)
        except Exception as e:
            els = [{"error": str(e)}]
        (OUT / "r5-form-elements.json").write_text(json.dumps(els, indent=2))
        note(f"enumerated {len(els)} elements")

        (OUT / "r5-api-hits.json").write_text(json.dumps(api_hits, indent=2))
        (OUT / "r5-log.txt").write_text("\n".join(log))
        note("DONE")
        time.sleep(6)
        ctx.close()


if __name__ == "__main__":
    main()
