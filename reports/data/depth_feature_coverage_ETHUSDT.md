# Binance bookDepth feature coverage — ETHUSDT

Available snapshots: 2023-01 through 2026-11. The public UM daily archive begins 2023-01-01 (2021–2022 URLs returned 404 during downloader discovery).
First parsed snapshot: `2023-01-01 00:06:05+00:00`; last parsed snapshot: `2026-11-10 23:59:30+00:00`. Largest within-month snapshot gap: 253,620 seconds.

Each archive CSV has `timestamp`, `percentage` (−5 through −1 bid; +1 through +5 ask), `depth` (base units), and `notional` (quote units). January 2026 introduced decimal-form integral bands and an optional paired ±0.2% band. Every snapshot must contain the ten required bands. The parser pivots them to one snapshot row and sets snapshot `known_at = timestamp`. Snapshot cadence is approximately 30 seconds. Features are minute-open rows with `known_at` at minute close. Every as-of snapshot time is ≤ `known_at`; observations older than 120 seconds have `coverage=False` and NaN features. The 5% total notional avoids double-counting nested bands. The z-score uses a trailing 7D minute grid with at least two valid values and population standard deviation; missing first-history observations remain NaN.

`source_missing_day=True` marks a source archive confirmed HTTP 404. All market features, snapshot time and staleness are null on those days; coverage is false.

| Month | Source | Snapshots | Minutes | Covered | Coverage | Missing archive minutes | Stale >120s | No prior | Median cadence (s) | Max gap (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023-01 | parsed parquet | 76,296 | 44,640 | 38,190 | 85.55% | 0 | 6,444 | 6 | 29.0 | 86427 |
| 2023-02 | parsed parquet | 70,640 | 40,320 | 35,361 | 87.70% | 2,880 | 2,079 | 2,880 | 29.0 | 253620 |
| 2023-03 | parsed parquet | 85,681 | 44,640 | 42,889 | 96.08% | 0 | 1,751 | 0 | 29.0 | 58620 |
| 2023-04 | parsed parquet | 85,618 | 43,200 | 42,858 | 99.21% | 0 | 342 | 0 | 29.0 | 1294 |
| 2023-05 | parsed parquet | 88,264 | 44,640 | 44,181 | 98.97% | 0 | 459 | 0 | 29.0 | 2552 |
| 2023-06 | parsed parquet | 85,001 | 43,200 | 42,543 | 98.48% | 0 | 657 | 0 | 30.0 | 2546 |
| 2023-07 | parsed parquet | 89,201 | 44,640 | 44,606 | 99.92% | 0 | 34 | 0 | 30.0 | 660 |
| 2023-08 | parsed parquet | 89,252 | 44,640 | 44,628 | 99.97% | 0 | 12 | 0 | 30.0 | 840 |
| 2023-09 | parsed parquet | 86,372 | 43,200 | 43,188 | 99.97% | 0 | 12 | 0 | 29.0 | 870 |
| 2023-10 | parsed parquet | 89,168 | 44,640 | 44,591 | 99.89% | 0 | 49 | 0 | 29.0 | 900 |
| 2023-11 | parsed parquet | 86,342 | 43,200 | 43,175 | 99.94% | 0 | 25 | 0 | 29.0 | 900 |
| 2023-12 | parsed parquet | 89,277 | 44,640 | 44,640 | 100.00% | 0 | 0 | 0 | 29.0 | 60 |
| 2024-01 | parsed parquet | 89,190 | 44,640 | 44,600 | 99.91% | 0 | 40 | 0 | 29.0 | 992 |
| 2024-02 | parsed parquet | 83,354 | 41,760 | 41,733 | 99.94% | 0 | 27 | 0 | 29.0 | 988 |
| 2024-03 | parsed parquet | 89,209 | 44,640 | 44,611 | 99.94% | 0 | 29 | 0 | 30.0 | 1020 |
| 2024-04 | parsed parquet | 86,271 | 43,200 | 43,146 | 99.88% | 0 | 54 | 0 | 30.0 | 1080 |
| 2024-05 | parsed parquet | 89,156 | 44,640 | 44,586 | 99.88% | 0 | 54 | 0 | 30.0 | 810 |
| 2024-06 | parsed parquet | 83,518 | 43,200 | 41,761 | 96.67% | 0 | 1,439 | 0 | 30.0 | 86370 |
| 2024-07 | parsed parquet | 89,218 | 44,640 | 44,613 | 99.94% | 0 | 27 | 0 | 30.0 | 810 |
| 2024-08 | parsed parquet | 89,225 | 44,640 | 44,617 | 99.95% | 0 | 23 | 0 | 30.0 | 841 |
| 2024-09 | parsed parquet | 86,313 | 43,200 | 43,161 | 99.91% | 0 | 39 | 0 | 30.0 | 929 |
| 2024-10 | parsed parquet | 89,250 | 44,640 | 44,626 | 99.97% | 0 | 14 | 0 | 30.0 | 932 |
| 2024-11 | parsed parquet | 86,400 | 43,200 | 43,200 | 100.00% | 0 | 0 | 0 | 30.0 | 39 |
| 2024-12 | parsed parquet | 89,250 | 44,640 | 44,626 | 99.97% | 0 | 14 | 0 | 30.0 | 931 |
| 2025-01 | parsed parquet | 89,220 | 44,640 | 44,613 | 99.94% | 0 | 27 | 0 | 30.0 | 930 |
| 2025-02 | parsed parquet | 80,468 | 40,320 | 40,262 | 99.86% | 0 | 58 | 0 | 30.0 | 811 |
| 2025-03 | parsed parquet | 89,195 | 44,640 | 44,608 | 99.93% | 0 | 32 | 0 | 30.0 | 1052 |
| 2025-04 | parsed parquet | 86,352 | 43,200 | 43,184 | 99.96% | 0 | 16 | 0 | 30.0 | 1106 |
| 2025-05 | parsed parquet | 87,564 | 44,640 | 44,537 | 99.77% | 0 | 103 | 0 | 30.0 | 300 |
| 2025-06 | parsed parquet | 84,340 | 43,200 | 43,067 | 99.69% | 0 | 133 | 0 | 30.0 | 259 |
| 2025-07 | parsed parquet | 87,596 | 44,640 | 44,431 | 99.53% | 0 | 209 | 0 | 30.0 | 5371 |
| 2025-08 | parsed parquet | 87,003 | 44,640 | 44,446 | 99.57% | 0 | 194 | 0 | 30.0 | 212 |
| 2025-09 | parsed parquet | 83,788 | 43,200 | 42,973 | 99.47% | 0 | 227 | 0 | 30.0 | 219 |
| 2025-10 | parsed parquet | 87,176 | 44,640 | 44,444 | 99.56% | 0 | 196 | 0 | 30.0 | 1408 |
| 2025-11 | parsed parquet | 81,279 | 43,200 | 42,733 | 98.92% | 0 | 467 | 0 | 30.0 | 353 |
| 2025-12 | parsed parquet | 85,766 | 44,640 | 44,332 | 99.31% | 0 | 308 | 0 | 30.0 | 289 |
| 2026-01 | parsed parquet | 85,025 | 44,640 | 44,298 | 99.23% | 0 | 342 | 0 | 30.0 | 266 |
| 2026-02 | parsed parquet | 77,269 | 40,320 | 40,085 | 99.42% | 0 | 235 | 0 | 30.0 | 329 |
| 2026-03 | parsed parquet | 81,946 | 44,640 | 44,010 | 98.59% | 0 | 630 | 0 | 30.0 | 360 |
| 2026-04 | parsed parquet | 78,792 | 43,200 | 42,561 | 98.52% | 0 | 639 | 0 | 30.0 | 420 |
| 2026-05 | parsed parquet | 82,773 | 44,640 | 44,117 | 98.83% | 0 | 523 | 0 | 30.0 | 245 |
| 2026-06 | parsed parquet | 85,833 | 43,200 | 43,155 | 99.90% | 0 | 45 | 0 | 30.0 | 240 |
| 2026-07 | parsed parquet | 89,253 | 44,640 | 44,640 | 100.00% | 0 | 0 | 0 | 30.0 | 120 |
| 2026-08 | parsed parquet | 89,280 | 44,640 | 44,640 | 100.00% | 0 | 0 | 0 | 30.0 | 46 |
| 2026-09 | parsed parquet | 86,400 | 43,200 | 43,200 | 100.00% | 0 | 0 | 0 | 30.0 | 43 |
| 2026-10 | parsed parquet | 83,368 | 44,640 | 41,686 | 93.38% | 1,440 | 1,514 | 1,440 | 30.0 | 177391 |
| 2026-11 | parsed parquet | 28,800 | 14,400 | 14,400 | 100.00% | 0 | 0 | 0 | 30.0 | 48 |

Total: **3,969,952** snapshots; **2,006,552/2,030,400** minutes covered (**98.83%**). Build runtime: **6.2 s**.

The final month is partial; output stops at the close of the last downloaded source day (2026-11-10).
