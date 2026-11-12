#!/bin/bash
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
work=data/silence_diagnostic
mkdir -p "$work/logs"
ledger_before=$(shasum -a 256 reports/trials.csv | awk '{print $1}')
run_one() {
  name="$1"; shift
  /usr/bin/time -l -o "$work/logs/$name.time" nice -n 10 uv run python -m msd.research.silence_diagnostic "$@" >"$work/logs/$name.log" 2>&1 || return 1
  rss=$(awk '/maximum resident set size/{print $1}' "$work/logs/$name.time")
  [ "${rss:-0}" -le 10737418240 ] || { echo "$name exceeded 10 GiB: $rss" > "$work/FAILED"; return 1; }
}
run_one costs --costs || { echo costs > "$work/FAILED"; exit 1; }
for unit in rsi2_mean_reversion supply_demand_zone_retest trend_following fvg_retrace liquidity_sweep; do
  run_one "$unit" --skill "$unit" || { echo "$unit" > "$work/FAILED"; exit 1; }
done
run_one report --report || { echo report > "$work/FAILED"; exit 1; }
ledger_after=$(shasum -a 256 reports/trials.csv | awk '{print $1}')
[ "$ledger_before" = "$ledger_after" ] || { echo "trial ledger changed" > "$work/FAILED"; exit 1; }
date -u +%FT%TZ > "$work/DONE"
