# starlux-award-watch

Watches the **Alaska Airlines award calendar** for **Starlux (JX) business-class
saver space** on `TPE ↔ LAX` and `TPE ↔ ONT`, and **pushes your phone** the
moment a day prices at or below your target (75,000 miles). The lone saver seat
on these flights gets taken fast, so speed of notification is the whole point.

## Status

**Working end to end.** Live-verified: the month-calendar scan flags candidate
days, the confirmation load parses all four route legs (`JX 2` nonstop TPE↔LAX,
`JX 10` nonstop TPE↔ONT), the matcher keeps nonstop Starlux business ≤ 75k and
rejects connections / non-JX / 175k, SQLite dedup fires once then stays quiet,
the scheduler loop runs full sweep + far-edge, and a Pushover push (emergency
priority) lands on the phone. 24 tests.

Alerts: **Pushover** (Twilio abandoned — trial suspended, upgrade now demands an
ID upload). Deploy: **macOS LaunchAgent** on an always-on Mac — see
`deploy/README.md`. Known gap: that Mac isn't online 24/7, so coverage has
holes; it resumes on wake.

To go live: fill `.env` (`PUSHOVER_*`), then `./deploy/install-macos.sh`.

## How it works

1. **Calendar scan** (`fetch/browser.py`, `parse_calendar`) — for each search,
   load Alaska's month calendar (`/search/calendar?...&FareType=Business&CM=YYYY-MM`)
   once per month across the booking window. Each load gives the lowest business
   award price per day (any routing).
2. **Confirm** — for every day the calendar flags at/under `max_miles`, load that
   day's full results page (`parse_results`) to check it's really the nonstop
   Starlux flight and not a cheaper partner connection.
3. **Match** (`match.py`) — keep only days that are Starlux (`JX`), nonstop, in
   the right cabin, at/under `max_miles`, under `max_taxes_usd`, seats ≥ pax.
4. **Dedup** (`store.py`, SQLite) — alert once per new hit; again only on a price
   drop or if it's still there after `renotify_after_hours`.
5. **Notify** (`notify.py`) — Pushover (emergency priority) with route, date,
   miles, taxes, seats.
6. **Schedule** (`scheduler.py`) — full sweeps every `full_sweep_minutes`, plus
   frequent `far_edge` passes over the newest bookable dates (where the saver
   seat first appears). A full 4-route × 331-day sweep is ~50 page loads.

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
