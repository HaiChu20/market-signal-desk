#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
mkdir -p data/logs
exec >> data/logs/swing_shadow.log 2>&1
PATH="${HOME:-/home/ubuntu}/.local/bin:/Users/bfhach/.local/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
export PATH
if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv not found; checked the configured local and package-manager paths." >&2
    exit 127
fi
exec uv run --env-file .env python -m msd.live.swing_shadow --send
