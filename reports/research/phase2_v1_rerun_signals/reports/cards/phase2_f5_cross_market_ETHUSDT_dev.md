# phase2_f5_cross_market_ETHUSDT — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 108 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 19 | 6.3319 | 0.3684 | -0.3030 | -1.6643 | 0.4579 | -0.9721 | -0.0402 | 0.1055 | 0.3333 | 0.0379 | 0.3000 | NA |
| ETHUSDT | 19 | 6.3319 | 0.3684 | -0.3030 | -1.6643 | 0.4579 | -0.9721 | -0.0402 | 0.1055 | 0.3333 | 0.0379 | NA | NA |

## Row accounting

Events: 210138; candidate rows: 5253450; assembled: 5253450; OOF predicted: 5253450; selected: 19; signals/year: 6.3319.

Drops: {}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.3030 (n=19); unselected candidate realized R: -0.0494 (n=5253431); unselected at selected events: -0.2654 (n=456). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: 0.3000. DSR: 0.0379.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
