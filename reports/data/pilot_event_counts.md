# Pilot event counts

Event-volume validation only; no labels or outcome metrics were evaluated. Definitions are frozen in the detector module docstrings and registered in `reports/trials.csv`. The event-volume guard permits at most 50 events per instrument-day.

| Symbol | Year | Period | Method | Events | Instrument-days | Per day | Guard |
|---|---:|---|---|---:|---:|---:|---|
| BTCUSDT | 2022 | Development | sr_touch | 1,214 | 366 | 3.32 | Pass |
| BTCUSDT | 2022 | Development | liquidity_sweep | 4,330 | 366 | 11.83 | Pass |
| BTCUSDT | 2022 | Development | rsi2_mean_reversion | 0 | 366 | 0.00 | Pass; index-only method |
| BTCUSDT | 2024 | Test (event-count only) | sr_touch | 1,006 | 366 | 2.75 | Pass |
| BTCUSDT | 2024 | Test (event-count only) | liquidity_sweep | 4,625 | 366 | 12.64 | Pass |

Index and ETH counts are pending their source pipeline. Index event generation remains blocked until the pre-2014 futures-era roll gaps are measured. Test-period rows here are count and guard validation only; no labels, trades, or performance statistics were evaluated.
