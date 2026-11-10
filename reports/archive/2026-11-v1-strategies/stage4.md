# Stage 4b — sizing comparison and corrected DSR

Frozen NA-v1: hard stops, TP 2R, minimum planned risk 5 spreads; indices USATECHIDXUSD, USA500IDXUSD.
All returns use actual spread-aware trade fills. Sizing-table Sharpe is annualized from daily returns; CAGR/MDD are compounded daily. Sizing method is selected independently for each series using IS Sharpe only.

## Sizing comparison

Paper vol-target uses prior cash-session close-to-close 14-session volatility: min(4, 2%/sigma). Stop-cap limits planned stop loss to 1% of equity. Portfolio leverage is aggregate concurrent notional across symbols.

| Series | Split | Sizing | Trades | Annualized Sharpe | CAGR | MDD | Worst trade loss / equity | Max notional leverage | >20x days |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| USATECHIDXUSD | IS | Equal risk 0.5% | 871 | 1.4210 | 14.1% | -7.9% | -0.57% | 24.78x | 1 |
| USATECHIDXUSD | OOS | Equal risk 0.5% | 822 | 0.6784 | 6.9% | -11.9% | -0.55% | 17.99x | 0 |
| USATECHIDXUSD | IS | Constant notional 1x | 871 | 1.6064 | 8.7% | -7.2% | -1.49% | 1.00x | 0 |
| USATECHIDXUSD | OOS | Constant notional 1x | 822 | 1.8613 | 10.3% | -3.0% | -1.00% | 1.00x | 0 |
| USATECHIDXUSD | IS | Paper vol-target | 871 | 1.5876 | 15.7% | -12.2% | -2.32% | 4.00x | 0 |
| USATECHIDXUSD | OOS | Paper vol-target | 822 | 2.0070 | 17.3% | -4.3% | -1.42% | 4.00x | 0 |
| USATECHIDXUSD | IS | Vol-target stop-cap 1% | 871 | 1.6062 | 14.1% | -9.8% | -1.00% | 4.00x | 0 |
| USATECHIDXUSD | OOS | Vol-target stop-cap 1% | 822 | 1.9966 | 16.7% | -4.3% | -1.00% | 4.00x | 0 |
| USA500IDXUSD | IS | Equal risk 0.5% | 747 | 0.7854 | 6.7% | -12.5% | -0.62% | 20.94x | 1 |
| USA500IDXUSD | OOS | Equal risk 0.5% | 703 | 0.6946 | 6.4% | -8.6% | -1.02% | 12.56x | 0 |
| USA500IDXUSD | IS | Constant notional 1x | 747 | 1.0308 | 4.4% | -6.4% | -1.45% | 1.00x | 0 |
| USA500IDXUSD | OOS | Constant notional 1x | 703 | 1.1340 | 4.7% | -2.6% | -0.66% | 1.00x | 0 |
| USA500IDXUSD | IS | Paper vol-target | 747 | 1.3923 | 12.1% | -7.3% | -2.01% | 4.00x | 0 |
| USA500IDXUSD | OOS | Paper vol-target | 703 | 1.2895 | 10.9% | -4.8% | -1.16% | 4.00x | 0 |
| USA500IDXUSD | IS | Vol-target stop-cap 1% | 747 | 1.3119 | 10.4% | -7.2% | -1.00% | 4.00x | 0 |
| USA500IDXUSD | OOS | Vol-target stop-cap 1% | 703 | 1.2475 | 9.9% | -5.0% | -1.00% | 4.00x | 0 |
| Portfolio | IS | Equal risk 0.5% | 1618 | 1.4004 | 21.7% | -12.2% | -0.62% | 24.78x | 3 |
| Portfolio | OOS | Equal risk 0.5% | 1525 | 0.8718 | 13.8% | -14.7% | -1.02% | 20.60x | 1 |
| Portfolio | IS | Constant notional 1x | 1618 | 1.5976 | 13.5% | -12.2% | -1.49% | 2.00x | 0 |
| Portfolio | OOS | Constant notional 1x | 1525 | 1.7739 | 15.5% | -5.2% | -1.00% | 2.00x | 0 |
| Portfolio | IS | Paper vol-target | 1618 | 1.7725 | 29.7% | -13.5% | -2.32% | 8.00x | 0 |
| Portfolio | OOS | Paper vol-target | 1525 | 1.9591 | 30.1% | -6.9% | -1.42% | 7.98x | 0 |
| Portfolio | IS | Vol-target stop-cap 1% | 1618 | 1.7554 | 26.0% | -11.6% | -1.00% | 8.00x | 0 |
| Portfolio | OOS | Vol-target stop-cap 1% | 1525 | 1.9317 | 28.3% | -6.8% | -1.00% | 7.98x | 0 |

### IS-selected method

| Series | Selected method | IS annualized Sharpe | OOS annualized Sharpe | OOS CAGR | OOS MDD | OOS worst trade loss | OOS max leverage |
|---|---|---:|---:|---:|---:|---:|---:|
| USATECHIDXUSD | Constant notional 1x | 1.6064 | 1.8613 | 10.3% | -3.0% | -1.00% | 1.00x |
| USA500IDXUSD | Paper vol-target | 1.3923 | 1.2895 | 10.9% | -4.8% | -1.16% | 4.00x |
| Portfolio | Paper vol-target | 1.7725 | 1.9591 | 30.1% | -6.9% | -1.42% | 7.98x |

## Days above EU index CFD leverage cap

20:1 is the stated cap. Dates below exceed it; row counts above give the number of flagged dates.

- USATECHIDXUSD, IS, Equal risk 0.5%: 2018-08-22
- USA500IDXUSD, IS, Equal risk 0.5%: 2020-07-20
- Portfolio, IS, Equal risk 0.5%: 2018-08-22, 2019-12-26, 2020-07-20
- Portfolio, OOS, Equal risk 0.5%: 2024-05-16

## Corrected Deflated Sharpe ratios

Trials counted: 40 = 30 Stage 1 rows + 10 Stage 2 noise_area report rows. DSR uses daily Sharpe units and applies the target series' selected sizing to every trial return stream.
Null benchmark: SR0 = sqrt(V[SR]) × ((1−γ)Φ⁻¹(1−1/N)+γΦ⁻¹(1−1/(N·e))); no mean term. V and mean pairwise return correlation are recomputed under each target's sizing.

| Series | Sizing selected on IS | OOS daily SR | N=1 | N=5 | N=10 | N=40 | mean pairwise ρ | N_eff | DSR at N_eff |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| USATECHIDXUSD | Constant notional 1x | 0.11725 | 0.9998 | 0.9885 | 0.9702 | 0.8951 | 0.537 | 19.04 | 0.9420 |
| USA500IDXUSD | Paper vol-target | 0.08123 | 0.9907 | 0.8630 | 0.7548 | 0.5157 | 0.501 | 20.46 | 0.6309 |
| Portfolio | Paper vol-target | 0.12341 | 0.9999 | 0.9923 | 0.9774 | 0.9068 | 0.501 | 20.46 | 0.9484 |

## Superseded DSR table (formula bug)

Retained for audit; it used a null benchmark with an erroneous mean-trial-Sharpe term.

| Series | Daily SR | Skew | Pearson kurtosis | Old expected max trial SR | Old DSR |
|---|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 0.04274 | 0.207 | 4.727 | 0.14330 | 0.0024 |
| USA500IDXUSD | 0.04376 | 0.300 | 5.248 | 0.14330 | 0.0026 |
| Portfolio | 0.05492 | 0.427 | 4.633 | 0.14330 | 0.0063 |

## NA-v1 confidence buckets

14-day volatility terciles use IS-only cut points. Decision blocks use the decision close time in New York.

| Variable | Bucket | IS n | IS hit | IS avg R | OOS n | OOS hit | OOS avg R | Variable Spearman |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| NR4 | No | 1229 | 31.0% | 0.106 | 1176 | 29.7% | 0.032 | -1.000 |
| NR4 | Yes | 389 | 32.1% | 0.102 | 349 | 30.7% | 0.142 | -1.000 |
| NR7 | No | 1411 | 31.5% | 0.113 | 1359 | 29.8% | 0.049 | -1.000 |
| NR7 | Yes | 207 | 30.0% | 0.049 | 166 | 30.7% | 0.123 | -1.000 |
| 14d vol | Low | 511 | 29.2% | 0.049 | 228 | 31.1% | 0.106 | -0.500 |
| 14d vol | Mid | 485 | 33.0% | 0.136 | 667 | 30.1% | 0.057 | -0.500 |
| 14d vol | High | 619 | 31.5% | 0.123 | 630 | 29.2% | 0.040 | -0.500 |
| Weekday | Mon | 334 | 32.6% | 0.163 | 227 | 20.7% | -0.172 | -0.100 |
| Weekday | Tue | 303 | 27.4% | -0.007 | 286 | 28.0% | 0.023 | -0.100 |
| Weekday | Wed | 339 | 31.0% | 0.107 | 293 | 31.1% | 0.111 | -0.100 |
| Weekday | Thu | 364 | 32.7% | 0.110 | 333 | 31.5% | 0.084 | -0.100 |
| Weekday | Fri | 278 | 32.4% | 0.148 | 386 | 34.5% | 0.153 | -0.100 |
| Decision block | 10–11 | 495 | 35.8% | 0.227 | 510 | 33.7% | 0.115 | 0.500 |
| Decision block | 11–13 | 544 | 32.0% | 0.086 | 480 | 27.3% | -0.052 | 0.500 |
| Decision block | 13–15:30 | 579 | 26.8% | 0.018 | 535 | 28.6% | 0.099 | 0.500 |
| Gap aligned | No | 483 | 28.4% | -0.007 | 464 | 32.3% | 0.118 | -1.000 |
| Gap aligned | Yes | 1135 | 32.5% | 0.153 | 1061 | 28.8% | 0.030 | -1.000 |

Stable ranking variable selected for confidence: Decision block (Spearman=0.500); k=50, p0=0.313.

| Confidence bucket | Predicted confidence | OOS n | OOS hit rate | OOS avg R |
|---|---:|---:|---:|---:|
| 10–11 | 0.353 | 510 | 33.7% | 0.115 |
| 11–13 | 0.319 | 480 | 27.3% | -0.052 |
| 13–15:30 | 0.271 | 535 | 28.6% | 0.099 |

## BTC Noise Area (UTC day)

UTC session open 00:00; previous close prior calendar day 23:59; decisions every 30 min 00:30–23:30; sigma=14 days; hard intrabar stops; MIN_RISK_SPREADS=5.
TP scheme: paper (no TP) and 2R; random-direction benchmark uses 200 seeds.

| Split | Variant | n | Hit | Avg R | Sharpe | MDD | Random percentile |
|---|---|---:|---:|---:|---:|---:|---:|
| IS | paper | 191 | 24.6% | -0.190 | -1.40 | -33.8% | 55.5 |
| OOS | paper | 370 | 27.6% | -0.169 | -0.77 | -38.8% | 51.5 |
| IS | TP 2R | 191 | 28.3% | -0.144 | -0.83 | -25.7% | 78.0 |
| OOS | TP 2R | 370 | 31.6% | -0.119 | -0.58 | -30.0% | 78.0 |

## BTC Donchian trend ensemble (approximate rules)

Long-only mean of 9 Donchian states; lookbacks=(5, 10, 20, 30, 60, 90, 150, 250, 360); exit lookback=ceil(N/2). Vol target 25% annualized from lagged 30-day daily-return std, cap 2x; BTC annualization=365 days. Exposure changes pay the Binance spread.
Buy-and-hold is also vol-targeted using the same lagged volatility and leverage cap.

| Split | Strategy | CAGR | Vol | Sharpe | MDD | Turnover |
|---|---|---:|---:|---:|---:|---:|
| IS | Donchian ensemble | 18.6% | 17.3% | 1.07 | -20.3% | 19.33x |
| IS | Vol-targeted buy-and-hold | 19.6% | 29.6% | 0.75 | -44.6% | 18.51x |
| OOS | Donchian ensemble | 14.4% | 15.1% | 0.97 | -16.5% | 19.00x |
| OOS | Vol-targeted buy-and-hold | 20.2% | 28.4% | 0.79 | -38.3% | 18.78x |

## Fixed constants

| Item | Fixed value |
|---|---|
| NA-v1 | stop=hard; TP=2R; minimum risk=5 entry spreads; symbols=USATECHIDXUSD, USA500IDXUSD |
| Index splits | IS 2018–2021; OOS 2022–2024; holdout excluded |
| Sizing methods | Equal risk 0.5%, Constant notional 1x, Paper vol-target, Vol-target stop-cap 1% |
| Sizing constants | equal risk 0.50%; vol target 2.0%; max 4x; stop loss cap 1.0%; index leverage flag 20x |
| DSR trial count | 40 (30 Stage 1 rows + 10 Stage 2 noise_area split/scheme rows) |
| DSR units | Daily Sharpe throughout; skew and Pearson kurtosis from daily returns; null SR0 has no mean term |
| Confidence shrinkage | k=50; p0=overall IS hit rate; choose highest IS-to-OOS bucket-rank Spearman |
| Confidence buckets | NR4, NR7, IS-cut 14-session volatility tercile, weekday, decision block (10–11/11–13/13–15:30 NY), gap aligned with side |
| BTC Noise Area | UTC sessions; sigma=14 days; decisions 00:30–23:30 every 30m; paper and TP 2R; minimum risk=5 spreads; spread pre-baked in Binance bid/ask |
| BTC random benchmark | 200 seeds |
| Donchian ensemble | N=(5, 10, 20, 30, 60, 90, 150, 250, 360); long-only mean of 9 states; exit ceil(N/2) |
| Donchian sizing | 30-day daily-return std lagged one day; 25% annual vol target; max 2×; 365 days/year; spread paid on exposure changes |

Runtime: 40.93 s
