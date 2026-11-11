#!/bin/sh
# Keep the verified archive campaign and its dependent feature rebuild in one job.
set -eu
cd /Users/bfhach/Projects/market-signal-desk/.cao/worktrees/fe242257
uv run python -u -m msd.data.binance_depth --btc-start 2026-01-01
uv run python -u -m msd.data.depth_features
