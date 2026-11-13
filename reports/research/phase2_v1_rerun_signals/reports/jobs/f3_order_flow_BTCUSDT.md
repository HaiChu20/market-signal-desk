# f3_order_flow — BTCUSDT DEV

Development only. Test and Final were neither loaded nor evaluated.

Training anchors are subsampled to hourly (:00), capped at 25,000 anchors per fold, for the 10 GiB memory cap; OOF evaluation uses every 15-minute anchor.

| n | trades/year | hit | net avg R | t | PF | Brier skill vs p0 | Brier skill vs cell base | random pct | beat base + positive net |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 7 | 2.3328 | 0.4286 | -0.2180 | -0.7490 | 0.5418 | 0.1206 | -0.0011 | NA | no |
