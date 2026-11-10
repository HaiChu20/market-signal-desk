# sr_touch — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 316 (paths and mtimes in JSON).

| Scope | n | Brier skill vs p0 | Net avg R | t | Grade |
|---|---:|---:|---:|---:|---|
| pooled | 831 | 0.0491 | -0.0835 | -1.2412 | ungraded |
| BTCUSDT | 70 | 0.1110 | -0.1219 | -0.7750 | ungraded |
| USA500IDXUSD | 250 | 0.0240 | 0.0014 | 0.0123 | ungraded |
| USATECHIDXUSD | 511 | 0.0324 | -0.1198 | -1.3155 | ungraded |

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- Random-direction percentile needs opposite-direction execution at identical entries and is unavailable from event labels.
- PBO needs comparable strategy configurations across CPCV paths; unavailable when only one fixed configuration is run.
- Deflated Sharpe requires observed trial Sharpe dispersion; omitted if not available.
