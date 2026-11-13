# f3_order_flow — ETHUSDT DEV

Development only. Test and Final were neither loaded nor evaluated.

Training anchors are subsampled to hourly (:00), capped at 25,000 anchors per fold, for the 10 GiB memory cap; OOF evaluation uses every 15-minute anchor.

| n | trades/year | hit | net avg R | t | PF | Brier skill vs p0 | Brier skill vs cell base | random pct | beat base + positive net |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 18 | 5.9987 | 0.3333 | -0.2190 | -0.8895 | 0.6286 | 0.1117 | -0.0041 | NA | no |
