# liquidity_sweep — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 316 (paths and mtimes in JSON).

| Scope | n | Brier skill vs p0 | Net avg R | t | Grade |
|---|---:|---:|---:|---:|---|
| pooled | 37 | 0.0962 | -0.5606 | -2.8149 | ungraded |
| USA500IDXUSD | 20 | 0.0268 | -0.4755 | -1.4414 | ungraded |
| USATECHIDXUSD | 17 | 0.0349 | -0.6607 | -3.2614 | ungraded |
| BTCUSDT | 0 | NA | NA | NA | ungraded |

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- Random-direction percentile needs opposite-direction execution at identical entries and is unavailable from event labels.
- PBO needs comparable strategy configurations across CPCV paths; unavailable when only one fixed configuration is run.
- Deflated Sharpe requires observed trial Sharpe dispersion; omitted if not available.
