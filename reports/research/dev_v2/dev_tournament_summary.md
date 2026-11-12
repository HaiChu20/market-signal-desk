# Protocol-v2 DEV tournament

**Development only. Test and Final were neither loaded nor evaluated.**

## Registry reconciliation

The method index contains 30 table rows plus 3 pilots = 33 detector modules. Bollinger and post-macro each add one extra frozen variant, producing 35 tournament units. #34 is inputs-pending and excluded.

Outcome counts: 0 pass DEV diagnostics; 5 fail DEV diagnostics; 27 are silent after selection; 2 have no DEV events.

| Unit | Candidates | Signals | Signals/yr | Hit | Net avg R | t | PF | Sharpe | MDD | Brier skill | DSR | PBO | Random pct | DEV status | Runtime s | Peak MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| sr_touch | 4,339,051 | 6 | 0.4002 | 0.3333 | 0.2257 | 0.4621 | 1.7367 | 0.6182 | -0.0052 | 0.1776 | 0.1468 | NA | 82.5000 | fails DEV diagnostics | 11817.02 | 9724.1 |
| round_number_reaction | 531,947 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1095 | NA | NA | NA | silent: 0 selected signals | 149.37 | 7900.4 |
| session_level_reaction | 350,945 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1324 | NA | NA | NA | silent: 0 selected signals | 99.06 | 7132.9 |
| supply_demand_zone_retest | 46,413 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.6144 | NA | NA | NA | silent: 0 selected signals | 45.17 | 2631.1 |
| trendline_channel | 855,025 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2555 | NA | NA | NA | silent: 0 selected signals | 340.27 | 7299.4 |
| market_structure_pullback | 92,433 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1907 | NA | NA | NA | silent: 0 selected signals | 55.35 | 4213.2 |
| dow_trend_confirmation | 8,049 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1523 | NA | NA | NA | silent: 0 selected signals | 16.67 | 1215.5 |
| chart_patterns | 514,956 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2068 | NA | NA | NA | silent: 0 selected signals | 215.73 | 7596.8 |
| candlestick_at_level | 166,585 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1790 | NA | NA | NA | silent: 0 selected signals | 82.42 | 5145.4 |
| price_action_h2l2 | 1,651,677 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2395 | NA | NA | NA | silent: 0 selected signals | 655.95 | 7412.3 |
| fib_pullback | 593,438 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2153 | NA | NA | NA | silent: 0 selected signals | 237.02 | 7009.3 |
| order_block_retest | 254,743 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.4407 | NA | NA | NA | silent: 0 selected signals | 123.06 | 5741.0 |
| fvg_retrace | 805,451 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.4803 | NA | NA | NA | silent: 0 selected signals | 354.52 | 7106.8 |
| liquidity_sweep | 3,651,466 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1955 | NA | NA | NA | silent: 0 selected signals | 1574.71 | 7611.0 |
| ote_zone | 402,201 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.5383 | NA | NA | NA | silent: 0 selected signals | 168.02 | 7894.7 |
| wyckoff_spring_upthrust | 436,115 | 2 | 0.1334 | 0.5000 | 0.6524 | 0.3888 | 2.2722 | 2.2734 | -0.0051 | 0.1789 | NA | NA | 44.5000 | fails DEV diagnostics | 183.86 | 8397.5 |
| ma_cross | 142,943 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1785 | NA | NA | NA | silent: 0 selected signals | 70.65 | 5098.3 |
| macd_signal | 414,705 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1963 | NA | NA | NA | silent: 0 selected signals | 169.77 | 7581.8 |
| bollinger:band_reversion | 339,552 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2042 | NA | NA | NA | silent: 0 selected signals | 145.08 | 6425.4 |
| bollinger:squeeze_breakout | 46,192 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1502 | NA | NA | NA | silent: 0 selected signals | 38.79 | 2432.0 |
| stochastic | 499,309 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1990 | NA | NA | NA | silent: 0 selected signals | 198.90 | 7735.0 |
| vwap_reclaim_reject | 971,167 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2277 | NA | NA | NA | silent: 0 selected signals | 385.49 | 8205.9 |
| donchian_atr_breakout | 76,770 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1078 | NA | NA | NA | silent: 0 selected signals | 49.41 | 3595.4 |
| ichimoku_cloud | 1,591,489 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2388 | NA | NA | NA | silent: 0 selected signals | 631.15 | 9113.3 |
| volume_profile_poc_vah_val | 1,617,540 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2224 | NA | NA | NA | silent: 0 selected signals | 636.77 | 8054.0 |
| btc_order_flow | 365,592 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.6910 | NA | NA | NA | silent: 0 selected signals | 128.11 | 6443.4 |
| post_macro_event_reaction:follow | 0 | 0 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | no DEV events: macro_minutes_since_event is absent from the frozen DEV features | 3.72 | 845.8 |
| post_macro_event_reaction:fade | 0 | 0 | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | NA | no DEV events: macro_minutes_since_event is absent from the frozen DEV features | 3.60 | 839.5 |
| trend_following | 197,262 | 11 | 0.7482 | 0.2727 | 0.1349 | 0.2735 | 1.2359 | 0.8007 | -0.0104 | 0.1943 | NA | NA | 62.0000 | fails DEV diagnostics | 92.99 | 6381.4 |
| intraday_momentum | 416,274 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.0984 | NA | NA | NA | silent: 0 selected signals | 139.48 | 7571.5 |
| rsi2_mean_reversion | 3,311 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | -0.1806 | NA | NA | NA | silent: 0 selected signals | 4.40 | 988.9 |
| range_breakout_nr4_nr7 | 93,533 | 1 | 0.0669 | 0.0000 | -0.0548 | NA | 0.0000 | NA | -0.0003 | 0.1952 | NA | NA | 0.0000 | fails DEV diagnostics | 53.97 | 4372.7 |
| vix_spike_dip_buy | 4,588 | 3 | 0.7932 | 0.0000 | -0.7021 | -2.1961 | 0.0000 | -1.9010 | -0.0105 | -0.0981 | NA | NA | 47.5000 | fails DEV diagnostics | 4.73 | 1072.7 |
| funding_extreme_fade | 6,763 | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.3098 | NA | NA | NA | silent: 0 selected signals | 6.65 | 1058.9 |

## Run notes

Recorded per-unit runtime totals 18881.85 seconds. The sr_touch runtime includes a deliberate SIGSTOP while the machine was unattended.

The two post-macro variants have no DEV events because `macro_minutes_since_event` is absent from the frozen DEV features. ETH contributes no candidates because executable spread calibration is absent; the frozen replay contains BTC, NQ, SPX and XAU only.

Memory note: the following completed units exceeded the 8 GiB guard: sr_touch (9724.1 MiB), wyckoff_spring_upthrust (8397.5 MiB), vwap_reclaim_reject (8205.9 MiB), ichimoku_cloud (9113.3 MiB). The stale `data/tournament_logs/FAILED` marker refers to the completed Ichimoku run; the relaunched serial driver continued to DONE.
