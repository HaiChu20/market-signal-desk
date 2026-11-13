# Final v2 — intraday Donchian ATR breakout

**DROP** — the frozen verdict uses only pooled net R per trade > 0.

Decisions begin at 2025-01-01 00:00 UTC. Detector state is warmed on 2024 minute bars. Trades still open at each market's local data end are dropped, not censored.

| Trades | Hit rate | Net R/trade | t | Profit factor | Random percentile | Dropped at end |
|---:|---:|---:|---:|---:|---:|---:|
| 608 | 0.4408 | -0.0669 | -1.5693 | 0.8580 | 28.5000 | 1 |

Random-direction percentile uses exactly 200 deterministic seeds and the same entries and geometry.

## Per market

| Scope | Trades | Hit rate | Net R/trade | t | Profit factor |
|---|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 153 | 0.3987 | -0.1106 | -1.3019 | 0.7730 |
| USA500IDXUSD | 164 | 0.4390 | -0.1213 | -1.5976 | 0.7427 |
| XAUUSD | 130 | 0.5615 | 0.1678 | 1.8736 | 1.4939 |
| BTCUSDT | 161 | 0.3851 | -0.1594 | -1.7880 | 0.7161 |

## Per year

| Scope | Trades | Hit rate | Net R/trade | t | Profit factor |
|---|---:|---:|---:|---:|---:|
| 2025 | 333 | 0.4114 | -0.1070 | -1.8698 | 0.7822 |
| 2026 | 275 | 0.4764 | -0.0184 | -0.2878 | 0.9589 |
