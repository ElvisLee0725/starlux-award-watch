#!/usr/bin/env bash
# Install starlux-award-watch as a macOS LaunchAgent (runs at login, restarts on crash).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.starlux-award-watch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ ! -x "$REPO/.venv/bin/python" ]]; then
  echo "!! $REPO/.venv not found. Create it and 'pip install -e .' first." >&2
  exit 1
fi
if [[ ! -f "$REPO/.env" ]]; then
  echo "!! $REPO/.env not found. Copy .env.example and fill it in first." >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$REPO/data"
sed "s|__REPO__|$REPO|g" "$REPO/deploy/$LABEL.plist.template" > "$PLIST"
echo "wrote $PLIST"

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "loaded. tailing $REPO/data/agent.log — Ctrl-C to stop watching (agent keeps running)."
sleep 1
tail -f "$REPO/data/agent.log"
