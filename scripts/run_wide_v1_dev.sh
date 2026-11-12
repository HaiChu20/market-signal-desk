#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
work=data/wide_v1_run
mkdir -p "$work/logs"
fail() { printf '%s\n' "$1" > "$work/FAILED"; exit 1; }
run_one() {
  name="$1"; shift
  /usr/bin/time -l -o "$work/logs/$name.time" nice -n 10 uv run "$@" >"$work/logs/$name.log" 2>&1 || fail "$name"
}
for symbol in BTCUSDT ETHUSDT USATECHIDXUSD USA500IDXUSD XAUUSD; do
  run_one "grid_$symbol" python -m msd.processing.wide_v1 --kind grid --symbol "$symbol"
done
date -u +%FT%TZ > "$work/LABELS_DONE"
for symbol in BTCUSDT ETHUSDT USATECHIDXUSD USA500IDXUSD XAUUSD; do
  run_one "events_$symbol" python -m msd.processing.wide_v1 --kind events --symbol "$symbol"
done
run_one pure_rules python -m msd.research.wide_pure_rules
date -u +%FT%TZ > "$work/DONE"
