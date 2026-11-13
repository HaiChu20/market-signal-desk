# Final check v2: three more rules on 2025+ (frozen before any result)

Date: 2026-11-13. The user asked to add three more rules to the live bot: the swing 20-day and 55-day
breakouts and the intraday 20-hour Donchian breakout. Before switching them on, each is checked **once**
on the 2025+ Final period, which none of them has seen. This file freezes the check before it runs. No
rerun, no regrade, and no change to any rule, market or setting after seeing the result.

## A. Swing S1 (Breakout 20) and S2 (Breakout 55)

- Rules exactly as in `docs/swing_v1_design.md` sections 2–6: daily bars closing at 17:00 New York,
  07:00 UTC next-day entry, Globex hours, gap fills, 30-session cap, section 6 costs with carry.
- **Primary option only: SL 2 ATR, TP 3R.** One open trade per market *within each setup*. S1 and S2 are
  graded separately and independently of S3.
- Markets, period, warm-up, open-at-end handling: exactly as section 11 of the swing design (MNQ/MGC/MBT
  pooled; trades entered from 2025-01-01 00:00 UTC to the end of the local data; warm-up and state from
  2023-01-01; trades entered before 2025 are never scored).
- **Verdict per rule:** KEEP if pooled net R per trade > 0, else DROP (not deployed).
- Also reported, without changing the verdict: t-stat, per market, per year, no-carry and 2× cost rows,
  random-direction 95th percentile (200 seeds), the evidence markets.
- One ledger row per rule in reports/trials.csv.

## B. Intraday Donchian ATR breakout

- Rule, code and settings exactly as in `docs/test_preregistration_v1.md` (frozen detector commit
  `a196fdd982e10aa4f3d4dffc08e59382615ce53a`, wide_v1 config SHA-256 `1cab0902…a1dd`): 1-hour Donchian-20
  breakout detected each minute, stop 3 × 1h ATR14, target 3R, maximum hold one trading day, the same
  CFD and BTC perpetual cost conventions, the same one-position-per-symbol gate.
- Markets: USATECHIDXUSD, USA500IDXUSD, XAUUSD, BTCUSDT, pooled. **All four go live together if KEEP**;
  no market is dropped or added after seeing results.
- Period: decisions from 2025-01-01 00:00 UTC to the end of the local data. Detector state and features may
  warm up on data before 2025. Trades still open at the end of the data are dropped and counted.
- **Verdict:** KEEP if pooled net R per trade > 0, else DROP.
- Also reported, without changing the verdict: trade count, hit rate, t-stat, profit factor, random-direction
  percentile (200 seeds), per market and per year.
- One ledger row in reports/trials.csv.

## Notes

- With roughly 50–100 trades per rule this check can only catch a clear failure; it cannot prove an edge.
- A KEEP rule goes live as a labelled, low-confidence signal. Swing rules keep their entry/SL/TP format;
  the intraday rule uses live Capital.com 1-minute prices, which differ slightly from the Dukascopy prices
  it was tested on.
- If a genuine software or data bug is found after results are seen, stop, report it, and do not regrade.
