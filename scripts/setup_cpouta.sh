#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

if [[ ! -f .env ]]; then
    echo "ERROR: .env is required. Copy it into the repository before setup; this script never creates or replaces it." >&2
    exit 1
fi

run_user=$(id -un)
if [[ "$run_user" == "root" ]]; then
    echo "ERROR: run this script as the repository owner, using sudo only when prompted." >&2
    exit 1
fi
repo_root=$(pwd -P)
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv for $run_user from the official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || { echo "ERROR: uv install did not provide uv." >&2; exit 127; }

uv sync

echo "Downloading the swing replay window into $repo_root/data/bars..."
uv run python -m msd.data.swing_bootstrap --data-root "$repo_root/data"

sudo tee /etc/systemd/system/msd-swing.service >/dev/null <<UNIT
[Unit]
Description=Market Signal Desk daily swing shadow run
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$run_user
WorkingDirectory=$repo_root
ExecStart=$repo_root/scripts/run_swing_shadow.sh
UNIT
sudo tee /etc/systemd/system/msd-swing.timer >/dev/null <<'UNIT'
[Unit]
Description=Run Market Signal Desk swing shadow daily

[Timer]
OnCalendar=*-*-* 07:00:00 Europe/Helsinki
Persistent=true
Unit=msd-swing.service

[Install]
WantedBy=timers.target
UNIT
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
sudo systemctl enable --now msd-swing.timer
sudo systemctl enable --now msd-live.service

echo "Sending the configured Telegram connection test..."
uv run --env-file .env python -m msd.live.swing_shadow --test-telegram
echo "Swing timer installed and enabled."
