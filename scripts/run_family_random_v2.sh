#!/bin/sh
set -eu

DATA_ROOT=${1:?usage: run_family_random_v2.sh MAIN_DATA_ROOT SAVED_SIGNALS_ROOT}
SIGNALS_ROOT=${2:?usage: run_family_random_v2.sh MAIN_DATA_ROOT SAVED_SIGNALS_ROOT}
OUT=reports/research/phase2_v1
mkdir -p "$OUT"
: > "$OUT/RANDOM_PCT_V2_RUNNING"
failed() { printf '%s\n' "$(date -u +%FT%TZ)" > "$OUT/RANDOM_PCT_V2_FAILED"; }
trap failed HUP INT TERM EXIT

nice -n 10 uv run python -m msd.research.family_random_v2 \
  --data-root "$DATA_ROOT" --signals-root "$SIGNALS_ROOT" --output "$OUT"

trap - HUP INT TERM EXIT
printf '%s\n' "$(date -u +%FT%TZ)" > "$OUT/RANDOM_PCT_V2_DONE"
