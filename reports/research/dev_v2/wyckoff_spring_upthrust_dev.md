# wyckoff_spring_upthrust — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 734 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 2 | 0.1334 | 0.5000 | 0.6524 | 0.3888 | 2.2722 | 2.2734 | -0.0051 | 0.1789 | 1.0000 | NA | NA | 44.5000 |
| USA500IDXUSD | 1 | 0.2507 | 0.0000 | -1.0257 | NA | 0.0000 | NA | -0.0051 | 0.0182 | 0.0000 | NA | NA | NA |
| XAUUSD | 1 | 0.0667 | 1.0000 | 2.3305 | NA | NA | NA | 0.0000 | 0.0595 | 1.0000 | NA | NA | NA |
| BTCUSDT | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.5457 | NA | NA | NA | NA |
| USATECHIDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.0324 | NA | NA | NA | NA |

## Row accounting

Events: 11839; candidate rows: 436115; assembled: 436115; OOF predicted: 436115; selected: 2; signals/year: 0.1334.

Drops: {"invalid_geometry": 0, "missing_outcome": 0}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: 0.6524 (n=2); unselected candidate realized R: -2806.3255 (n=436113); unselected at selected events: -0.0639 (n=72). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 44.5000 (matched signals 2, 200 seeds). PBO: NA. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
