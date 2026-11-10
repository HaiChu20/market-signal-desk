# Processing pipeline report

Protocol: `docs/protocol.md` v2. No model training or label-performance evaluation was run. The final period remains locked. Values below distinguish current diagnostic runs from retained legacy outputs.

## Current fixed definitions

| Item | Definition |
|---|---|
| HTF bars | 5m, 15m, 1h, 4h, 1D; emit only when complete; index daily session 18:00–17:00 America/New_York, crypto UTC day |
| Feature knowledge time | `known_at = 1m bar open + 1 minute`; all as-of joins backward |
| Label entry | At the open of signal bar + 2 bars |
| Label maximum hold | 5 trading days by time: entry timestamp plus 5 weekdays for non-crypto, 120h for crypto; exit at first bar open at/after deadline |
| Label grid | Every 15 UTC minutes, both sides; SL ATR multipliers 0.5, 1, 1.5, 2, 3; TP multipliers 0.5, 1, 1.5, 2, 3, 4, 6 |
| Financing | 17:00 New York rollover; Friday counts 3 for index/metals/FX; crypto counts 1 at every UTC midnight |
| S/R touch | Confirmed 15m+ swing k3/k5, prior day/week H/L, round numbers, zone edges; cluster 0.25×ATR1h, require 2 touches; edge-trigger at ±0.1×ATR after rearm 0.5×ATR; 4h cooldown |
| Liquidity sweep | Same level universe/clustering; wick 0.1×ATR beyond and close back inside within 3 bars; 4h cooldown |
| RSI(2) | Daily close RSI(2)<10 above daily EMA200; index-only, max one per day |

The Rust scalar and batch label entry points share one `simulate_one` implementation. Ten thousand randomized cases are checked against the independent Python reference for each entry point.

## Diagnostic performance

The table below is the saved pre-event/vectorization baseline. Current post-change timings and exact comparison results are in `performance_optimization.md`.

| Layer/sample | Runtime | Peak RSS | Detail |
|---|---:|---:|---|
| HTF, BTCUSDT 2022-01 | 0.433s | 0.165 GiB | Top cumulative entries in `profile_BTCUSDT_2022-01.md` |
| Levels, BTCUSDT 2022-01 | 2.888s | 0.179 GiB | `_vwap_snapshots` dominates; 2.332s cumulative |
| Features, BTCUSDT 2022-01 | 0.750s | 0.695 GiB | `_nearest_level_features` is largest function |
| S/R, BTCUSDT 2022-01 | 2.056s | 0.696 GiB | `bar_clusters` / Python level scanning dominate |
| Sweep, BTCUSDT 2022-01 | 2.182s | 0.696 GiB | `bar_clusters` / Python level scanning dominate |
| RSI(2), BTCUSDT 2022-01 | 0.017s | 0.696 GiB | No BTC events; index-only method |
| Labels, BTCUSDT 2022-01 | 0.798s | 0.344 GiB | 208,250 labels; 261,119 labels/s; top entries in profile file |
| S/R, BTCUSDT 2024 | 63.229s | 2.12 GiB | Event-count/guard only; no labels or outcomes |
| Sweep, BTCUSDT 2024 | 64.487s | 2.12 GiB | Event-count/guard only; no labels or outcomes |

The label-grid packing path was changed after profiling to remove repeated pandas row indexing and repeated bar-array conversion. The 2022-01 output matched the saved pre-optimization output exactly, row-for-row and dtype-for-dtype; runtime improved from 4.083s to 0.798s (5.1×). The subsequent event/vectorization pass reduced the 2022 monthly levels profile from 2.888s to 0.539s and the S/R and sweep detectors from 2.056s/2.182s to 1.367s/1.357s. Jan 2024 outputs matched the saved pre-change VWAP and event results exactly. The full-year 2024 event diagnostic was not repeated after this optimization; see `performance_optimization.md` for current month profiles and the label-grid follow-up note.

## Memory and data readiness

A prior full-year BTC feature build peaked at 4.44 GiB, above the 3 GiB per-worker target. The month profile peaked below 0.7 GiB, but production month streaming with warm-up overlap is not yet wired end-to-end. Do not launch a multi-worker build until that memory issue is resolved.

Overlap-era NSXUSD/SPXUSD HistData Parquets were rebuilt using full-day offset estimates, stale-expiry flags and independent held-out roll checks. Of 32 quarterly candidates per index, 19 NQ and 18 SPX rolls pass the <2-point held-out check; the rest remain unmeasured and are not applied. Adjusted values before the latest unresolved roll are NaN (valid segment starts 2018-06-14 for NQ and 2017-12-14 for SPX). The FRED CSV request needed to measure pre-2014 non-overlap rolls timed out; it was not retried. Do not build or evaluate index features across unresolved segments. BTC event counts are in `pilot_event_counts.md`; those rows are counts/guard checks only and do not evaluate outcomes.

The Parquets under `data/events/` and `data/labels/` are retained legacy outputs from earlier definitions and the bar-count label contract. They are not valid outputs under the current frozen event definitions/time-based label contract and must be regenerated before modeling. They have not been deleted.

## Tests

Latest full run: `uv run pytest -q` — 86 passed. No model training or holdout metrics were generated.
