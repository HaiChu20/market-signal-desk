# liquidity_sweep — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 316 (paths and mtimes in JSON).

| Scope | n | Brier skill vs p0 | Net avg R | t | Grade |
|---|---:|---:|---:|---:|---|
| pooled | 0 | 0.1035 | NA | NA | ungraded |
| USA500IDXUSD | 0 | 0.0301 | NA | NA | ungraded |
| BTCUSDT | 0 | 0.2835 | NA | NA | ungraded |
| USATECHIDXUSD | 0 | 0.0381 | NA | NA | ungraded |

## Row accounting

Events: 39848; candidate rows: 1219938; assembled: 1219905; OOF predicted: 975924; selected: 0; signals/year: 0.0000.

Drops: {"event_after_dev": 0, "invalid_geometry": 16, "label_extends_beyond_dev": 17, "missing_asof_feature": 0, "missing_outcome": 7}; no OOF prediction: 243981 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: NA (n=0); unselected candidate realized R: -2.6497 (n=975924); unselected at selected events: NA (n=0). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: NA (matched signals 0, 200 seeds). PBO: NA. DSR: NA.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses CSCV over common development years of logged configurations; null here because fewer than four common years have comparable trial scores.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
