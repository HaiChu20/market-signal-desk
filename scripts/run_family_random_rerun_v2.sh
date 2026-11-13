#!/bin/sh
set -eu

DATA_ROOT=${1:?usage: run_family_random_rerun_v2.sh MAIN_DATA_ROOT}
ROOT=reports/research/phase2_v1_rerun_signals
mkdir -p "$ROOT"
: > "$ROOT/RUNNING"
failed() { printf '%s\n' "$(date -u +%FT%TZ)" > "$ROOT/FAILED"; }
trap failed HUP INT TERM EXIT

nice -n 10 uv run python -m msd.research.family_random_rerun \
  --data-root "$DATA_ROOT" \
  --labels-root "$DATA_ROOT/labels_wide_v1" \
  --original-output reports/research/phase2_v1 \
  --rerun-root "$ROOT" \
  --ledger reports/trials.csv

trap - HUP INT TERM EXIT
mv "$ROOT/RUNNING" "$ROOT/DONE"
