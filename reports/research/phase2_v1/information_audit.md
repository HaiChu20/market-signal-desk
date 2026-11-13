# Phase 2 DEV information and correctness audit

**DEV only: all decisions, targets and label ends are before 2023-01-01. Test and Final were not loaded. Analysis only; no rules, thresholds or ledger rows were changed.**

Runtime: 45.33 minutes; peak RSS: 9.32 GiB.

## Label correctness

Direct bar-path recomputation: 30/30 randomly selected labels matched outcome, entry/exit timestamps and prices, gross R and net R. The recomputation used the nanosecond-normalized pure-Python reference and the stored declared deadline independently; these random rows resolved before the deadline and therefore did **not** test the subsequently discovered max-hold timestamp-unit bug.

**Known label defect:** the wide-label Rust input converted `datetime64[us]` timestamps as if they were nanoseconds, so some CFD time deadlines did not fire. The following DEV scan is `exit_ts > deadline_ts`; results using affected CFD labels are contaminated and must be rerun after the owning worker rebuilds them. Forward-return ICs below are unaffected because they use nanosecond NumPy timestamps plus `searchsorted`, not the label kernel.

| Market | DEV labels | Exit after deadline | Share |
|---|---:|---:|---:|
| USATECHIDXUSD | 4,561,550 | 50,930 | 1.1165% |
| USA500IDXUSD | 4,453,650 | 90,309 | 2.0278% |
| XAUUSD | 17,923,250 | 250,011 | 1.3949% |
| BTCUSDT | 5,253,450 | 0 | 0.0000% |
| ETHUSDT | 5,253,450 | 0 | 0.0000% |

## Feature coverage and model inputs

The completed family runner supplied explicit feature lists to ResidualModel. Therefore its automatic ≥50% coverage selection was bypassed: `actual passed` below is the configured count, while `eligible at ≥50%` shows what the automatic path would have retained. Per-feature values are in `information_feature_coverage.csv`.

| Family | Market | Training anchors | Actual passed | Eligible at ≥50% | All-NaN source features | Causal stamps |
|---|---|---:|---:|---:|---:|---|
| f3_order_flow | USATECHIDXUSD | 23,544 | 84 | 6 | 35 | yes |
| f3_order_flow | USA500IDXUSD | 23,215 | 84 | 6 | 35 | yes |
| f3_order_flow | XAUUSD | 90,084 | 84 | 6 | 35 | yes |
| f3_order_flow | BTCUSDT | 26,266 | 84 | 31 | 7 | yes |
| f3_order_flow | ETHUSDT | 26,266 | 84 | 31 | 7 | yes |
| f4_regime | USATECHIDXUSD | 23,544 | 406 | 192 | 10 | yes |
| f4_regime | USA500IDXUSD | 23,215 | 406 | 192 | 10 | yes |
| f4_regime | XAUUSD | 90,084 | 406 | 192 | 10 | yes |
| f4_regime | BTCUSDT | 26,266 | 406 | 192 | 10 | yes |
| f4_regime | ETHUSDT | 26,266 | 406 | 192 | 10 | yes |
| f5_cross_market | USATECHIDXUSD | 23,544 | 74 | 28 | 2 | yes |
| f5_cross_market | USA500IDXUSD | 23,215 | 74 | 28 | 2 | yes |
| f5_cross_market | XAUUSD | 90,084 | 50 | 16 | 2 | yes |
| f5_cross_market | BTCUSDT | 26,266 | 74 | 36 | 0 | yes |
| f5_cross_market | ETHUSDT | 26,266 | 74 | 35 | 0 | yes |

**Coverage warning:** F3 order flow was not a valid test on the CFD markets. NQ, SPX and XAU each had only 6/84 configured features at ≥50% training coverage and 35/84 were entirely NaN. The explicit family feature list bypassed ResidualModel's normal ≥50% filter, so those fits were dominated by missing inputs rather than a usable CFD flow history. F4 likewise had only 192/406 eligible inputs, although its usable subset was much broader.

## Gate and fit diagnostics

| Family | Market | edge p50 | p95 | p99 | edge>0 | edge>0.05 | uncertainty-only failures | neighbour-only event failures | chosen | gated | train Brier | OOF Brier | gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| f3_order_flow | USATECHIDXUSD | -0.2559 | -0.0286 | -0.0114 | 7,521 | 1,579 | 833 | 728 | 0 | 0 | 0.179063 | 0.180318 | 0.001255 |
| f3_order_flow | USA500IDXUSD | -0.2722 | -0.0217 | -0.0154 | 5,146 | 790 | 501 | 256 | 33 | 12 | 0.173984 | 0.175301 | 0.001316 |
| f3_order_flow | XAUUSD | -0.3200 | -0.0389 | -0.0343 | 508 | 0 | 0 | 0 | 0 | 0 | 0.173504 | 0.173739 | 0.000235 |
| f3_order_flow | BTCUSDT | -0.3895 | -0.0951 | -0.0605 | 1,519 | 269 | 118 | 73 | 36 | 7 | 0.173300 | 0.174185 | 0.000885 |
| f3_order_flow | ETHUSDT | -0.3413 | -0.0709 | -0.0455 | 3,778 | 706 | 361 | 168 | 85 | 18 | 0.175523 | 0.176519 | 0.000997 |
| f4_regime | USATECHIDXUSD | -0.2499 | -0.0310 | -0.0202 | 3,115 | 649 | 159 | 360 | 31 | 15 | 0.177825 | 0.179354 | 0.001528 |
| f4_regime | USA500IDXUSD | -0.2818 | -0.0239 | -0.0172 | 1,135 | 278 | 0 | 278 | 0 | 0 | 0.173274 | 0.174930 | 0.001657 |
| f4_regime | XAUUSD | -0.3362 | -0.0385 | -0.0335 | 14,177 | 12,547 | 129 | 7,508 | 87 | 35 | 0.172583 | 0.172969 | 0.000386 |
| f4_regime | BTCUSDT | -0.4257 | -0.1128 | -0.0783 | 515 | 134 | 46 | 41 | 12 | 2 | 0.173007 | 0.174652 | 0.001645 |
| f4_regime | ETHUSDT | -0.3657 | -0.0807 | -0.0584 | 2,115 | 458 | 216 | 105 | 62 | 17 | 0.174762 | 0.176190 | 0.001427 |
| f5_cross_market | USATECHIDXUSD | -0.2887 | -0.0340 | -0.0237 | 2,739 | 142 | 25 | 29 | 37 | 9 | 0.178660 | 0.180186 | 0.001526 |
| f5_cross_market | USA500IDXUSD | -0.2944 | -0.0223 | -0.0148 | 2,698 | 3 | 3 | 0 | 0 | 0 | 0.173504 | 0.175061 | 0.001557 |
| f5_cross_market | XAUUSD | -0.3411 | -0.0396 | -0.0345 | 127 | 0 | 0 | 0 | 0 | 0 | 0.173770 | 0.173958 | 0.000188 |
| f5_cross_market | BTCUSDT | -0.4064 | -0.1025 | -0.0655 | 1,109 | 367 | 180 | 77 | 57 | 8 | 0.174181 | 0.176045 | 0.001863 |
| f5_cross_market | ETHUSDT | -0.3621 | -0.0776 | -0.0461 | 4,323 | 502 | 271 | 99 | 73 | 19 | 0.175979 | 0.178239 | 0.002259 |

The train-to-OOF Brier gaps are only 0.0002–0.0023. That rules out severe tree overfit, but does not prove that 40 trees/7 leaves are sufficient: together with compressed predicted-edge distributions, it is consistent with weak/missing inputs or mild underfit. This audit cannot distinguish those without changing the pre-registered model, so no capacity change was made.

## Information content

The exhaustive per-feature/per-year IC summary is in `information_ic.csv`. Stable ranking is |mean annual Spearman IC| × same-sign year share. The cost comparison is |IC| × target standard deviation divided by median executable cost in ATR units.

### USATECHIDXUSD

Anchors: 91,231; features: 424; median cost: 0.066398 ATR; causal joins: True.

| Target | Ridge OOF IC | n | Best feature | Mean IC | IC t(years) | Same-sign years | Proxy/cost |
|---|---:|---:|---|---:|---:|---:|---:|
| return_15m | -0.0028 | 91,230 | spread_atr | -0.0220 | -4.8786 | 4/4 | 0.1461 |
| abs_return_15m | 0.4531 | 91,230 | time_cos | -0.3753 | -21.9541 | 4/4 | 1.9667 |
| return_1h | 0.0084 | 91,227 | 1h_volume_ratio20 | 0.0302 | 2.9680 | 4/4 | 0.4182 |
| abs_return_1h | 0.4386 | 91,227 | time_cos | -0.3698 | -25.6929 | 4/4 | 4.0341 |
| return_4h | 0.0013 | 91,215 | dvol_btc_level | 0.0517 | 1.9134 | 2/2 | 1.4966 |
| abs_return_4h | 0.4528 | 91,215 | time_sin | 0.3204 | 8.0303 | 4/4 | 7.1372 |
| return_1d | 0.0711 | 91,142 | dvol_btc_level | 0.1358 | 3.2064 | 2/2 | 8.7452 |
| abs_return_1d | 0.2401 | 91,142 | 1h_atr14 | -0.2049 | -6.0994 | 4/4 | 8.8671 |

DVOL/1-day non-overlap check: one anchor per UTC day gives n=551, IC=0.165; 2021: IC 0.140 (n=242), 2022: IC 0.130 (n=309). This is only 2 calendar years and is treated as a slow regime observation, not robust evidence.
### USA500IDXUSD

Anchors: 89,073; features: 424; median cost: 0.051863 ATR; causal joins: True.

| Target | Ridge OOF IC | n | Best feature | Mean IC | IC t(years) | Same-sign years | Proxy/cost |
|---|---:|---:|---|---:|---:|---:|---:|
| return_15m | 0.0046 | 89,072 | 5m_plus_di14 | -0.0231 | -5.6495 | 4/4 | 0.1801 |
| abs_return_15m | 0.4246 | 89,072 | time_cos | -0.3362 | -11.9977 | 4/4 | 2.0070 |
| return_1h | 0.0138 | 89,069 | 1d_ema20_50_gap_atr | -0.0274 | -4.6919 | 4/4 | 0.4409 |
| abs_return_1h | 0.3955 | 89,069 | time_cos | -0.3372 | -12.8144 | 4/4 | 4.1516 |
| return_4h | 0.0206 | 89,057 | 1d_ema200_slope | -0.0551 | -7.4366 | 3/3 | 1.8255 |
| abs_return_4h | 0.3991 | 89,057 | time_cos | -0.2914 | -18.5364 | 4/4 | 7.2469 |
| return_1d | 0.0601 | 88,984 | 1d_ema200_slope | -0.1283 | -8.9175 | 3/3 | 9.6509 |
| abs_return_1d | 0.2034 | 88,984 | 1h_vol_ratio14_50 | -0.1436 | -3.7519 | 4/4 | 7.2070 |
### XAUUSD

Anchors: 358,465; features: 412; median cost: 0.101628 ATR; causal joins: True.

| Target | Ridge OOF IC | n | Best feature | Mean IC | IC t(years) | Same-sign years | Proxy/cost |
|---|---:|---:|---|---:|---:|---:|---:|
| return_15m | 0.0350 | 358,464 | 1m_ema50_distance_atr | -0.0584 | -13.7440 | 15/15 | 0.2292 |
| abs_return_15m | 0.3745 | 358,464 | time_cos | -0.3097 | -29.4098 | 15/15 | 0.9343 |
| return_1h | 0.0313 | 358,461 | spread_modeled | 0.0574 | NA | 1/1 | 0.4580 |
| abs_return_1h | 0.3761 | 358,461 | time_cos | -0.3212 | -27.9344 | 15/15 | 1.9790 |
| return_4h | 0.0080 | 358,449 | spread_modeled | 0.0399 | NA | 1/1 | 0.6591 |
| abs_return_4h | 0.3796 | 358,449 | time_cos | -0.3382 | -27.5673 | 15/15 | 4.2939 |
| return_1d | 0.0233 | 358,373 | 15m_swing_high | -0.0872 | -8.0071 | 15/15 | 3.3969 |
| abs_return_1d | 0.2222 | 358,373 | 1h_parkinson_vol14 | -0.2363 | -19.5207 | 15/15 | 6.3790 |
### BTCUSDT

Anchors: 105,069; features: 424; median cost: 0.120193 ATR; causal joins: True.

| Target | Ridge OOF IC | n | Best feature | Mean IC | IC t(years) | Same-sign years | Proxy/cost |
|---|---:|---:|---|---:|---:|---:|---:|
| return_15m | 0.0797 | 105,068 | 1m_ema20_distance_atr | -0.0952 | -16.0089 | 3/3 | 0.2899 |
| abs_return_15m | 0.2242 | 105,068 | perp_trade_intensity_z20d | 0.1517 | 13.0129 | 3/3 | 0.3489 |
| return_1h | 0.0063 | 105,065 | spot_large1m_imbalance_1m | -0.0991 | -0.9723 | 2/3 | 0.6001 |
| abs_return_1h | 0.1873 | 105,065 | 15m_donchian55_width_atr | -0.1277 | -5.0394 | 3/3 | 0.5907 |
| return_4h | 0.0005 | 105,053 | 15m_bollinger_pctb20 | -0.0483 | -9.6923 | 3/3 | 0.5989 |
| abs_return_4h | 0.1841 | 105,053 | 15m_donchian55_width_atr | -0.1291 | -5.0722 | 3/3 | 1.2039 |
| return_1d | -0.0163 | 104,973 | dvol_btc_level | 0.0785 | 2.6481 | 2/2 | 2.6119 |
| abs_return_1d | 0.2154 | 104,973 | 1h_parkinson_vol14 | -0.2086 | -8.2903 | 3/3 | 5.0760 |

DVOL/1-day non-overlap check: one anchor per UTC day gives n=647, IC=0.075; 2021: IC 0.039 (n=283), 2022: IC 0.097 (n=364). This is only 2 calendar years and is treated as a slow regime observation, not robust evidence.
### ETHUSDT

Anchors: 105,069; features: 424; median cost: 0.093391 ATR; causal joins: True.

| Target | Ridge OOF IC | n | Best feature | Mean IC | IC t(years) | Same-sign years | Proxy/cost |
|---|---:|---:|---|---:|---:|---:|---:|
| return_15m | 0.0628 | 105,068 | 1m_ema20_distance_atr | -0.0802 | -14.0381 | 3/3 | 0.3131 |
| abs_return_15m | 0.2066 | 105,068 | perp_trade_intensity_z20d | 0.1438 | 14.3882 | 3/3 | 0.4140 |
| return_1h | -0.0026 | 105,065 | perp_large1m_imbalance_1m | -0.0625 | -1.3685 | 3/3 | 0.4841 |
| abs_return_1h | 0.1753 | 105,065 | perp_large1m_imbalance_1m | -0.1291 | -1.2384 | 3/3 | 0.7433 |
| return_4h | 0.0148 | 105,053 | perp_large1m_imbalance_1m | 0.2427 | 0.9630 | 2/3 | 3.8567 |
| abs_return_4h | 0.1675 | 105,053 | 15m_donchian55_width_atr | -0.1092 | -5.6711 | 3/3 | 1.2696 |
| return_1d | 0.0453 | 104,973 | 5m_swing_high | -0.0890 | -5.1712 | 3/3 | 3.7418 |
| abs_return_1d | 0.1911 | 104,973 | 1h_parkinson_vol14 | -0.1936 | -9.0871 | 3/3 | 5.7235 |

## Plain-language conclusion

Across 2108 market-feature inventories, stable directional relationships and purged ridge forecasts are generally tiny. 27 market/target ridge forecasts reached |OOF IC| ≥ 0.03, but the large ICs are concentrated in absolute-return targets: volatility is predictable (roughly 0.20–0.45 OOF IC, mostly from time of day), while direction is not.

The clearest directional pattern is 15-minute crypto mean reversion (for example, BTC EMA20 distance IC about -0.09), but its IC-implied move is only about 0.3× executable cost. It is information, not a net trading edge at this horizon.

The NQ/BTC one-day DVOL relationship survives daily de-overlap, but DVOL is available for only two DEV calendar years. It is a plausible slow regime proxy, not a validated directional signal. XAU `spread_modeled` has an IC t-stat of NA because the flag varied in only one year; it is a data-quality indicator and not stable evidence.

F3 on NQ, SPX and XAU cannot support a conclusion about order-flow edge because almost all intended CFD flow history was unavailable during DEV. This is a coverage failure, not evidence that order flow has no value.

Family 1 is rule-only and therefore has no feature coverage, probability fit or model gate to audit; its wide-v1 OOF rule results remain in `reports/research/wide_v1/pure_rules_summary.md`.

No model, threshold, rule or trial-ledger entry was changed by this audit.
