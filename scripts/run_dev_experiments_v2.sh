#!/bin/sh
set -eu

run_root=data/dev_experiments_v2_run
mkdir -p "$run_root"
trap 'printf "%s\n" "$(date -u +%FT%TZ)" > "$run_root/FAILED"' EXIT HUP INT TERM

for symbol in BTCUSDT ETHUSDT USATECHIDXUSD USA500IDXUSD XAUUSD; do
  /usr/bin/time -l nice -n 10 uv run python -m msd.processing.wide_v1 \
    --symbol "$symbol" --kind events --data-root data \
    --config hpc/roihu/sequence/configs/wide_v2.json \
    --output-root data/events_wide_v2 \
    > "$run_root/hold1_${symbol}.log" 2>&1
  /usr/bin/time -l nice -n 10 uv run python -m msd.processing.wide_v1 \
    --symbol "$symbol" --kind events --data-root data \
    --config hpc/roihu/sequence/configs/wide_hold3_v2.json \
    --output-root data/events_wide_hold3_v2 \
    > "$run_root/hold3_${symbol}.log" 2>&1
done

/usr/bin/time -l nice -n 10 uv run python -m msd.research.dev_experiments_v2 \
  --skip-build --data-root data \
  --v1-root data/events_wide_v2 \
  --e1-root data/events_wide_hold3_v2 \
  > "$run_root/analysis.log" 2>&1

trap - EXIT HUP INT TERM
printf "%s\n" "$(date -u +%FT%TZ)" > "$run_root/DONE"
