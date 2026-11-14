#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo_root"

if [[ ! -f .env ]]; then
    echo "ERROR: .env is required. This script never creates or replaces it." >&2
    exit 1
fi
run_user=$(id -un)
if [[ "$run_user" == "root" ]]; then
    echo "ERROR: run this script as the repository owner, using sudo only when prompted." >&2
    exit 1
fi

sudo tee /etc/systemd/system/msd-live.service >/dev/null <<UNIT
[Unit]
Description=Market Signal Desk live TikTok A/B alerts
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$run_user
WorkingDirectory=$repo_root
ExecStart=$repo_root/scripts/run_live.sh
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now msd-live.service
echo "msd-live.service installed and started."
