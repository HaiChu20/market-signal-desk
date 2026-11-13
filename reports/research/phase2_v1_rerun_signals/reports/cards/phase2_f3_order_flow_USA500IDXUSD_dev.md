# phase2_f3_order_flow_USA500IDXUSD — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 96 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 12 | 3.0043 | 0.5000 | -0.3029 | -1.3876 | 0.4096 | -1.2815 | -0.0242 | 0.1138 | 0.0000 | 0.0454 | 0.0000 | NA |
| USA500IDXUSD | 12 | 3.0043 | 0.5000 | -0.3029 | -1.3876 | 0.4096 | -1.2815 | -0.0242 | 0.1138 | 0.0000 | 0.0454 | NA | NA |

## Row accounting

Events: 178146; candidate rows: 4453650; assembled: 4453650; OOF predicted: 4453650; selected: 12; signals/year: 3.0043.

Drops: {}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.3029 (n=12); unselected candidate realized R: -0.0499 (n=4453638); unselected at selected events: -0.4291 (n=288). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: 0.0000. DSR: 0.0454.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
