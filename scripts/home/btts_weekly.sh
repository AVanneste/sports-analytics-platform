#!/usr/bin/env bash
# Weekly refresh of OddsPortal closing BTTS prices, run on the home machine by a systemd user timer
# (scripts/home/install_btts_timer.sh). The timer fires daily; this script does the work at most
# once every 6 days, and only when the connection appears in an allowed country (OddsPortal
# redirects Belgian visitors and lists only the bookmakers licensed in the visitor's country).
# It works in its own clone, so it never touches the working copy.
set -euo pipefail

REPO_URL="${BTTS_REPO_URL:-$(git -C "$(dirname "$0")/../.." remote get-url origin)}"
HARVESTER="${ODDSHARVESTER:-$(cd "$(dirname "$0")/../.." && pwd)/.venv-scrape/bin/oddsharvester}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/ag-sports-data"
CLONE="$STATE_DIR/btts-clone"
STAMP="$STATE_DIR/btts-last-success"
ALLOWED="${BTTS_COUNTRIES:-DE AT NL}"
mkdir -p "$STATE_DIR"

if [ -f "$STAMP" ] && [ $(( $(date +%s) - $(stat -c %Y "$STAMP") )) -lt $(( 6 * 86400 )) ]; then
  echo "BTTS refresh done less than 6 days ago; nothing to do."; exit 0
fi
country=$(curl -s -m 10 https://ipinfo.io/country || true)
if ! grep -qw "${country:-none}" <<< "$ALLOWED"; then
  echo "Connection appears in '${country:-unknown}', not one of: $ALLOWED (switch the VPN). Skipping."; exit 0
fi

[ -d "$CLONE/.git" ] || git clone -q "$REPO_URL" "$CLONE"
cd "$CLONE"
git checkout -q main && git pull -q --rebase origin main
ODDSHARVESTER="$HARVESTER" python3 scripts/scrape_oddsportal_btts.py --seasons current

git add Football/data/raw/oddsportal/
if git diff --staged --quiet; then
  echo "No new BTTS prices."
else
  git commit -q -m "chore(auto): weekly OddsPortal BTTS prices [skip ci]"
  for attempt in 1 2 3; do
    git pull -q --rebase origin main && git push -q origin HEAD:main && break
    sleep 10
  done
fi
touch "$STAMP"
echo "BTTS refresh complete."
