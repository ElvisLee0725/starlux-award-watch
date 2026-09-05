# starlux-award-watch

Watches the **Alaska Airlines award calendar** for **Starlux (JX) business-class
saver space** on `TPE ↔ LAX / ONT / SFO / SEA` (≤75,000 mi) and `TPE ↔ PHX`
(≤85,000 mi) — 10 directed routes — and **pushes your phone** the moment a day
prices at or below target. The lone saver seat on these flights gets taken fast,
so speed of notification is the whole point.

## Running it — use `make`

From the repo root. `make` auto-creates the venv on first use; you never touch
`.venv/` directly.

```
make setup      one-time: venv + deps + Chromium, and create .env
make warm       clear an Akamai CAPTCHA in the profile browser
make run        THE DAILY RUN — one full sweep of all routes (~30-40 min), visible window
make run-near   quick check: nearest 30 bookable days only (~3-5 min)
make run-far    quick check: farthest 30 bookable days only, e.g. newly-opened dates (~3-5 min)
make test-push  send one test Pushover notification
make loop       run continuously (full sweep ~2h, far-edge ~20m) + heartbeat
make test       run the test suite
make            list all targets
```

**The normal workflow is `make run` once a day**, while you're at the keyboard so
you can solve a CAPTCHA if one appears. `make loop` (or the LaunchAgent in
`deploy/`) runs forever but hits Alaska often enough to get CAPTCHA'd when
nobody's watching.

> First time only: macOS gates `make` behind the Xcode licence —
> `sudo xcodebuild -license accept`. Or `brew install make` and use `gmake`.

Under the hood every target just runs `.venv/bin/python -m starlux_award_watch …`
with the right flags — you can still call that directly if you prefer.

**What you'll see / get:**

- Terminal prints one `calendar_scan …` line per route as it finishes that
  route's months (with how many candidate days it flagged).
- A **Pushover push only on a hit** — a day where the nonstop JX flight is
  at/under that route's target, with the route line colour-coded per airport
  (`alerts.route_colors` in `config.yaml`). **No hits → no notification**, it
  just returns to the prompt. There is no "sweep finished" ping.
- Drop `--headed` to run with no visible window.
- `--days N` / `--far N` (or `make run-near` / `make run-far`) scan only the
  nearest or farthest N bookable days instead of the whole window — a fast
  spot-check instead of the full sweep.

**If you get a "CAPTCHA" push** (only happens headless / if you're away):

```bash
.venv/bin/python scripts/warm.py   # opens the profile browser — solve it once
```

A headed run instead waits up to 3 minutes for you to solve it in the window,
then carries on by itself.

Edit routes, target miles, cadence, and alert priority in **`config.yaml`**.

## Status

**Working end to end.** Live-verified across all 10 routes: the month-calendar
scan flags candidate days, the confirmation load parses the nonstop Starlux
flight (`JX 2` TPE↔LAX, `JX 10` TPE↔ONT, `JX 12` TPE↔SFO, plus SEA/PHX), the
matcher keeps nonstop Starlux business at/under each route's target and rejects
connections / non-JX / non-saver fares, SQLite dedup fires once then stays
quiet, the scheduler loop runs full sweep + far-edge, and a Pushover push lands
on the phone with a per-route coloured route line. 37 tests.

Found and fixed live: after a CAPTCHA clears mid-scan, Alaska's redirect-back
doesn't reliably reapply the URL's month/cabin params — it can silently settle
on a default month with no error. Fixed by forcing a clean reload of the exact
URL once a challenge clears.

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
5. **Notify** (`notify.py`) — Pushover with route (colour-coded per airport),
   date, miles, taxes, seats.
6. **Schedule** (`scheduler.py`) — full sweeps every `full_sweep_minutes`, plus
   frequent `far_edge` passes over the newest bookable dates (where the saver
   seat first appears). A full 10-route × 331-day sweep is ~120-150 page loads.

## First-time setup

```bash
make setup                      # venv + deps + Chromium
$EDITOR .env                    # fill in PUSHOVER_API_TOKEN + PUSHOVER_USER_KEY
make warm                       # clears the initial Akamai CAPTCHA
```

(Already done on this machine — this is here for a fresh clone.)

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
| `--days N` | quick scan: only the nearest N days of the window |
| `--far N` | quick scan: only the farthest N days of the window |
| `--max-cycles N` | run the loop for N cycles then exit (testing) |

## Notes

- Not affiliated with Alaska Airlines or Starlux. Personal use; keep polling
  gentle (`poll.request_delay_seconds`, `poll.jitter_pct`).
- Alaska's partner booking window is ~330 days; `window.max_days_ahead` controls
  how far ahead the calendar scan goes.
