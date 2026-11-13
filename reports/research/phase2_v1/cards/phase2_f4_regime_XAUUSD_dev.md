# phase2_f4_regime_XAUUSD — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 362 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 35 | 2.3344 | 0.6286 | -0.1557 | -1.3861 | 0.5706 | -14.4707 | -0.0271 | 0.1260 | 0.0000 | NA | 0.0000 | 13.0000 |
| XAUUSD | 35 | 2.3344 | 0.6286 | -0.1557 | -1.3861 | 0.5706 | -14.4707 | -0.0271 | 0.1260 | 0.0000 | NA | NA | NA |

## Row accounting

Events: 716930; candidate rows: 17923250; assembled: 17923250; OOF predicted: 17923250; selected: 35; signals/year: 2.3344.

Drops: {}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.1557 (n=35); unselected candidate realized R: -0.0793 (n=17923215); unselected at selected events: -0.2736 (n=840). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 13.0000 (matched signals 35, 200 seeds). PBO: 0.0000. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
