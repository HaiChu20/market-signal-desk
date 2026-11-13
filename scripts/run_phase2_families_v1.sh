#!/bin/sh
set -eu

# Serial DEV-only family runner.  Launch explicitly with nohup + setsid after
# labels_wide_v1 is frozen; this script never accesses Test or Final.
DATA_ROOT=${1:?usage: run_phase2_families_v1.sh MAIN_DATA_ROOT [LABELS_ROOT]}
LABELS_ROOT=${2:-"$DATA_ROOT/labels_wide_v1"}
OUT=reports/research/phase2_v1
mkdir -p "$OUT/logs"
: > "$OUT/RUNNING"

failed() {
  printf '%s\n' "$(date -u +%FT%TZ)" > "$OUT/FAILED"
}
trap failed HUP INT TERM EXIT

for family in f3_order_flow f4_regime f5_cross_market; do
  for symbol in USATECHIDXUSD USA500IDXUSD XAUUSD BTCUSDT ETHUSDT; do
    nice -n 10 uv run python -m msd.research.family \
      --family "$family" --symbol "$symbol" \
      --data-root "$DATA_ROOT" --labels-root "$LABELS_ROOT" \
      --output "$OUT" > "$OUT/logs/${family}_${symbol}.log" 2>&1
  done
done

trap - HUP INT TERM EXIT
printf '%s\n' "$(date -u +%FT%TZ)" > "$OUT/DONE"
