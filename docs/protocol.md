# Evaluation protocol v2 (pre-registered 2026-11-10, before any v2 model is trained)

This protocol covers every method model in the 35-method tournament and every combined model
built later. Changes require a new protocol version, written down **before** the results they
would affect are seen.

## 1. Data periods
| Period | Range | Use |
|---|---|---|
| Development | first available → 2022-12-31 | Feature and model design. Hyperparameter search uses combinatorial purged cross-validation (CPCV) only. |
| Test | 2023-01-01 → 2024-12-31 | Grading. One evaluation per method version; every evaluation is logged in the trial ledger. |
| Final | 2025-01-01 → latest | **Locked.** Evaluated once, for all surviving methods together, at the end of the tournament. Semi-contaminated, because the v1 strategies were judged on it; this is stated in every report. |
| Forward paper | from bot go-live | The real arbiter. No real money before ≥3 months of forward paper results. |

Purging: training rows whose label window overlaps the evaluation fold are dropped. Embargo:
1 trading day after each evaluation fold.

## 2. Causality
- Every derived value (feature, level, event, label input) carries a `known_at` timestamp.
  All joins are as-of joins: `known_at ≤ decision time`.
- A swing pivot is known only after its k right-hand bars close. A pattern is known only when its
  last pivot is confirmed. Session and prior-day levels respect real session boundaries.
- All normalisation uses trailing windows only.
- Truncation test: recomputing on data cut at a random time t must reproduce every value and decision
  ≤ t, including when future prices and volume are perturbed. It runs on the full pipeline.

## 3. Execution and cost model
- Signal is known at the close of bar t. **Entry at the open of bar t+2** (≥1 min manual delay).
  Limit-order signals fill only if price trades through the limit before expiry.
- Longs buy at ask and exit at bid; shorts the reverse. Where a source has no bid/ask, a per-instrument,
  per-year modelled spread is used; sensitivity is also reported at 1.5× spread.
- Stops are intrabar. If SL and TP are hit in the same bar, SL counts first. A gap through the stop fills
  at the bar open. Time exits at the open of the first bar at or after the exit time (shared
  `evaluate_bar()` code for backtest and live).
- Maximum holding time is 5 trading days.
- Overnight CFD financing is charged for each night held. Conservative assumptions until broker figures
  are measured: indices 0.02% of notional per night, crypto 0.06%, gold/FX 0.015%. Weekends count as 3 nights.
- R = net PnL / planned risk, where planned risk = |mid price at entry − SL|.

## 4. Metrics (per method, per instrument and pooled)
- Signals per year, hit rate, net average R, t-statistic, profit factor.
- Daily Sharpe at fixed 0.5% risk per trade, max drawdown.
- Calibration: Brier score and Brier skill versus the **geometric baseline**
  p₀ = SL/(SL+TP), plus reliability per year and per volatility tercile.
- Random-direction benchmark percentile (same entries and SL/TP policy, 200 seeds).
- Stability: share of positive years in development; per-instrument breakdown.
- Deflated Sharpe ratio using the trial ledger count, and the probability of backtest overfitting
  (PBO) from CPCV.

## 5. Grades (applied to the Test period)
- ✅ **Confirmed:** all of the following:
  - n_test ≥ 200;
  - net average R > 0 with t ≥ 3;
  - significant after Benjamini–Hochberg false-discovery control across all graded methods (q = 0.10);
  - Brier skill > 0;
  - positive in ≥ 60% of development years;
  - still positive at 1.5× spread.
- 🧪 **Experimental:** net average R > 0 and either
  - t ≥ 2, or
  - n_test < 200 with posterior P(edge > 0) ≥ 0.90 under a skeptical prior centred on 0R.
- ❌ **Dropped:** everything else.

## 6. Trial ledger and search limits
- Every run of any configuration on any period is appended to `reports/trials.csv` with: config hash,
  method, parameters, data range, period, and metrics. Nothing is deleted from it.
- At most 20 configurations per method in development. Test is evaluated only after the configuration
  is frozen.
- Method definitions (trigger rules, natural levels) are written in their module docstring
  **before** their first test evaluation.

## Recorded deviations

- 2026-11-11: label kernel charges XAUUSD the index financing rate (0.02%/night) instead of the gold/FX 0.015%/night stated above. This overstates cost by 0.005%/night (conservative); labels are not regenerated for it.
