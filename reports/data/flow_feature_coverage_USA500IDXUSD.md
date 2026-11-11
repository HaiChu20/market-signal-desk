# Flow feature coverage: USA500IDXUSD

Coverage includes verified source files with no activity; unavailable source periods remain NaN.

| Year | Source flag | Covered rows | Total rows | Coverage |
|---:|---|---:|---:|---:|
| 2023 | `bybit_flow_coverage` | 0 | 278275 | 0.00% |
| 2023 | `flow_coverage` | 275905 | 278275 | 99.15% |
| 2023 | `perp_flow_coverage` | 0 | 278275 | 0.00% |
| 2023 | `spot_flow_coverage` | 0 | 278275 | 0.00% |
| 2023 | `tick_flow_coverage` | 275905 | 278275 | 99.15% |
| 2024 | `bybit_flow_coverage` | 0 | 335016 | 0.00% |
| 2024 | `flow_coverage` | 334301 | 335016 | 99.79% |
| 2024 | `perp_flow_coverage` | 0 | 335016 | 0.00% |
| 2024 | `spot_flow_coverage` | 0 | 335016 | 0.00% |
| 2024 | `tick_flow_coverage` | 334301 | 335016 | 99.79% |
| 2025 | `bybit_flow_coverage` | 0 | 339139 | 0.00% |
| 2025 | `flow_coverage` | 339139 | 339139 | 100.00% |
| 2025 | `perp_flow_coverage` | 0 | 339139 | 0.00% |
| 2025 | `spot_flow_coverage` | 0 | 339139 | 0.00% |
| 2025 | `tick_flow_coverage` | 339139 | 339139 | 100.00% |
| 2026 | `bybit_flow_coverage` | 0 | 294641 | 0.00% |
| 2026 | `flow_coverage` | 294641 | 294641 | 100.00% |
| 2026 | `perp_flow_coverage` | 0 | 294641 | 0.00% |
| 2026 | `spot_flow_coverage` | 0 | 294641 | 0.00% |
| 2026 | `tick_flow_coverage` | 294641 | 294641 | 100.00% |

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
