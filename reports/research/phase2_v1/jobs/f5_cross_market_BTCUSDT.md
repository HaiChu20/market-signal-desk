# f5_cross_market — BTCUSDT DEV

Development only. Test and Final were neither loaded nor evaluated.

Training anchors are subsampled to hourly (:00), capped at 25,000 anchors per fold, for the 10 GiB memory cap; OOF evaluation uses every 15-minute anchor.

| n | trades/year | hit | net avg R | t | PF | Brier skill vs p0 | Brier skill vs cell base | random pct | beat base + positive net |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 8 | 2.6661 | 0.6250 | -0.1020 | -0.4287 | 0.6942 | 0.1128 | -0.0100 | 64.0000 | no |
