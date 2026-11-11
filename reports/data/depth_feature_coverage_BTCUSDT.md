# Binance bookDepth feature coverage — BTCUSDT

Available snapshots: 2023-01 through 2026-01. The public UM daily archive begins 2023-01-01 (2021–2022 URLs returned 404 during downloader discovery).
First parsed snapshot: `2023-01-01 00:06:05+00:00`; last parsed snapshot: `2026-01-31 23:59:33+00:00`. Largest within-month snapshot gap: 253,620 seconds.

Each archive CSV has `timestamp`, `percentage` (−5 through −1 bid; +1 through +5 ask), `depth` (base units), and `notional` (quote units). Some January 2026 archives encode integral bands as decimals (for example `-5.00`) and add an optional paired ±0.2% band; the existing parser stops at the decimal, so this feature build validates SHA256 sidecars and parses those raw ZIPs directly. Every snapshot must contain the ten required bands. The parser pivots them to one snapshot row and sets snapshot `known_at = timestamp`. Snapshot cadence is approximately 30 seconds. Features are minute-open rows with `known_at` at minute close. Every as-of snapshot time is ≤ `known_at`; observations older than 120 seconds have `coverage=False` and NaN features. The 5% total notional avoids double-counting nested bands. The z-score uses a trailing 7D minute grid with at least two valid values and population standard deviation; missing first-history observations remain NaN.

| Month | Source | Snapshots | Minutes | Covered | Coverage | Stale >120s | No prior | Median cadence (s) | Max gap (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023-01 | parsed parquet | 76,296 | 44,640 | 38,190 | 85.55% | 6,444 | 6 | 29.0 | 86427 |
| 2023-02 | parsed parquet | 70,640 | 40,320 | 35,361 | 87.70% | 4,959 | 0 | 29.0 | 253620 |
| 2023-03 | parsed parquet | 85,681 | 44,640 | 42,889 | 96.08% | 1,751 | 0 | 29.0 | 58620 |
| 2023-04 | parsed parquet | 82,761 | 43,200 | 41,429 | 95.90% | 1,771 | 0 | 29.0 | 87000 |
| 2023-05 | parsed parquet | 79,746 | 44,640 | 39,917 | 89.42% | 4,723 | 0 | 29.0 | 87568 |
| 2023-06 | parsed parquet | 82,133 | 43,200 | 41,107 | 95.16% | 2,093 | 0 | 30.0 | 86615 |
| 2023-07 | parsed parquet | 83,458 | 44,640 | 41,734 | 93.49% | 2,906 | 0 | 30.0 | 86437 |
| 2023-08 | parsed parquet | 89,252 | 44,640 | 44,628 | 99.97% | 12 | 0 | 30.0 | 840 |
| 2023-09 | parsed parquet | 86,372 | 43,200 | 43,188 | 99.97% | 12 | 0 | 29.0 | 870 |
| 2023-10 | parsed parquet | 89,168 | 44,640 | 44,591 | 99.89% | 49 | 0 | 29.0 | 900 |
| 2023-11 | parsed parquet | 86,342 | 43,200 | 43,175 | 99.94% | 25 | 0 | 29.0 | 900 |
| 2023-12 | parsed parquet | 89,277 | 44,640 | 44,640 | 100.00% | 0 | 0 | 29.0 | 60 |
| 2024-01 | parsed parquet | 80,551 | 44,640 | 40,283 | 90.24% | 4,357 | 0 | 29.0 | 86442 |
| 2024-02 | parsed parquet | 80,474 | 41,760 | 40,294 | 96.49% | 1,466 | 0 | 29.0 | 86439 |
| 2024-03 | parsed parquet | 86,329 | 44,640 | 43,172 | 96.71% | 1,468 | 0 | 30.0 | 86438 |
| 2024-04 | parsed parquet | 77,631 | 43,200 | 38,829 | 89.88% | 4,371 | 0 | 30.0 | 86439 |
| 2024-05 | parsed parquet | 89,156 | 44,640 | 44,586 | 99.88% | 54 | 0 | 30.0 | 810 |
| 2024-06 | parsed parquet | 83,518 | 43,200 | 41,761 | 96.67% | 1,439 | 0 | 30.0 | 86370 |
| 2024-07 | parsed parquet | 89,218 | 44,640 | 44,613 | 99.94% | 27 | 0 | 30.0 | 810 |
| 2024-08 | parsed parquet | 89,225 | 44,640 | 44,617 | 99.95% | 23 | 0 | 30.0 | 841 |
| 2024-09 | parsed parquet | 86,313 | 43,200 | 43,161 | 99.91% | 39 | 0 | 30.0 | 929 |
| 2024-10 | parsed parquet | 89,250 | 44,640 | 44,626 | 99.97% | 14 | 0 | 30.0 | 932 |
| 2024-11 | parsed parquet | 86,400 | 43,200 | 43,200 | 100.00% | 0 | 0 | 30.0 | 39 |
| 2024-12 | parsed parquet | 89,250 | 44,640 | 44,626 | 99.97% | 14 | 0 | 30.0 | 931 |
| 2025-01 | parsed parquet | 89,220 | 44,640 | 44,613 | 99.94% | 27 | 0 | 30.0 | 930 |
| 2025-02 | parsed parquet | 80,468 | 40,320 | 40,262 | 99.86% | 58 | 0 | 30.0 | 811 |
| 2025-03 | parsed parquet | 89,195 | 44,640 | 44,608 | 99.93% | 32 | 0 | 30.0 | 1052 |
| 2025-04 | parsed parquet | 86,352 | 43,200 | 43,184 | 99.96% | 16 | 0 | 30.0 | 1106 |
| 2025-05 | parsed parquet | 87,564 | 44,640 | 44,537 | 99.77% | 103 | 0 | 30.0 | 300 |
| 2025-06 | parsed parquet | 84,340 | 43,200 | 43,067 | 99.69% | 133 | 0 | 30.0 | 259 |
| 2025-07 | parsed parquet | 87,596 | 44,640 | 44,431 | 99.53% | 209 | 0 | 30.0 | 5371 |
| 2025-08 | parsed parquet | 87,003 | 44,640 | 44,446 | 99.57% | 194 | 0 | 30.0 | 212 |
| 2025-09 | parsed parquet | 83,788 | 43,200 | 42,973 | 99.47% | 227 | 0 | 30.0 | 219 |
| 2025-10 | parsed parquet | 87,176 | 44,640 | 44,444 | 99.56% | 196 | 0 | 30.0 | 1408 |
| 2025-11 | parsed parquet | 81,279 | 43,200 | 42,733 | 98.92% | 467 | 0 | 30.0 | 353 |
| 2025-12 | parsed parquet | 85,766 | 44,640 | 44,332 | 99.31% | 308 | 0 | 30.0 | 289 |
| 2026-01 | verified raw ZIP | 85,025 | 44,640 | 44,298 | 99.23% | 342 | 0 | 30.0 | 266 |

Total: **3,143,213** snapshots; **1,582,545/1,622,880** minutes covered (**97.51%**). Build runtime: **3.4 s**.
