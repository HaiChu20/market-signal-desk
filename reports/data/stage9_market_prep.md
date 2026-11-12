# Stage 9 remaining-market preparation

Quote windows and hourly costs are measured from the latest twelve complete local Dukascopy months. A no-quote window requires <5% minute occupancy on that local weekday. Session rules use these recurring windows and timezone conversion remains DST-aware. The hourly cost artifact contains the median and P95 executable `ask_o − bid_o`; labels continue to consume the actual bid/ask path.

| Symbol | Complete sample | Configured quote session | Observed weekday no-quote windows | Hourly median spread range | Point scale | Label class / nightly rate |
|---|---|---|---|---:|---:|---|
| USA30IDXUSD | 2025-11–2026-10 | 18:00–16:15 America/New_York | Mon: 16:15–18:00; Tue: 16:15–18:00; Wed: 16:15–18:00; Thu: 16:15–18:00; Fri: 16:15–24:00 | 2.026–2.062 | 1,000 | index / 0.00020 |
| DEUIDXEUR | 2025-11–2026-10 | 00:00–22:15 Europe/Berlin | Mon: 22:15–24:00; Tue: 22:15–24:00; Wed: 22:15–24:00; Thu: 22:15–24:00; Fri: 22:01–24:00 | 1.346–7.346 | 1,000 | index / 0.00020 |
| GBRIDXGBP | 2024-01–2024-12 | 23:00–21:15 Europe/London | Mon: 21:15–23:00; Tue: 21:15–23:00; Wed: 21:15–23:00; Thu: 21:15–23:00; Fri: 21:01–24:00 | 1–5.731 | 1,000 | index / 0.00020 |
| JPNIDXJPY | unavailable | pending measurement | no complete local month | — | — | index / 0.00020 |
| XAGUSD | 2025-11–2026-10 | 18:00–17:00 America/New_York | Mon: 17:00–18:00; Tue: 17:00–18:00; Wed: 17:00–18:00; Thu: 17:00–18:00; Fri: 17:00–24:00 | 0.036–0.055 | 1,000 | metal / 0.00015 |
| EURUSD | 2025-11–2026-10 | 17:00–17:00 America/New_York | Mon: none; Tue: none; Wed: none; Thu: none; Fri: 17:00–24:00 | 3e-05–0.00029 | 100,000 | fx / 0.00015 |
| USDJPY | 2025-11–2026-10 | 17:00–17:00 America/New_York | Mon: none; Tue: none; Wed: none; Thu: none; Fri: 17:00–24:00 | 0.004–0.048 | 1,000 | fx / 0.00015 |
| GBPUSD | 2025-11–2026-10 | 17:00–17:00 America/New_York | Mon: none; Tue: none; Wed: none; Thu: none; Fri: 17:00–24:00 | 6e-05–0.00062 | 100,000 | fx / 0.00015 |
| LIGHTCMDUSD | 2025-11–2026-10 | 18:00–17:00 America/New_York | Mon: 17:00–18:00; Tue: 17:00–18:00; Wed: 17:00–18:00; Thu: 17:00–18:00; Fri: 17:00–24:00 | 0.05–0.086 | 1,000 | energy / 0.00020 |
| BRENTCMDUSD | 2025-11–2026-10 | 00:00–22:00 Europe/London | Mon: 22:00–24:00; Tue: 22:00–24:00; Wed: 22:00–24:00; Thu: 22:00–24:00; Fri: 22:00–24:00 | 0.05–0.086 | 1,000 | energy / 0.00020 |

## Gaps before production Stage 9

- JPNIDXJPY has no complete local month, so its session endpoints, hourly spread costs and point scale remain unset. Its HTF builder fails closed.
- GBRIDXGBP is measured through 2024-12 only. Re-run this audit after the active campaign finishes before its production build.
- The existing label kernel has weekday deadlines and a 17:00 New York financing counter for all non-crypto instruments. The descriptive FX/metal/energy classes and explicit rates are prepared; class-specific rollover financing would require a separate kernel change.
- No production Stage 9 outputs were written. Dry-run artifacts are isolated under `data/tmp/fe242257/`.

Hourly cost artifact: `reports/data/stage9_spread_by_local_hour.csv`.

## One-year HTF dry runs

These are calendar/aggregation dry runs only. They wrote five timeframe files per symbol under `data/tmp/fe242257/`; they did not write production features, levels, events or labels.

| Symbol | Year | Input 1m rows | 5m | 15m | 1h | 4h | 1d | Runtime (s) | Peak RSS (MiB) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| USA30IDXUSD | 2025 | 340,959 | 68,202 | 22,735 | 5,868 | 1,520 | 246 | 4.151 | 410.5 |
| DEUIDXEUR | 2025 | 335,949 | 67,132 | 22,293 | 5,750 | 1,525 | 254 | 4.066 | 400.6 |
| XAGUSD | 2025 | 353,705 | 70,758 | 23,537 | 5,900 | 1,534 | 257 | 4.715 | 418.1 |
| EURUSD | 2025 | 372,088 | 74,420 | 24,823 | 6,212 | 1,551 | 258 | 5.913 | 372.3 |
| USDJPY | 2025 | 371,707 | 74,266 | 24,737 | 6,193 | 1,551 | 258 | 5.522 | 413.4 |
