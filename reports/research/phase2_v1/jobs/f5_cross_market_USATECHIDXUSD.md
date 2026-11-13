# f5_cross_market — USATECHIDXUSD DEV

Development only. Test and Final were neither loaded nor evaluated.

Training anchors are subsampled to hourly (:00), capped at 25,000 anchors per fold, for the 10 GiB memory cap; OOF evaluation uses every 15-minute anchor.

| n | trades/year | hit | net avg R | t | PF | Brier skill vs p0 | Brier skill vs cell base | random pct | beat base + positive net |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 9 | 2.2532 | 0.4444 | -0.3650 | -1.4186 | 0.3530 | 0.0995 | -0.0028 | 0.5000 | no |
