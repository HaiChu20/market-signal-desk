#!/bin/sh
set -eu

DATA_ROOT=${1:?usage: run_information_audit.sh MAIN_DATA_ROOT}
OUT=reports/research/phase2_v1
mkdir -p "$OUT"
: > "$OUT/INFORMATION_AUDIT_RUNNING"
failed() { printf '%s\n' "$(date -u +%FT%TZ)" > "$OUT/INFORMATION_AUDIT_FAILED"; }
trap failed HUP INT TERM EXIT

nice -n 10 uv run python -m msd.research.information_audit \
  --data-root "$DATA_ROOT" \
  --labels-root "$DATA_ROOT/labels_wide_v1" \
  --output "$OUT/information_audit.md"

trap - HUP INT TERM EXIT
printf '%s\n' "$(date -u +%FT%TZ)" > "$OUT/INFORMATION_AUDIT_DONE"
