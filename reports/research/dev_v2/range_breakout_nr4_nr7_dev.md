# range_breakout_nr4_nr7 — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 728 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 1 | 0.0669 | 0.0000 | -0.0548 | NA | 0.0000 | NA | -0.0003 | 0.1952 | 0.0000 | NA | NA | 0.0000 |
| XAUUSD | 1 | 0.0669 | 0.0000 | -0.0548 | NA | 0.0000 | NA | -0.0003 | 0.0413 | 0.0000 | NA | NA | NA |
| BTCUSDT | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.5531 | NA | NA | NA | NA |
| USATECHIDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.0439 | NA | NA | NA | NA |
| USA500IDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | -0.0108 | NA | NA | NA | NA |

## Row accounting

Events: 2533; candidate rows: 93533; assembled: 93533; OOF predicted: 93533; selected: 1; signals/year: 0.0669.

Drops: {"invalid_geometry": 0, "missing_outcome": 0}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.0548 (n=1); unselected candidate realized R: -96332.4478 (n=93532); unselected at selected events: -0.1402 (n=36). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 0.0000 (matched signals 1, 200 seeds). PBO: NA. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
