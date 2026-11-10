# Processing profile: BTCUSDT, 2024-07

Run with `cProfile` on the local 46,080-row Binance spot month. These are baseline measurements only; no optimization was applied. Python 3.12, current working tree and local data.

| Layer | Elapsed | Output |
|---|---:|---:|
| HTF bars | 0.419 s | Five timeframes |
| Levels | 2.877 s | Level table |
| Features | 0.729 s | 46,080 feature rows |
| Event detection | 1.743 s | 9,697 events across the three enabled pilots |
| Label reference | 0.077 s | 100 reference calls; not a full label-grid run |

The label reference measurement is deliberately scoped to 100 calls: the existing Rust scalar/batch interface is currently inconsistent with the in-progress timestamp-based label API, so a full label-grid profile would not be a valid end-to-end baseline. Fix that interface before measuring full label throughput.

## HTF: top cumulative-time entries

| Function | Calls | Cumulative |
|---|---:|---:|
| `build_all_timeframes` | 1 | 0.419 s |
| `build_timeframe` | 5 | 0.419 s |
| pandas `aggregate` | 5 | 0.210 s |
| pandas `_python_agg_general` | 5 | 0.191 s |
| pandas `_aggregate_series_pure_python` | 5 | 0.190 s |
| custom volume/roll aggregation lambdas | 13,280 | 0.133 s |
| `build_timeframe.<lambda>` | 13,280 | 0.131 s |

The remaining top-15 entries were pandas groupby/apply dispatch and aggregation plumbing, each about 0.04–0.21 s cumulative.

## Levels: top cumulative-time entries

| Function | Calls | Cumulative |
|---|---:|---:|
| `build_levels` | 1 | 2.877 s |
| `_vwap_snapshots` | 1 | 2.323 s |
| VWAP row generator | 46,112 | 2.277 s |
| pandas `__getattr__` from row access | 101,333 | 1.506 s |
| pandas `DataFrame.__getitem__` | 101,290 | 1.141 s |
| pandas `DataFrame._ixs` | 101,306 | 0.876 s |
| pandas `.iloc` indexing | 101,049 | 0.796 s |
| `pivot_events` | included in remainder | below top 15 |

This confirms row-wise pandas access in VWAP snapshot creation as the principal levels cost. Per-level touch tracking was not a dominant call in this month profile.

## Features: top cumulative-time entries

| Function | Calls | Cumulative |
|---|---:|---:|
| `build_features` | 1 | 0.729 s |
| `_nearest_level_features` | 1 | 0.356 s |
| `_structure` | 5 | 0.163 s |
| `pivot_events` | 5 | 0.134 s |
| `indicator_frame` | 6 | 0.105 s |
| pandas attribute / column access | ~6,800 | ~0.09 s |
| pandas `replace` | 81 | 0.033 s |

Repeated `merge_asof` calls were not among the leading cumulative entries in this month profile.

## Events: top cumulative-time entries

| Method | Elapsed | Main function self time | Events |
|---|---:|---:|---:|
| `sr_touch.detect` | 1.008 s | 0.758 s | 4,465 |
| `liquidity_sweep.detect` | 0.719 s | 0.507 s | 5,232 |
| `rsi2_mean_reversion.detect` | 0.016 s | <0.001 s | 0 |

Within the two active event methods, repeated `searchsorted` and Python per-bar/per-level loops were the main visible costs.

## Labels: reference path, 100 calls

| Function | Calls | Cumulative |
|---|---:|---:|
| `first_hit_reference` | 100 | 0.073 s |
| `_row_bar` | 1,332 | 0.050 s |
| pandas `.iloc` indexing | 2,132 | 0.032 s |
| pandas `DataFrame._ixs` | 1,932 | 0.025 s |
| pandas `Series.__getitem__` | 10,656 | 0.021 s |

The reference path confirms repeated per-bar pandas extraction is expensive; no optimization is made until the reference/Rust contracts are aligned and outputs can be compared row-for-row.

## Assessment

Measured layer times on this month are far below the 15-minute/year concern when split by layer. The obvious current hot spots are row-wise VWAP level creation, the two event detectors, and pandas extraction in the Python label reference. A month-only profile cannot establish the ≤2-minute/year target, especially while the label API is inconsistent. No replacements or parallel execution were introduced; the required exact-output comparison remains a gate before any performance change.
