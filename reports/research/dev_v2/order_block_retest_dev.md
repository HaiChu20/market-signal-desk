# order_block_retest — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 732 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.4407 | NA | NA | NA | NA |
| XAUUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.4037 | NA | NA | NA | NA |
| BTCUSDT | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.7759 | NA | NA | NA | NA |
| USA500IDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.2694 | NA | NA | NA | NA |
| USATECHIDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.3126 | NA | NA | NA | NA |

## Row accounting

Events: 11199; candidate rows: 414008; assembled: 254743; OOF predicted: 254743; selected: 0; signals/year: 0.0000.

Drops: {"invalid_geometry": 0, "missing_outcome": 159265}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: NA (n=0); unselected candidate realized R: -1.6731 (n=254743); unselected at selected events: NA (n=0). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: NA. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
