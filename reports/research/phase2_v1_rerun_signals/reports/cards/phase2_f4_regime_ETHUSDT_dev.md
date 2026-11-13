# phase2_f4_regime_ETHUSDT — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 108 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 17 | 5.6654 | 0.2941 | -0.3746 | -1.8731 | 0.3977 | -1.0666 | -0.0401 | 0.1136 | 0.3333 | 0.0283 | 0.3000 | NA |
| ETHUSDT | 17 | 5.6654 | 0.2941 | -0.3746 | -1.8731 | 0.3977 | -1.0666 | -0.0401 | 0.1136 | 0.3333 | 0.0283 | NA | NA |

## Row accounting

Events: 210138; candidate rows: 5253450; assembled: 5253450; OOF predicted: 5253450; selected: 17; signals/year: 5.6654.

Drops: {}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.3746 (n=17); unselected candidate realized R: -0.0494 (n=5253433); unselected at selected events: -0.3044 (n=408). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: 0.3000. DSR: 0.0283.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
