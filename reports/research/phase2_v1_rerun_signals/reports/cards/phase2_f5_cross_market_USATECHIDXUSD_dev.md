# phase2_f5_cross_market_USATECHIDXUSD — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 96 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 9 | 2.2532 | 0.4444 | -0.3650 | -1.4186 | 0.3530 | -2.1605 | -0.0210 | 0.0995 | 0.0000 | 0.0150 | 0.0000 | NA |
| USATECHIDXUSD | 9 | 2.2532 | 0.4444 | -0.3650 | -1.4186 | 0.3530 | -2.1605 | -0.0210 | 0.0995 | 0.0000 | 0.0150 | NA | NA |

## Row accounting

Events: 182462; candidate rows: 4561550; assembled: 4561550; OOF predicted: 4561550; selected: 9; signals/year: 2.2532.

Drops: {}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.3650 (n=9); unselected candidate realized R: -0.0546 (n=4561541); unselected at selected events: -0.5533 (n=216). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: 0.0000. DSR: 0.0150.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
