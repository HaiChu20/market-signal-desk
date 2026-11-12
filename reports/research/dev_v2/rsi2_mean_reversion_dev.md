# rsi2_mean_reversion — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 64 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | -0.1806 | NA | NA | NA | NA |
| USATECHIDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | -0.2373 | NA | NA | NA | NA |
| USA500IDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | -0.0843 | NA | NA | NA | NA |

## Row accounting

Events: 92; candidate rows: 3311; assembled: 3311; OOF predicted: 3311; selected: 0; signals/year: 0.0000.

Drops: {"invalid_geometry": 0, "missing_outcome": 0}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: NA (n=0); unselected candidate realized R: -0.6715 (n=3311); unselected at selected events: NA (n=0). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: NA. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
