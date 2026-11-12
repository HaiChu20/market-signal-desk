# Stage 9 production audit

All builds used the preregistered financing addendum, nice priority, atomic verified monthly writes, and the 15 GiB free-space guard.

| Market | Wall time | Peak RSS | Output size | Feature/source coverage | Feature range | Truncation |
|---|---:|---:|---:|---:|---|---|
| USA30IDXUSD | 0.63 h | 4.85 GiB | 2.43 GiB | 2,915,811/2,916,623 (99.9722%) | 2018-05-01 00:00:00+00:00 – 2026-11-10 23:59:00+00:00 | PASS (all 5 HTFs unchanged through 2024-09-16T12:00:00+00:00) |
| DEUIDXEUR | 0.46 h | 3.59 GiB | 1.92 GiB | 2,308,756/2,309,059 (99.9869%) | 2020-01-01 23:04:00+00:00 – 2026-11-10 23:59:00+00:00 | PASS (all 5 HTFs unchanged through 2024-09-16T11:00:00+00:00) |
| XAGUSD | 0.51 h | 3.43 GiB | 1.88 GiB | 2,414,716/2,416,541 (99.9245%) | 2020-01-01 23:00:00+00:00 – 2026-11-10 23:59:00+00:00 | PASS (all 5 HTFs unchanged through 2024-09-16T12:00:00+00:00) |
| EURUSD | 4.86 h | 6.19 GiB | 6.87 GiB | 8,788,447/8,788,941 (99.9944%) | 2003-05-04 21:00:00+00:00 – 2026-11-10 23:59:00+00:00 | PASS (all 5 HTFs unchanged through 2024-09-16T10:00:00+00:00) |
| USDJPY | 6.26 h | 6.07 GiB | 6.69 GiB | 8,769,124/8,770,529 (99.9840%) | 2003-05-04 21:00:00+00:00 – 2026-11-10 23:59:00+00:00 | PASS (all 5 HTFs unchanged through 2024-09-16T10:00:00+00:00) |
| GBPUSD | 8.63 h | 8.22 GiB | 6.86 GiB | 8,784,414/8,785,223 (99.9908%) | 2003-05-04 21:00:00+00:00 – 2026-11-10 23:59:00+00:00 | PASS (all 5 HTFs unchanged through 2024-09-16T11:00:00+00:00) |
| LIGHTCMDUSD | 1.28 h | 6.51 GiB | 3.42 GiB | 4,439,119/4,440,207 (99.9755%) | 2013-05-23 07:00:00+00:00 – 2026-11-10 23:59:00+00:00 | PASS (all 5 HTFs unchanged through 2024-09-16T11:00:00+00:00) |
| BRENTCMDUSD | 1.14 h | 5.62 GiB | 3.21 GiB | 4,147,513/4,148,230 (99.9827%) | 2013-05-23 07:00:00+00:00 – 2026-11-10 21:59:00+00:00 | PASS (all 5 HTFs unchanged through 2024-09-16T12:00:00+00:00) |

Wall time includes operator-requested pauses for EURUSD, USDJPY and GBPUSD.

## Oil quote exclusion audit

Invalid observed quotes were removed before features, events, or labels; no spread was filled or invented.

| Market | Excluded | Non-finite | Zero spread | Crossed | First affected month | Last affected month |
|---|---:|---:|---:|---:|---|---|
| LIGHTCMDUSD | 430,950 | 0 | 430,950 | 9 | 2012-01 | 2013-09 |
| BRENTCMDUSD | 276,637 | 0 | 276,637 | 5 | 2012-01 | 2013-08 |

The raw-source diagnostic found 430,984 WTI and 276,645 Brent invalid quote rows; the build audit above is slightly lower because the standard bad-tick/stale filter runs first.
The invalid oil regime predates the April 2020 WTI shock; April 2020 had zero invalid and zero negative-price quote rows in both local CFD feeds.
