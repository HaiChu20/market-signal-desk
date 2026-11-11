#!/bin/sh
# Increase tick workers only after the two-worker 1m campaign has exited.
set -eu
cd /Users/bfhach/Projects/market-signal-desk/.cao/worktrees/fe242257
campaign_log=/Users/bfhach/Projects/market-signal-desk/data/logs/stage8_dukascopy_resume5.log
tick_log=/Users/bfhach/Projects/market-signal-desk/data/logs/dukascopy_ticks_download.log
until grep -q 'Dukascopy campaign missing days' "$campaign_log"; do
    sleep 60
done
while pgrep -f '[p]ython.*-m msd.data.stage8_download --task dukascopy' >/dev/null; do
    sleep 30
done
for pid in $(pgrep -f '[p]ython.*-m msd.data.dukascopy_ticks' || true); do
    kill -TERM "$pid" || true
done
for count in 1 2 3 4 5 6 7 8 9 10; do
    if ! pgrep -f '[p]ython.*-m msd.data.dukascopy_ticks' >/dev/null; then
        break
    fi
    sleep 6
done
if pgrep -f '[p]ython.*-m msd.data.dukascopy_ticks' >/dev/null; then
    printf 'tick restart deferred: old process still alive\n' >> "$tick_log"
    exit 1
fi
printf 'Dukascopy 1m complete; restarting ticks with MSD_TICK_WORKERS=4\n' >> "$tick_log"
MSD_TICK_WORKERS=4 nohup nice -n 10 uv run python -u -m msd.data.dukascopy_ticks --end 2026-11-09 >> "$tick_log" 2>&1 < /dev/null &
printf 'tick restart PID %s\n' "$!" >> "$tick_log"
