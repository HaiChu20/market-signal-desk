# dow_trend_confirmation — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 361 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.1523 | NA | NA | NA | NA |
| XAUUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.0607 | NA | NA | NA | NA |
| BTCUSDT | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.5687 | NA | NA | NA | NA |
| USATECHIDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | -0.1274 | NA | NA | NA | NA |
| USA500IDXUSD | 0 | 0.0000 | NA | NA | NA | NA | NA | NA | 0.0511 | NA | NA | NA | NA |

## Row accounting

Events: 218; candidate rows: 8049; assembled: 8049; OOF predicted: 8049; selected: 0; signals/year: 0.0000.

Drops: {"invalid_geometry": 0, "missing_outcome": 0}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: NA (n=0); unselected candidate realized R: -8.2864 (n=8049); unselected at selected events: NA (n=0). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: NA. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
