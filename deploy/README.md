# Deploying starlux-award-watch

Route A (Playwright + a warmed real-Chrome profile) needs **Google Chrome** and,
for a headed window, a logged-in GUI session. The simplest target is an
always-on Mac.

## macOS (LaunchAgent)

One-time:

```bash
cd starlux-award-watch
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium          # only needed if not using channel=chrome
cp .env.example .env                 # fill in PUSHOVER_* keys
$EDITOR config.yaml                  # routes / targets / cadence
python -m starlux_award_watch --headed --once --days 5 --route TPE->LAX   # smoke test
```

Then install the agent:

```bash
./deploy/install-macos.sh
```

It writes `~/Library/LaunchAgents/com.starlux-award-watch.plist`, loads it, and
tails `data/agent.log`. The agent runs at login and restarts on crash.

A full 4-route × 331-day sweep is ~50 page loads (~12 month-calendar loads per
route plus a confirmation for each day flagged at/under target), so it finishes
in minutes, not hours.

Manage it:

```bash
launchctl list | grep starlux
launchctl unload ~/Library/LaunchAgents/com.starlux-award-watch.plist   # stop
launchctl load   ~/Library/LaunchAgents/com.starlux-award-watch.plist   # start
./deploy/uninstall-macos.sh                                             # remove
tail -f data/agent.log
```

### Known limits on this Mac

- **Not online 24/7.** While the Mac sleeps or is offline, no checks run; it
  resumes on wake. Coverage has gaps — accepted for now.
- **Headed Chrome** needs you logged into the desktop. If you log out, the agent
  keeps restarting and failing until you log back in. Set `browser.headless:
  true` in `config.yaml` to run without a visible window (slightly higher
  CAPTCHA odds — worth testing).
- To reduce sleep gaps you can run it under `caffeinate -s` (keeps the Mac awake
  while on AC power) instead of the LaunchAgent.

### When you get a "CAPTCHA" alert

The monitor pauses that pass and pushes you a link. Clear it once:

```bash
python scripts/warm.py     # opens the profile browser; solve the challenge
```

The agent picks back up on its next cycle.

## Linux — Docker (amd64)

`Dockerfile` + `docker-compose.yml` in the repo root. The image installs real
Google Chrome and runs the loop under `xvfb-run` (headed Chrome, virtual
display). `data/` is a volume (Chrome profile + `state.db`); `.env` and
`config.yaml` are mounted.

```bash
cp .env.example .env && $EDITOR .env       # PUSHOVER_API_TOKEN / PUSHOVER_USER_KEY
mkdir -p data
docker compose build
docker compose up -d
docker compose logs -f
```

**IP reputation matters most here.** A home box / mini-PC on a residential
connection is fine. A cloud datacenter IP gets Akamai-challenged constantly with
no human at the console to clear it — you'd need a residential proxy, which this
image doesn't set up.

**Clearing a CAPTCHA in the container:** no display is attached, so
`scripts/warm.py`'s window is invisible. Options: (a) add `x11vnc` to the image
and VNC into the Xvfb display, (b) warm `data/chrome-profile/` on a desktop and
copy it onto the host's `data/` volume, (c) rely on residential-IP challenges
being rare and the heartbeat telling you when one is stuck.

**Raspberry Pi (ARM):** no `google-chrome-stable` build. Swap to Playwright's
bundled Chromium — in `fetch/browser.py` drop `channel="chrome"`, and in the
Dockerfile replace the Chrome apt install with `RUN playwright install
--with-deps chromium`. Untested.

## systemd (no Docker)

Install `google-chrome-stable`, then a `~/.config/systemd/user/` unit running
`xvfb-run -a .venv/bin/python -m starlux_award_watch` with `Restart=always`.

## The heartbeat

However you run it, the loop sends a quiet Pushover digest every
`alerts.heartbeat_hours` (default 24) plus one on startup:

```
still watching.
last full sweep: 2h ago
in the last 26h: 4 sweeps, 11 passes, 2 hits, 0 CAPTCHAs, 0 errors
routes: 4
```

If that digest stops arriving, the process or the host is down — that's your
signal to check. `heartbeat_hours: 0` disables it.
