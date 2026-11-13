# phase2_f3_order_flow_BTCUSDT — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 108 (paths and mtimes in JSON).

| Scope | n | Signals/year | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Brier skill | Positive DEV years | DSR | PBO | Random pct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pooled | 7 | 2.3328 | 0.4286 | -0.2180 | -0.7490 | 0.5418 | -0.7125 | -0.0130 | 0.1206 | 0.0000 | NA | 0.4000 | 50.0000 |
| BTCUSDT | 7 | 2.3328 | 0.4286 | -0.2180 | -0.7490 | 0.5418 | -0.7125 | -0.0130 | 0.1206 | 0.0000 | NA | NA | NA |

## Row accounting

Events: 210138; candidate rows: 5253450; assembled: 5253450; OOF predicted: 5253450; selected: 7; signals/year: 2.3328.

Drops: {}; no OOF prediction: 0 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.2180 (n=7); unselected candidate realized R: -0.0728 (n=5253443); unselected at selected events: -0.2322 (n=168). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 50.0000 (matched signals 7, 200 seeds). PBO: 0.4000. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses like-for-like CPCV train/test ranks across logged development configurations; null until at least two comparable configurations exist.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
