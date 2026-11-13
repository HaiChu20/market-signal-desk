# Swing v1 — FINAL test

**NOT BROKEN** — the frozen main-version verdict is based only on pooled net R per trade being greater than zero.

Trades entered before 2025-01-01 UTC are not scored. The main version carries one-trade-per-market state from the 2023–24 warm-up. The Stage 2 version is reported only and does not affect the verdict.

| Version | Trades | Net R/trade | t | No-carry R | 2× cost R | Random 95% R | Evidence avg R | Unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Main: S3, 2 ATR / 3R | 88 | 0.0368 | 0.2333 | 0.0694 | -0.0059 | 0.2624 | -0.1535 | 13 |
| Stage 2 walk-forward | 82 | 0.0894 | 0.4442 | 0.1231 | 0.0445 | 0.4107 | 0.0104 | 10 |

## Main version: per market

| Market | Trades | Net R | t | No-carry R | 2× cost R |
|---|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 27 | -0.1809 | -0.7378 | -0.1309 | -0.2333 |
| XAUUSD | 29 | 0.4482 | 1.4416 | 0.4873 | 0.4055 |
| BTCUSDT | 32 | -0.1523 | -0.6078 | -0.1404 | -0.1869 |
| USA500IDXUSD | 25 | -0.3136 | -1.3447 | -0.2449 | -0.3895 |
| USA30IDXUSD | 26 | -0.2998 | -1.4449 | -0.2429 | -0.3634 |
| DEUIDXEUR | 29 | -0.1816 | -0.7686 | -0.1330 | -0.2363 |
| LIGHTCMDUSD | 31 | -0.0189 | -0.0697 | -0.0377 | -0.0045 |
| BRENTCMDUSD | 33 | -0.0050 | -0.0184 | -0.0225 | 0.0078 |
| XAGUSD | 25 | 0.6057 | 1.8067 | 0.6351 | 0.5720 |
| EURUSD | 23 | -0.3356 | -1.2842 | -0.3143 | -0.3720 |
| GBPUSD | 29 | -0.6798 | -4.9401 | -0.6884 | -0.6848 |
| USDJPY | 24 | -0.1076 | -0.3996 | -0.0448 | -0.1824 |
| ETHUSDT | 35 | -0.1987 | -0.7821 | -0.2065 | -0.2526 |

## Main version: traded markets per year

| Year | Trades | Net R | t | No-carry R | 2× cost R |
|---|---:|---:|---:|---:|---:|
| 2025 | 48 | 0.1040 | 0.4811 | 0.1590 | 0.0395 |
| 2026 | 40 | -0.0439 | -0.1887 | -0.0382 | -0.0604 |

## Stage 2 version: per market

| Market | Trades | Net R | t | No-carry R | 2× cost R |
|---|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 29 | -0.1603 | -0.5697 | -0.1138 | -0.2097 |
| XAUUSD | 28 | 0.4464 | 1.1226 | 0.4701 | 0.4184 |
| BTCUSDT | 25 | -0.0208 | -0.0571 | 0.0091 | -0.0794 |
| USA500IDXUSD | 26 | -0.1354 | -0.4085 | -0.0584 | -0.2209 |
| USA30IDXUSD | 24 | -0.1532 | -0.6385 | -0.0777 | -0.2369 |
| DEUIDXEUR | 26 | 0.0403 | 0.1145 | 0.1006 | -0.0266 |
| LIGHTCMDUSD | 30 | -0.3419 | -1.2088 | -0.3546 | -0.3350 |
| BRENTCMDUSD | 28 | 0.5060 | 1.2435 | 0.4916 | 0.5145 |
| XAGUSD | 19 | 0.7882 | 1.6178 | 0.8275 | 0.7440 |
| EURUSD | 22 | -0.1136 | -0.3488 | -0.0510 | -0.1948 |
| GBPUSD | 34 | -0.5597 | -2.9644 | -0.5653 | -0.5724 |
| USDJPY | 29 | 0.0552 | 0.1627 | 0.1044 | -0.0084 |
| ETHUSDT | 30 | 0.0181 | 0.0522 | 0.0138 | -0.0516 |

## Stage 2 version: traded markets per year

| Year | Trades | Net R | t | No-carry R | 2× cost R |
|---|---:|---:|---:|---:|---:|
| 2025 | 37 | 0.3476 | 1.1025 | 0.4245 | 0.2599 |
| 2026 | 45 | -0.1229 | -0.4757 | -0.1248 | -0.1326 |

## Stage 2 model audit

| Predicted year | Training rows | Latest training exit |
|---|---:|---|
| 2025 | 126646 | 2024-12-31T23:00:00.000000000 |
| 2026 | 137012 | 2025-12-31T23:00:00.000000000 |

The JSON report contains all summaries, selection counts, unresolved counts, model settings, and opportunity-drop audit fields.
