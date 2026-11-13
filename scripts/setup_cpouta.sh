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
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv for $run_user from the official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || { echo "ERROR: uv install did not provide uv." >&2; exit 127; }

uv sync
if ! uv run python -c 'import msd._msd_kernels' >/dev/null 2>&1; then
    echo "Building the Rust extension..."
    uv run maturin develop --release --manifest-path rust/msd_kernels/Cargo.toml --offline
fi

echo "Downloading the swing replay window into $repo_root/data/bars..."
uv run python -m msd.data.swing_bootstrap --data-root "$repo_root/data"

unit_dir=$(mktemp -d)
trap 'rm -rf -- "$unit_dir"' EXIT
cat > "$unit_dir/msd-swing.service" <<UNIT
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
cat > "$unit_dir/msd-swing.timer" <<'UNIT'
[Unit]
Description=Run Market Signal Desk swing shadow daily

[Timer]
OnCalendar=*-*-* 07:00:00 Europe/Helsinki
Persistent=true
Unit=msd-swing.service

[Install]
WantedBy=timers.target
UNIT

sudo install -o root -g root -m 0644 "$unit_dir/msd-swing.service" /etc/systemd/system/msd-swing.service
sudo install -o root -g root -m 0644 "$unit_dir/msd-swing.timer" /etc/systemd/system/msd-swing.timer
sudo systemctl daemon-reload
sudo systemctl enable --now msd-swing.timer

echo "Sending the configured Telegram connection test..."
uv run --env-file .env python -m msd.live.swing_shadow --test-telegram
echo "Swing timer installed and enabled."
