# Holdout evaluation — 2026-11-09 — single evaluation

Frozen index NA-v1: hard stops, TP 2R, minimum planned risk 5 spreads; sizing is min(4, 2%/prior 14-session volatility) capped so planned stop loss is ≤1% equity. BTC is the frozen long-only Donchian ensemble (25% annual vol, 2× cap). Confidence is the IS-only shrunk hit rate by decision-time block.

Data ranges include pre-holdout history for causal features; reported trades/returns use 2025-01-01 onward. Index metrics use annualized 252-session Sharpe/CAGR and BTC uses 365-day annualization. BTC 'trades' are contiguous long-exposure episodes; avg R is n/a because the ensemble has no single fixed initial risk.

| Series | Data range (full; evaluated) | Trades / episodes | Hit rate | Avg R | Sharpe | CAGR | MDD | Worst trade loss / equity | Random percentile |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 2018-01-02..2026-11-08 (holdout 2025-01-01..2026-11-08) | 504 | 28.4% | -0.022 | -0.396 | -3.5% | -17.7% | -1.00% | 71.0 |
| USA500IDXUSD | 2018-01-02..2026-11-08 (holdout 2025-01-01..2026-11-08) | 455 | 24.4% | -0.099 | -1.063 | -8.3% | -22.9% | -1.00% | 14.5 |
| Portfolio | USATECHIDXUSD: 2018-01-02..2026-11-08 (holdout 2025-01-01..2026-11-08); USA500IDXUSD: 2018-01-02..2026-11-08 (holdout 2025-01-01..2026-11-08) | 959 | 26.5% | -0.059 | -0.821 | -11.5% | -35.1% | -1.00% | nan |
| BTC Donchian | 2018-01-01..2026-10-31 (holdout 2025-01-01..2026-10-30) | 8 | 12.5% | nan | -0.218 | -3.8% | -20.1% | -3.90% | nan |

## Confidence calibration

Confidence values were frozen from the 2018–2021 IS sample using k=50 and overall p0=506/1618. Holdout outcomes are TP hit rates and net R.

| Decision block | Frozen confidence | Symbol | n | Holdout hit rate | Holdout avg R |
|---|---:|---|---:|---:|---:|
| 10–11 | 0.353 | USATECHIDXUSD | 170 | 28.8% | 0.009 |
| 11–13 | 0.319 | USATECHIDXUSD | 169 | 33.1% | 0.108 |
| 13–15:30 | 0.271 | USATECHIDXUSD | 165 | 23.0% | -0.187 |
| 10–11 | 0.353 | USA500IDXUSD | 152 | 25.0% | -0.120 |
| 11–13 | 0.319 | USA500IDXUSD | 151 | 26.5% | -0.072 |
| 13–15:30 | 0.271 | USA500IDXUSD | 152 | 21.7% | -0.105 |

## Frozen IS confidence values

| Decision block | IS n | IS hits | Shrunk confidence |
|---|---:|---:|---:|
| 10–11 | 495 | 177 | 0.353462 |
| 11–13 | 544 | 174 | 0.319254 |
| 13–15:30 | 579 | 155 | 0.271282 |

Runtime: 158.59 s
