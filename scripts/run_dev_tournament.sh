#!/usr/bin/env bash
set -u

cd "$(git rev-parse --show-toplevel)" || exit 1

logs="data/tournament_logs"
output="reports/research/dev_v2"
sha="e18389ba59e47ba85758462afae6444d33d91d8f4795561ff879023fa2b2bef2"
rss_limit=$((8 * 1024 * 1024 * 1024))
mkdir -p "$logs" "$output"

# The first unit may have been launched interactively before this driver.
while kill -0 47147 2>/dev/null; do
    sleep 30
done

units=(
    sr_touch
    round_number_reaction
    session_level_reaction
    supply_demand_zone_retest
    trendline_channel
    market_structure_pullback
    dow_trend_confirmation
    chart_patterns
    candlestick_at_level
    price_action_h2l2
    fib_pullback
    order_block_retest
    fvg_retrace
    liquidity_sweep
    ote_zone
    wyckoff_spring_upthrust
    ma_cross
    macd_signal
    bollinger:band_reversion
    bollinger:squeeze_breakout
    stochastic
    vwap_reclaim_reject
    donchian_atr_breakout
    ichimoku_cloud
    volume_profile_poc_vah_val
    btc_order_flow
    post_macro_event_reaction:follow
    post_macro_event_reaction:fade
    trend_following
    intraday_momentum
    rsi2_mean_reversion
    range_breakout_nr4_nr7
    vix_spike_dip_buy
    funding_extreme_fade
)

for unit in "${units[@]}"; do
    report="$output/${unit}_dev.json"
    if [[ -f "$report" ]]; then
        continue
    fi
    safe=${unit//:/__}
    log="$logs/${safe}.log"
    timing="$logs/${safe}.time"
    /usr/bin/time -l nice -n 10 uv run python -m msd.research.tournament \
        --method "$unit" --frozen-events-sha "$sha" >"$log" 2>"$timing"
    status=$?
    if [[ $status -ne 0 ]]; then
        printf '%s exit=%s; see %s and %s\n' "$unit" "$status" "$log" "$timing" >"$logs/FAILED"
        exit "$status"
    fi
    rss=$(awk '/maximum resident set size/{print $1}' "$timing" | tail -1)
    if [[ -z "$rss" ]]; then
        printf '%s missing RSS measurement; see %s\n' "$unit" "$timing" >"$logs/FAILED"
        exit 1
    fi
    if (( rss > rss_limit )); then
        printf '%s peak_rss_bytes=%s exceeds %s\n' "$unit" "$rss" "$rss_limit" >"$logs/FAILED"
        exit 1
    fi
done

printf 'completed %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$logs/DONE"
