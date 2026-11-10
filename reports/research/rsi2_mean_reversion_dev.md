# rsi2_mean_reversion — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 20 (paths and mtimes in JSON).

| Scope | n | Brier skill vs p0 | Net avg R | t | Grade |
|---|---:|---:|---:|---:|---|
| pooled | 2 | -0.1322 | -0.5661 | -1.1748 | ungraded |
| USATECHIDXUSD | 2 | -0.1322 | -0.5661 | -1.1748 | ungraded |

## Row accounting

Events: 12; candidate rows: 432; assembled: 432; OOF predicted: 258; selected: 2; signals/year: 2.9944.

Drops: {"event_after_dev": 0, "invalid_geometry": 0, "label_extends_beyond_dev": 0, "missing_asof_feature": 0, "missing_outcome": 0}; no OOF prediction: 174 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.5661 (n=2); unselected candidate realized R: -0.3378 (n=256); unselected at selected events: -0.6994 (n=70). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 24.5000 (matched signals 2, 200 seeds). PBO: NA. DSR: 0.0082.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses CSCV over common development years of logged configurations; null here because fewer than four common years have comparable trial scores.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
