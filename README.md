# starlux-award-watch

Watches the **Alaska Airlines award calendar** for **Starlux (JX) business-class
saver space** on `TPE ↔ LAX` and `TPE ↔ ONT`, and **texts you** the moment a day
prices at or below your target (75,000 miles). The lone saver seat on these
flights gets taken fast, so speed of notification is the whole point.

## Status

**Fetcher works against live Alaska/Atmos data.** Recon nailed down the direct
results URL and DOM contract; `fetch/browser.py` navigates per date with a warm
persistent Chrome profile and parses the flight cards. A live probe confirms
nonstop `JX 2` business at 75k is flagged as a hit and connections / non-JX
carriers / 175k fares are rejected.

Left to do: Twilio creds in `.env`; verify `TPE↔ONT` nonstop; tune pacing for
the full ~330-day sweep (CAPTCHA risk over ~1300 navs); exercise the scheduler
`loop()`; `Dockerfile` + deploy to the home box.

## How it works

1. **Fetch** — for each search, read the miles-per-day grid from Alaska across
   the whole booking window (`fetch/api.py`, `curl_cffi`; `fetch/browser.py`
   Playwright fallback if Akamai blocks the direct call).
2. **Match** (`match.py`) — keep only days that are Starlux, nonstop, in the
   right cabin, at/under `max_miles`, under `max_taxes_usd`, with enough seats.
3. **Dedup** (`store.py`, SQLite) — alert once per new hit; again only on a price
   drop or if it's still there after `renotify_after_hours`.
4. **Notify** (`notify.py`) — Twilio SMS with route, date, miles, taxes, seats.
5. **Schedule** (`scheduler.py`) — full sweeps every `full_sweep_minutes`, plus
   frequent `far_edge` passes over the newest bookable dates (where the saver
   seat first appears).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,browser]"
cp .env.example .env         # fill in Twilio creds
$EDITOR config.yaml          # routes, targets, cadence
```

## Run

```bash
python -m starlux_award_watch --once --dry-run   # one sweep, print instead of SMS
python -m starlux_award_watch                     # the real loop
```

## Deploy

Target is a small always-on cloud VM (Docker). `Dockerfile` TBD once fetch works.
Running on a laptop only checks while the laptop is awake and the process is up —
not suitable for catching space that appears overnight.

## Notes

- Not affiliated with Alaska Airlines or Starlux. For personal use; respect the
  sites' terms and keep polling gentle (`request_delay_seconds`, `jitter_pct`).
- Alaska's partner booking window is ~330 days; occasionally Starlux loads closer
  to 350. `window.max_days_ahead` controls how far we probe.
