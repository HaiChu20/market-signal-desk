#!/bin/sh

set -u

worktree=/Users/bfhach/Projects/market-signal-desk/.cao/worktrees/fe242257
log_dir="$worktree/data/tmp/fe242257/stage9_logs"
gbp_pid=87564

cd "$worktree" || exit 1
mkdir -p "$log_dir"

while kill -0 "$gbp_pid" 2>/dev/null; do
    sleep 60
done

for job in "LIGHTCMDUSD 2012" "BRENTCMDUSD 2012"; do
    set -- $job
    symbol=$1
    start_year=$2
    if ! nice -n 10 /usr/bin/time -l uv run python -u -m msd.processing.pipeline \
        --symbol "$symbol" --start-year "$start_year" --end-year 2026 \
        > "$log_dir/$symbol.log" 2>&1; then
        printf '%s symbol=%s exit=failed\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$symbol" \
            > "$log_dir/REMAINING_FAILED"
        exit 1
    fi
done

printf '%s status=done\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$log_dir/REMAINING_DONE"
