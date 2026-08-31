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

## Linux (x86, systemd) — later

Install Google Chrome (`google-chrome-stable`), run under `xvfb-run` for a
virtual display, and wrap `python -m starlux_award_watch` in a `systemd --user`
service with `Restart=always`. A Dockerfile can bundle Chrome + xvfb; ARM
(Raspberry Pi) has no Google Chrome build, so it must fall back to Playwright's
bundled Chromium (`channel` unset) headless.
