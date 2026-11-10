# rsi2_mean_reversion — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 16 (paths and mtimes in JSON).

| Scope | n | Brier skill vs p0 | Net avg R | t | Grade |
|---|---:|---:|---:|---:|---|
| pooled | 4 | -0.1861 | -0.6222 | -2.3879 | ungraded |
| USATECHIDXUSD | 4 | -0.1861 | -0.6222 | -2.3879 | ungraded |

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- Random-direction percentile needs opposite-direction execution at identical entries and is unavailable from event labels.
- PBO needs comparable strategy configurations across CPCV paths; unavailable when only one fixed configuration is run.
- Deflated Sharpe requires observed trial Sharpe dispersion; omitted if not available.
