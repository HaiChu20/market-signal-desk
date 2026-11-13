# phase2_f4_regime_BTCUSDT — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 108 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 2 | 0.6665 | 0.0000 | -0.8365 | -14.5377 | 0.0000 | -1.3231 | -0.0083 | 0.1194 | 0.0000 | 0.0025 | 0.4000 | NA |
| BTCUSDT | 2 | 0.6665 | 0.0000 | -0.8365 | -14.5377 | 0.0000 | -1.3231 | -0.0083 | 0.1194 | 0.0000 | 0.0025 | NA | NA |

## Row accounting

Events: 210138; candidate rows: 5253450; assembled: 5253450; OOF predicted: 5253450; selected: 2; signals/year: 0.6665.

Drops: {}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.8365 (n=2); unselected candidate realized R: -0.0728 (n=5253448); unselected at selected events: -0.3123 (n=48). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: 0.4000. DSR: 0.0025.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
