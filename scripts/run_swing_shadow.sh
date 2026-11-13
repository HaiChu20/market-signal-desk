#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
mkdir -p data/logs
exec uv run --env-file .env python -m msd.live.swing_shadow --send \
    >> data/logs/swing_shadow.log 2>&1
