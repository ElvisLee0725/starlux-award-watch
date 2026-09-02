# starlux-award-watch

Watches the **Alaska Airlines award calendar** for **Starlux (JX) business-class
saver space** on `TPE ↔ LAX` and `TPE ↔ ONT`, and **pushes your phone** the
moment a day prices at or below your target (75,000 miles). The lone saver seat
on these flights gets taken fast, so speed of notification is the whole point.

## Running it — the commands you keep forgetting

Always run from the repo root (`~/claude-projects/starlux-award-watch`). No venv
activation needed — call the venv's Python by path.

**The normal way — one sweep a day, by hand:**

```bash
.venv/bin/python -m starlux_award_watch --once --headed
```

Sweeps all 4 routes (~10–20 min), pushes you for any ≤75k nonstop JX business
day, then exits. Run it while you're at the keyboard so you can clear a CAPTCHA
in the window if one appears. This is the intended workflow — the continuous
loop hits Alaska often enough to get CAPTCHA'd when nobody's watching.

**Other modes:**

```bash
# Send one test push and exit (checks Pushover works).
.venv/bin/python -m starlux_award_watch --test-sms

# Continuous loop (full sweep ~every 2h, far-edge ~every 20min) + daily heartbeat.
# Only worth it if you'll clear the occasional CAPTCHA. Ctrl-C to stop.
.venv/bin/python -m starlux_award_watch --headed

# Install that loop as an always-on service. Same CAPTCHA caveat.
./deploy/install-macos.sh          # deploy/README.md; ./deploy/uninstall-macos.sh to remove
```

**What you'll see / get:**

- Terminal prints one `calendar_scan …` line per route as it finishes that
  route's months (with how many candidate days it flagged).
- A **Pushover push only on a hit** — a day where the nonstop JX flight has
  business ≤ 75,000 mi. **No hits → no notification**, it just returns to the
  prompt. There is no "sweep finished" ping.
- Drop `--headed` to run with no visible window.

**If you get a "CAPTCHA" push** (only happens headless / if you're away):

```bash
.venv/bin/python scripts/warm.py   # opens the profile browser — solve it once
```

A headed run instead waits up to 3 minutes for you to solve it in the window,
then carries on by itself.

Edit routes, target miles, cadence, and alert priority in **`config.yaml`**.

## Status

**Working end to end.** Live-verified: the month-calendar scan flags candidate
days, the confirmation load parses all four route legs (`JX 2` nonstop TPE↔LAX,
`JX 10` nonstop TPE↔ONT), the matcher keeps nonstop Starlux business ≤ 75k and
rejects connections / non-JX / 175k, SQLite dedup fires once then stays quiet,
the scheduler loop runs full sweep + far-edge, and a Pushover push (emergency
priority) lands on the phone. 24 tests.

Alerts: **Pushover**. A quiet daily **heartbeat** digest also goes out (plus one
on startup) so silence means "no seats," not "process/Mac dead" — if the digest
stops, go check.

Deploy: **macOS LaunchAgent** (`./deploy/install-macos.sh`) on an always-on Mac,
or **Docker** (`Dockerfile` + `docker-compose.yml`, amd64, best on a residential
IP — not build-verified locally). Details in `deploy/README.md`. Known gap: the
Mac isn't online 24/7, so coverage has holes; it resumes on wake.

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

## First-time setup (already done on this machine)

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/playwright install chromium
cp .env.example .env            # fill in PUSHOVER_API_TOKEN + PUSHOVER_USER_KEY
# warm the browser profile once (clears the initial Akamai CAPTCHA):
.venv/bin/python scripts/warm.py
```

## Deploy

Built for a macOS **LaunchAgent** on an always-on Mac — `./deploy/install-macos.sh`,
details in `deploy/README.md`. Linux (systemd + Chrome + xvfb) is sketched there
too. Running on a laptop only checks while it's awake and online.

## CLI flags

| flag | effect |
|---|---|
| `--once` | one full sweep, then exit (default is loop forever) |
| `--headed` | show the Chrome window |
| `--dry-run` | print alerts instead of pushing |
| `--test-sms` | send one test push via the configured channel, exit |
| `--route SUBSTR` | only run searches whose name contains SUBSTR |
| `--days N` | cap the scan to the next N days (testing) |
| `--max-cycles N` | run the loop for N cycles then exit (testing) |

## Notes

- Not affiliated with Alaska Airlines or Starlux. Personal use; keep polling
  gentle (`poll.request_delay_seconds`, `poll.jitter_pct`).
- Alaska's partner booking window is ~330 days; `window.max_days_ahead` controls
  how far ahead the calendar scan goes.
