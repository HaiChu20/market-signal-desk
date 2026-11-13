# DEV experiments v2 preregistration

This document freezes three development-only experiments before any result from them is calculated. All decisions, labels, training folds, and realized exits are strictly before `2023-01-01T00:00:00Z`. Test (2023–2024) is already seen and is not loaded or used here. Final (2025+) remains locked. The frozen event replay is unchanged; only the outcomes or portfolio construction described below are evaluated.

Common provenance:

- preregistration parent code commit: `e880346605fb0d5745f51e61fd110c8bca87d44d`;
- frozen detector/event replay manifest combined SHA-256: `e18389ba59e47ba85758462afae6444d33d91d8f4795561ff879023fa2b2bef2`;
- canonical wide-v1 geometry config SHA-256: `1cab0902ea0845a1ab74ff15333ea412a1f16bd6b3b71031afeb4a2da02681dd`;
- CPCV uses five chronological groups with two held-out groups, with the existing label-window purge and one-trading-day embargo;
- one append-only ledger row is written for every evaluated configuration, `period=dev`, protocol/note `dev_v2_experiments`; ledger rows are appended only after the complete experiment succeeds.

## E1 — longer hold

Evaluate every one of the 34 in-scope Family-1 rule units on its frozen DEV events. Keep the wide-v1 geometry unchanged: SL multiples `{1, 1.5, 2, 3, 4}` of completed 1h ATR14 and TP multiples `{0.5, 1, 1.5, 2, 3}` R, both detector-directed sides. Change only maximum holding time from one to three trading days. Unresolved positions exit at the executable price at the three-day deadline. Extra CFD financing nights and actual crossed Binance-perpetual funding settlements are included through the existing cost kernels. Any label resolving at or after 2023-01-01 is dropped, never censored.

For each CPCV split, choose exactly one SL/TP cell by highest mean net R on the purged train rows, then report the chosen cell on the held-out rows. Resolve overlapping fold votes as in wide-v1 and apply the deterministic one-position-per-symbol gate. Report OOF net average R, t-statistic, profit factor, and time-exit share, plus their deltas versus the accepted wide-v1 one-day report. No Test-informed rule or geometry is introduced.

## E2 — nested rule portfolio

Use the same ten CPCV splits. The selection unit is a rule. Inside each split only:

1. For every rule, compare its train-fold mean net R from wide-v1 with its train-fold mean net R from E1, each using that horizon's train-selected best SL/TP cell.
2. Retain the horizon/cell with the higher train-fold mean. Select the rule only if that winning train-fold mean is strictly positive.
3. Apply that frozen choice to the held-out events. No test-fold performance participates in rule, horizon, geometry, or sizing selection.
4. Within each rule and symbol, apply the deterministic one-position gate. Different rules may hold positions concurrently; the constraint is one position per symbol per rule.

Combine the nested OOF trades in two preregistered portfolio configurations:

- **equal risk:** each accepted trade contributes its realized net R at a constant 0.5% account-risk unit;
- **inverse volatility:** at entry, multiply the 0.5% unit by `median(train trailing-vol observations) / trailing 20-trading-day realized volatility`, using only returns known before entry and the train fold to set the median. Clip the multiplier to `[0.5, 2.0]`. If volatility is unavailable, use multiplier 1.0. This is a capped Moreira–Muir-style volatility scaling, not an optimized parameter.

Deduplicate a held-out event appearing in multiple CPCV test combinations by deterministic majority vote over its train-derived rule/horizon/cell choice; ties sort by `(horizon, SL, TP)`. Report OOF trades/day, mean net R/day (unscaled R for equal risk and scaled R for inverse-vol), annualized daily Sharpe, maximum drawdown at 0.5% base risk, profit factor, and contribution by market.

## E3 — intraday momentum

Markets are fixed to `USATECHIDXUSD` and `USA500IDXUSD`, using their cash-era DEV data only. For each New York trading session:

- signal return is the fractional return from the prior session's executable midpoint at the 16:00 ET close to the current session's midpoint at 10:00 ET (the 09:59 minute close, known at 10:00);
- if the signal sign is nonzero, enter in that direction at the executable 15:30 ET minute open (long at ask, short at bid);
- exit only at the executable 16:00 ET close (the 15:59 minute close: long at bid, short at ask); there is no SL or TP;
- express net P&L in R using the completed 1h ATR14 known at entry; executable CFD bid/ask prices therefore include the round-trip spread cost.

Two fixed variants are evaluated by purged chronological CPCV:

- **all nonzero signals**;
- **large signals**, traded only when absolute signal return is strictly above the median absolute signal return learned on that split's train sessions.

The median is never learned on a held-out fold. Deduplicate repeated CPCV test membership by deterministic majority vote. Report per market and year: trades, net average R per trade, hit rate, and t-statistic, plus pooled metrics. No parameter is tuned from the results.
