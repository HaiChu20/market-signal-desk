# Protocol Test exam v1 preregistration

This document freezes the one-time Test-period examination before any Test data are read. The Test period is **2023-01-01 through 2024-12-31**. The 2025+ Final period remains locked.

## Fixed candidates and geometry

- `funding_extreme_fade`, `BTCUSDT`: stop loss `1.5 × 1h ATR14`; take profit `2R`.
- `donchian_atr_breakout`, pooled over `USATECHIDXUSD`, `USA500IDXUSD`, `XAUUSD`, and `BTCUSDT`: stop loss `3 × 1h ATR14`; take profit `3R`.

There is one fixed configuration per rule. No parameter, threshold, detector, market, geometry, or selection rule may be changed after Test results are observed.

## Fixed execution and evaluation settings

- Use the same frozen detector implementations and causal checkpoint state. State warm-up may use observations before 2023-01-01, but no decision before that instant is part of the exam.
- Maximum hold is one trading day. An unresolved position exits at the executable time-exit price.
- `USATECHIDXUSD`, `USA500IDXUSD`, and `XAUUSD` use the existing CFD modeled spread and financing convention.
- `BTCUSDT` uses the Binance USDT-M perpetual convention: the existing causal Binance spread/slippage model, 0.05% taker fee per side, and actual crossed funding rates with side-aware sign.
- Apply the shared deterministic one-position-per-symbol gate.
- Drop every trade whose realized exit/label end is on or after `2025-01-01T00:00:00Z`. Do not censor or replace its outcome.
- Decision inputs and labels must be read strictly before `2025-01-01T00:00:00Z`; the runner must assert this boundary.

## Pre-declared decision rule

Grade each rule once, pooling its stated markets. A rule passes only if all three conditions hold:

1. net average R is greater than zero;
2. profit factor is greater than one; and
3. its same-entry, same-geometry random-direction percentile is at least 75, using exactly 200 deterministic seeds.

Also report trade count, hit rate, net-R t-statistic, daily Sharpe at the established fixed-fractional convention, maximum drawdown, and results by calendar year and market. These diagnostics do not affect the pass/fail decision.

## Frozen provenance

- Frozen detector/code commit: `a196fdd982e10aa4f3d4dffc08e59382615ce53a`.
- Canonical wide-grid config: `hpc/roihu/sequence/configs/wide_v1.json`.
- Canonical config SHA-256: `1cab0902ea0845a1ab74ff15333ea412a1f16bd6b3b71031afeb4a2da02681dd`.
- The fixed candidate subset and Test-only dates are defined completely by this committed preregistration; the implementation must reject any mismatch.

If a genuine software or data bug is discovered after Test values are accessed, stop without grading, without appending Test ledger rows, and report the bug. There is no regrade under this protocol.
