# Swing v1 Stage 2 — S3 option selection, DEV only

**PASS** against frozen section 10.

One LightGBM net-R regressor, trained on all S3 entry opportunities × 12 options with exits before the predicted year. Trades are selected sequentially per market; the best predicted option is taken at ≥0.05R.

Return features are price changes divided by current ATR. High/low distances use the previous 20 or 55 daily closes. ATR percentile uses the trailing 365 calendar days including the signal day's completed bar. The first available market year is warm-up only.

| Measure | Stage 2 | Stage 1 S3 primary, same years |
|---|---:|---:|
| Trades | 481 | 426 |
| Net R/trade | 0.1840 | 0.1674 |
| Total R | 88.4839 | 71.3017 |
| t-stat | 2.0162 | 2.2077 |
| Positive-year share | 0.6154 | 0.6923 |
| No-carry R/trade | 0.2178 | 0.1911 |
| 2× cost R/trade | 0.0902 | 0.1029 |

Random-direction 95th percentile: 0.0875 R/trade (200 seeds). Evidence-market average: 0.1398 R/trade. Prediction skip rate: 0.8128.

## Pass criteria

| Criterion | Met |
|---|---|
| positive_t | True |
| positive_markets | True |
| positive_year_share | True |
| above_random_95 | True |
| positive_evidence_average | True |
| beats_primary_total_R | True |
| beats_primary_net_R_per_trade | True |

## Per market

| Market | Trades | Trades/year | Hold days | Hit rate | Net R | t | Positive years | Max DD R | SL | TP | Cap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 163 | 16.3000 | 14.3820 | 0.1840 | 0.2036 | 1.3179 | 0.7000 | 21.3105 | 107 | 30 | 26 |
| XAUUSD | 221 | 17.0000 | 16.4043 | 0.1991 | 0.1463 | 1.1377 | 0.4615 | 18.6393 | 140 | 44 | 37 |
| BTCUSDT | 97 | 19.4000 | 9.6793 | 0.3196 | 0.2369 | 1.0351 | 0.6000 | 16.5098 | 63 | 31 | 3 |
| USA500IDXUSD | 170 | 17.0000 | 14.9173 | 0.1647 | 0.1521 | 0.9754 | 0.4000 | 12.8055 | 114 | 28 | 28 |
| USA30IDXUSD | 144 | 18.0000 | 13.9041 | 0.1181 | -0.1500 | -0.9589 | 0.5000 | 22.0571 | 111 | 17 | 16 |
| DEUIDXEUR | 149 | 16.5556 | 13.6752 | 0.1544 | -0.0546 | -0.3514 | 0.5556 | 30.0232 | 108 | 23 | 18 |
| LIGHTCMDUSD | 145 | 14.5000 | 15.0119 | 0.2414 | 0.1713 | 1.1170 | 0.7000 | 10.9463 | 92 | 35 | 18 |
| BRENTCMDUSD | 133 | 13.3000 | 16.8580 | 0.2331 | 0.1878 | 1.1101 | 0.6000 | 10.8150 | 85 | 31 | 17 |
| XAGUSD | 162 | 12.4615 | 14.6764 | 0.2284 | 0.1063 | 0.7355 | 0.5385 | 26.6752 | 105 | 37 | 20 |
| EURUSD | 212 | 16.3077 | 17.4883 | 0.1557 | 0.2850 | 2.0842 | 0.7692 | 17.6718 | 128 | 33 | 51 |
| GBPUSD | 214 | 16.4615 | 16.4613 | 0.1075 | 0.0124 | 0.0928 | 0.5385 | 34.1432 | 150 | 23 | 41 |
| USDJPY | 203 | 15.6154 | 16.2352 | 0.1626 | 0.2022 | 1.4094 | 0.6923 | 25.1623 | 132 | 33 | 38 |
| ETHUSDT | 94 | 18.8000 | 9.3078 | 0.2553 | 0.4855 | 1.9268 | 0.6000 | 15.2276 | 62 | 24 | 8 |

## Per predicted year, traded markets pooled

| Year | Stage 2 trades | Stage 2 net R | Stage 1 primary trades | Stage 1 primary net R |
|---|---:|---:|---:|---:|
| 2010 | 12 | 0.4480 | 12 | 0.6635 |
| 2011 | 16 | 0.6884 | 17 | 0.5464 |
| 2012 | 11 | -0.3518 | 13 | -0.1841 |
| 2013 | 21 | 0.4044 | 22 | 0.6237 |
| 2014 | 33 | -0.0722 | 30 | 0.0450 |
| 2015 | 38 | -0.3378 | 33 | -0.0451 |
| 2016 | 35 | 0.3582 | 30 | 0.0757 |
| 2017 | 24 | 0.2600 | 29 | 0.2825 |
| 2018 | 42 | -0.0766 | 45 | -0.0333 |
| 2019 | 61 | 0.2133 | 51 | 0.2289 |
| 2020 | 72 | 0.7152 | 58 | 0.3773 |
| 2021 | 67 | -0.1078 | 44 | -0.0613 |
| 2022 | 49 | 0.2010 | 42 | 0.0723 |

## Chosen option distribution

| Option | Trades |
|---|---:|
| 1ATR_1.5R | 56 |
| 1ATR_2R | 22 |
| 1ATR_3R | 52 |
| 1ATR_5R | 254 |
| 2ATR_1.5R | 2 |
| 2ATR_2R | 5 |
| 2ATR_3R | 6 |
| 2ATR_5R | 51 |
| 3ATR_1.5R | 8 |
| 3ATR_2R | 2 |
| 3ATR_3R | 9 |
| 3ATR_5R | 14 |

## Model audit

| Predicted year | Training rows | Latest training exit |
|---|---:|---|
| 2010 | 16536 | 2009-12-30T14:49:00.000000000 |
| 2011 | 19532 | 2010-12-31T15:57:00.000000000 |
| 2012 | 22844 | 2011-12-29T11:58:00.000000000 |
| 2013 | 25933 | 2012-12-31T17:47:00.000000000 |
| 2014 | 30211 | 2013-12-31T16:12:00.000000000 |
| 2015 | 36256 | 2014-12-30T23:00:00.000000000 |
| 2016 | 42349 | 2015-12-31T15:26:00.000000000 |
| 2017 | 48420 | 2016-12-30T19:50:00.000000000 |
| 2018 | 54417 | 2017-12-29T18:15:00.000000000 |
| 2019 | 63810 | 2018-12-31T23:00:00.000000000 |
| 2020 | 74104 | 2019-12-31T23:00:00.000000000 |
| 2021 | 84647 | 2020-12-31T23:00:00.000000000 |
| 2022 | 95149 | 2021-12-31T20:36:00.000000000 |

The JSON includes all per-market and per-year metrics, skip counts, model settings, and the fixed evidence cost mapping. The 07:00 entry requires an exact minute. An unresolved chosen option at the DEV cutoff is dropped.
