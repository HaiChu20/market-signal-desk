# vix_spike_dip_buy — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 46 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 3 | 0.7932 | 0.0000 | -0.7021 | -2.1961 | 0.0000 | -1.9010 | -0.0105 | -0.0981 | 0.0000 | NA | NA | 47.5000 |
| USA500IDXUSD | 1 | 0.2644 | 0.0000 | -0.0627 | NA | 0.0000 | NA | -0.0003 | -0.0726 | 0.0000 | NA | NA | NA |
| USATECHIDXUSD | 2 | 0.6255 | 0.0000 | -1.0219 | -1739.2575 | 0.0000 | -3.4245 | -0.0102 | -0.1258 | 0.0000 | NA | NA | NA |

## Row accounting

Events: 124; candidate rows: 4588; assembled: 4588; OOF predicted: 4588; selected: 3; signals/year: 0.7932.

Drops: {"invalid_geometry": 0, "missing_outcome": 0}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.7021 (n=3); unselected candidate realized R: -0.3721 (n=4585); unselected at selected events: -0.3962 (n=108). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 47.5000 (matched signals 3, 200 seeds). PBO: NA. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
