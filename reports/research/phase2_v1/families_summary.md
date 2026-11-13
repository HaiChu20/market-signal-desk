# Phase 2 v1 — feature-family DEV summary

**Development only (decisions and label ends before 2023-01-01). Test and Final were not loaded.**

LightGBM residual models use the geometric p0 offset. CPCV predictions use purging and a one-trading-day embargo. Training anchors are hourly (at most 25,000 per fold) to cap RSS; evaluation anchors remain 15-minute.

DXY and Treasury yields are unavailable in v1 and are not included in F5.

| Family | Market | OOF net R | Trades/year | Hit | t | PF | Brier skill vs p0 | Brier skill vs cell base | Random pct | Beat base + net > 0 | Runtime min | Peak GiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| f3_order_flow | BTCUSDT | -0.2180 | 2.3328 | 0.4286 | -0.7490 | 0.5418 | 0.1206 | -0.0011 | 50.0000 | no | 0.90 | 5.05 |
| f3_order_flow | ETHUSDT | -0.2190 | 5.9987 | 0.3333 | -0.8895 | 0.6286 | 0.1117 | -0.0041 | 74.0000 | no | 0.94 | 5.14 |
| f3_order_flow | USA500IDXUSD | -0.3029 | 3.0043 | 0.5000 | -1.3876 | 0.4096 | 0.1138 | -0.0076 | 8.5000 | no | 0.77 | 4.44 |
| f3_order_flow | USATECHIDXUSD | NA | 0.0000 | NA | NA | NA | 0.0970 | -0.0057 | NA | no | 0.76 | 4.07 |
| f3_order_flow | XAUUSD | NA | 0.0000 | NA | NA | NA | 0.1218 | -0.0027 | NA | no | 2.78 | 5.45 |
| f4_regime | BTCUSDT | -0.8365 | 0.6665 | 0.0000 | -14.5377 | 0.0000 | 0.1194 | -0.0024 | 47.5000 | no | 2.23 | 7.63 |
| f4_regime | ETHUSDT | -0.3746 | 5.6654 | 0.2941 | -1.8731 | 0.3977 | 0.1136 | -0.0020 | 63.5000 | no | 2.23 | 8.40 |
| f4_regime | USA500IDXUSD | NA | 0.0000 | NA | NA | NA | 0.1160 | -0.0051 | NA | no | 1.94 | 8.76 |
| f4_regime | USATECHIDXUSD | 0.1562 | 3.7554 | 0.8000 | 1.6330 | 2.8729 | 0.1021 | 0.0000 | 98.5000 | yes | 1.88 | 7.80 |
| f4_regime | XAUUSD | -0.1557 | 2.3344 | 0.6286 | -1.3861 | 0.5706 | 0.1260 | 0.0021 | 13.0000 | no | 6.29 | 8.43 |
| f5_cross_market | BTCUSDT | -0.1020 | 2.6661 | 0.6250 | -0.4287 | 0.6942 | 0.1128 | -0.0100 | 64.0000 | no | 0.89 | 4.80 |
| f5_cross_market | ETHUSDT | -0.3030 | 6.3319 | 0.3684 | -1.6643 | 0.4579 | 0.1055 | -0.0111 | 70.5000 | no | 0.93 | 4.46 |
| f5_cross_market | USA500IDXUSD | NA | 0.0000 | NA | NA | NA | 0.1154 | -0.0057 | NA | no | 0.79 | 4.13 |
| f5_cross_market | USATECHIDXUSD | -0.3650 | 2.2532 | 0.4444 | -1.4186 | 0.3530 | 0.0995 | -0.0028 | 0.5000 | no | 0.80 | 3.96 |
| f5_cross_market | XAUUSD | NA | 0.0000 | NA | NA | NA | 0.1207 | -0.0040 | NA | no | 2.57 | 7.55 |
