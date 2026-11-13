# phase2_f4_regime_USATECHIDXUSD — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 96 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 15 | 3.7554 | 0.8000 | 0.1562 | 1.6330 | 2.8729 | 2.8711 | 0.0000 | 0.1021 | 1.0000 | NA | 0.0000 | 98.5000 |
| USATECHIDXUSD | 15 | 3.7554 | 0.8000 | 0.1562 | 1.6330 | 2.8729 | 2.8711 | 0.0000 | 0.1021 | 1.0000 | NA | NA | NA |

## Row accounting

Events: 182462; candidate rows: 4561550; assembled: 4561550; OOF predicted: 4561550; selected: 15; signals/year: 3.7554.

Drops: {}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: 0.1562 (n=15); unselected candidate realized R: -0.0546 (n=4561535); unselected at selected events: 0.3135 (n=360). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 98.5000 (matched signals 15, 200 seeds). PBO: 0.0000. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
