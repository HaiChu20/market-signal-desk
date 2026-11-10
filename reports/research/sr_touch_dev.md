# sr_touch — development report card

**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**

Input files: 416 (paths and mtimes in JSON).

| Scope | n | Brier skill vs p0 | Net avg R | t | Grade |
|---|---:|---:|---:|---:|---|
| pooled | 209 | 0.0478 | -0.2321 | -2.3712 | ungraded |
| BTCUSDT | 5 | 0.1071 | -0.1450 | -0.3000 | ungraded |
| USA500IDXUSD | 61 | 0.0238 | -0.1008 | -0.4749 | ungraded |
| USATECHIDXUSD | 143 | 0.0318 | -0.2911 | -2.6487 | ungraded |

## Row accounting

Events: 18675; candidate rows: 590352; assembled: 590348; OOF predicted: 472278; selected: 209; signals/year: 62.8752.

Drops: {"event_after_dev": 0, "invalid_geometry": 0, "label_extends_beyond_dev": 4, "missing_asof_feature": 0, "missing_outcome": 0}; no OOF prediction: 118070 (initial walk-forward training block).

## Candidate ranking

Selected candidate realized R: -0.2321 (n=209); unselected candidate realized R: -2.1854 (n=472069); unselected at selected events: -0.2159 (n=7999). Alternatives at the same event are correlated.

## Selection-bias diagnostics

Random-direction percentile: 19.5000 (matched signals 209, 200 seeds). PBO: NA. DSR: 0.0000.

## Limitations

- Stage 9 inputs may be rebuilt; inspect manifest before reuse.
- PBO uses CSCV over common development years of logged configurations; null here because fewer than four common years have comparable trial scores.
- Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.
- For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.
- DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.
