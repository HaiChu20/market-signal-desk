# sr_touch — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 733 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 6 | 0.4002 | 0.3333 | 0.2257 | 0.4621 | 1.7367 | 0.6182 | -0.0052 | 0.1776 | 1.0000 | 0.1468 | NA | 82.5000 |
| USA500IDXUSD | 5 | 1.2520 | 0.4000 | 0.2741 | 0.4605 | 1.7522 | 0.6243 | -0.0052 | 0.0259 | 1.0000 | 0.1479 | NA | NA |
| XAUUSD | 1 | 0.0667 | 0.0000 | -0.0163 | NA | 0.0000 | NA | -0.0001 | 0.0498 | 0.0000 | NA | NA | NA |
| BTCUSDT | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.5307 | NA | NA | NA | NA |
| USATECHIDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.0385 | NA | NA | NA | NA |

## Row accounting

Events: 115416; candidate rows: 4339051; assembled: 4339051; OOF predicted: 4339051; selected: 6; signals/year: 0.4002.

Drops: {"invalid_geometry": 0, "missing_outcome": 0}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: 0.2257 (n=6); unselected candidate realized R: -1531.1790 (n=4339045); unselected at selected events: -0.1334 (n=210). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 82.5000 (matched signals 6, 200 seeds). PBO: NA. DSR: 0.1468.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
