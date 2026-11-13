# f4_regime — USATECHIDXUSD DEV

Development only. Test and Final were neither loaded nor evaluated.

Training anchors are subsampled to hourly (:00), capped at 25,000 anchors per fold, for the 10 GiB memory cap; OOF evaluation uses every 15-minute anchor.

| n | trades/year | hit | net avg R | t | PF | Brier skill vs p0 | Brier skill vs cell base | random pct | beat base + positive net |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 15 | 3.7554 | 0.8000 | 0.1562 | 1.6330 | 2.8729 | 0.1021 | 0.0000 | NA | yes |
