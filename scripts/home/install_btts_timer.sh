#!/usr/bin/env bash
# Install (or update) the systemd user timer that runs scripts/home/btts_weekly.sh daily at ~10:00;
# the script itself does the work at most once every 6 days, when the VPN country allows it.
#   bash scripts/home/install_btts_timer.sh          # install / update
#   systemctl --user list-timers btts-weekly.timer    # next run
#   journalctl --user -u btts-weekly.service          # logs
set -euo pipefail
SCRIPT="$(cd "$(dirname "$0")" && pwd)/btts_weekly.sh"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
chmod +x "$SCRIPT"

cat > "$UNIT_DIR/btts-weekly.service" <<EOF
[Unit]
Description=Weekly OddsPortal BTTS price refresh (AG sports data)
After=network-online.target

[Service]
Type=oneshot
ExecStart=$SCRIPT
TimeoutStartSec=3h
EOF

cat > "$UNIT_DIR/btts-weekly.timer" <<EOF
[Unit]
Description=Daily check for the weekly BTTS price refresh

[Timer]
OnCalendar=*-*-* 10:00
RandomizedDelaySec=30min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now btts-weekly.timer
systemctl --user list-timers btts-weekly.timer --no-pager
