# Flow feature coverage: BTCUSDT

Coverage includes verified source files with no activity; unavailable source periods remain NaN.

| Year | Source flag | Covered rows | Total rows | Coverage |
|---:|---|---:|---:|---:|
| 2017 | `bybit_flow_coverage` | 0 | 196544 | 0.00% |
| 2017 | `flow_coverage` | 196544 | 196544 | 100.00% |
| 2017 | `perp_flow_coverage` | 0 | 196544 | 0.00% |
| 2017 | `spot_flow_coverage` | 196544 | 196544 | 100.00% |
| 2017 | `tick_flow_coverage` | 0 | 196544 | 0.00% |
| 2018 | `bybit_flow_coverage` | 0 | 521624 | 0.00% |
| 2018 | `flow_coverage` | 521624 | 521624 | 100.00% |
| 2018 | `perp_flow_coverage` | 0 | 521624 | 0.00% |
| 2018 | `spot_flow_coverage` | 521624 | 521624 | 100.00% |
| 2018 | `tick_flow_coverage` | 0 | 521624 | 0.00% |
| 2019 | `bybit_flow_coverage` | 0 | 523836 | 0.00% |
| 2019 | `flow_coverage` | 523836 | 523836 | 100.00% |
| 2019 | `perp_flow_coverage` | 0 | 523836 | 0.00% |
| 2019 | `spot_flow_coverage` | 523836 | 523836 | 100.00% |
| 2019 | `tick_flow_coverage` | 0 | 523836 | 0.00% |
| 2020 | `bybit_flow_coverage` | 405370 | 525788 | 77.10% |
| 2020 | `flow_coverage` | 525788 | 525788 | 100.00% |
| 2020 | `perp_flow_coverage` | 525788 | 525788 | 100.00% |
| 2020 | `spot_flow_coverage` | 525788 | 525788 | 100.00% |
| 2020 | `tick_flow_coverage` | 0 | 525788 | 0.00% |
| 2021 | `bybit_flow_coverage` | 524607 | 524607 | 100.00% |
| 2021 | `flow_coverage` | 524607 | 524607 | 100.00% |
| 2021 | `perp_flow_coverage` | 524607 | 524607 | 100.00% |
| 2021 | `spot_flow_coverage` | 524607 | 524607 | 100.00% |
| 2021 | `tick_flow_coverage` | 0 | 524607 | 0.00% |
| 2022 | `bybit_flow_coverage` | 525600 | 525600 | 100.00% |
| 2022 | `flow_coverage` | 525600 | 525600 | 100.00% |
| 2022 | `perp_flow_coverage` | 525600 | 525600 | 100.00% |
| 2022 | `spot_flow_coverage` | 525600 | 525600 | 100.00% |
| 2022 | `tick_flow_coverage` | 0 | 525600 | 0.00% |
| 2023 | `bybit_flow_coverage` | 525520 | 525520 | 100.00% |
| 2023 | `flow_coverage` | 525520 | 525520 | 100.00% |
| 2023 | `perp_flow_coverage` | 525520 | 525520 | 100.00% |
| 2023 | `spot_flow_coverage` | 525520 | 525520 | 100.00% |
| 2023 | `tick_flow_coverage` | 0 | 525520 | 0.00% |
| 2024 | `bybit_flow_coverage` | 527040 | 527040 | 100.00% |
| 2024 | `flow_coverage` | 527040 | 527040 | 100.00% |
| 2024 | `perp_flow_coverage` | 527040 | 527040 | 100.00% |
| 2024 | `spot_flow_coverage` | 527040 | 527040 | 100.00% |
| 2024 | `tick_flow_coverage` | 0 | 527040 | 0.00% |
| 2025 | `bybit_flow_coverage` | 525600 | 525600 | 100.00% |
| 2025 | `flow_coverage` | 525600 | 525600 | 100.00% |
| 2025 | `perp_flow_coverage` | 525600 | 525600 | 100.00% |
| 2025 | `spot_flow_coverage` | 525600 | 525600 | 100.00% |
| 2025 | `tick_flow_coverage` | 0 | 525600 | 0.00% |
| 2026 | `bybit_flow_coverage` | 437760 | 437760 | 100.00% |
| 2026 | `flow_coverage` | 437760 | 437760 | 100.00% |
| 2026 | `perp_flow_coverage` | 437760 | 437760 | 100.00% |
| 2026 | `spot_flow_coverage` | 437760 | 437760 | 100.00% |
| 2026 | `tick_flow_coverage` | 0 | 437760 | 0.00% |

## Feature definitions

All flow values are known at the minute close (`known_at`), plus any source publication lag. A rolling window is valid when at least 80% of its clock minutes have verified source coverage. Covered minutes with no activity contribute zero; missing source periods remain NaN.

- `*_delta_{1,5,15,60}m`: sum of buy volume minus sell volume over the trailing window.
- `*_imbalance_{1,5,15,60}m`: trailing delta divided by total buy plus sell volume.
- `*_large100k_imbalance_1m`, `*_large1m_imbalance_1m`: buy minus sell notional for trades at or above 100k/1m USDT, divided by that bucket's total notional; NaN where the source lacks sided large-trade totals.
- `*_trade_intensity_z20d`: current trade count z-scored against the trailing 20×24×60 minute window (minimum 1×24×60 observations; population standard deviation).
- `spot_perp_delta_spread_*`, `spot_bybit_delta_spread_*`: difference between the two venues' trailing base-quantity deltas.
- `cum_delta_divergence_60m`: negative sign of spot 60-minute delta multiplied by the 60-bar primary-price return; positive values indicate price/delta disagreement.
- `ticks_ofi`, `ticks_size_imbalance`, `ticks_tick_count`, `ticks_mean_spread`, `ticks_max_spread`: same-minute Dukascopy tick aggregates.

## Feature columns

- `flow_coverage`
- `tick_flow_coverage`
- `spot_flow_coverage`
- `spot_trade_intensity_z20d`
- `spot_large100k_imbalance_1m`
- `spot_large1m_imbalance_1m`
- `spot_delta_1m`
- `spot_imbalance_1m`
- `spot_delta_5m`
- `spot_imbalance_5m`
- `spot_delta_15m`
- `spot_imbalance_15m`
- `spot_delta_60m`
- `spot_imbalance_60m`
- `perp_flow_coverage`
- `perp_trade_intensity_z20d`
- `perp_large100k_imbalance_1m`
- `perp_large1m_imbalance_1m`
- `perp_delta_1m`
- `perp_imbalance_1m`
- `perp_delta_5m`
- `perp_imbalance_5m`
- `perp_delta_15m`
- `perp_imbalance_15m`
- `perp_delta_60m`
- `perp_imbalance_60m`
- `bybit_flow_coverage`
- `bybit_trade_intensity_z20d`
- `bybit_large100k_imbalance_1m`
- `bybit_large1m_imbalance_1m`
- `bybit_delta_1m`
- `bybit_imbalance_1m`
- `bybit_delta_5m`
- `bybit_imbalance_5m`
- `bybit_delta_15m`
- `bybit_imbalance_15m`
- `bybit_delta_60m`
- `bybit_imbalance_60m`
- `spot_perp_delta_spread_1m`
- `spot_bybit_delta_spread_1m`
- `spot_perp_delta_spread_5m`
- `spot_bybit_delta_spread_5m`
- `spot_perp_delta_spread_15m`
- `spot_bybit_delta_spread_15m`
- `spot_perp_delta_spread_60m`
- `spot_bybit_delta_spread_60m`
- `cum_delta_divergence_60m`
- `perp_uncovered_volume`
- `perp_um_kline_agg_mismatch`
- `ticks_ofi`
- `ticks_size_imbalance`
- `ticks_tick_count`
- `ticks_mean_spread`
- `ticks_max_spread`
- `ticks_bid_size_sum`
- `ticks_ask_size_sum`
- `ticks_count_z20d`
- `ticks_ofi_5m`
- `ticks_size_imbalance_5m`
- `ticks_tick_count_5m`
- `ticks_ofi_15m`
- `ticks_size_imbalance_15m`
- `ticks_tick_count_15m`
- `ticks_ofi_60m`
- `ticks_size_imbalance_60m`
- `ticks_tick_count_60m`
