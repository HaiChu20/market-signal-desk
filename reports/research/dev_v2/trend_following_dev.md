# trend_following — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 713 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 11 | 0.7482 | 0.2727 | 0.1349 | 0.2735 | 1.2359 | 0.8007 | -0.0104 | 0.1943 | 1.0000 | NA | NA | 62.0000 |
| USA500IDXUSD | 9 | 2.5624 | 0.2222 | -0.0607 | -0.1269 | 0.8961 | 0.4555 | -0.0155 | 0.0020 | 0.0000 | NA | NA | NA |
| XAUUSD | 2 | 0.1361 | 0.5000 | 1.0150 | 0.4957 | 2.9660 | 1.3617 | -0.0052 | 0.1200 | 1.0000 | NA | NA | NA |
| BTCUSDT | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.5572 | NA | NA | NA | NA |
| USATECHIDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.0154 | NA | NA | NA | NA |

## Row accounting

Events: 5342; candidate rows: 197262; assembled: 197262; OOF predicted: 197262; selected: 11; signals/year: 0.7482.

Drops: {"invalid_geometry": 0, "missing_outcome": 0}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: 0.1349 (n=11); unselected candidate realized R: -1319.4802 (n=197251); unselected at selected events: 0.0759 (n=396). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 62.0000 (matched signals 11, 200 seeds). PBO: NA. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
