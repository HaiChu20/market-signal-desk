# f3_order_flow — USA500IDXUSD DEV

Development only. Test and Final were neither loaded nor evaluated.

Training anchors are subsampled to hourly (:00), capped at 25,000 anchors per fold, for the 10 GiB memory cap; OOF evaluation uses every 15-minute anchor.

| n | trades/year | hit | net avg R | t | PF | Brier skill vs p0 | Brier skill vs cell base | random pct | beat base + positive net |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 12 | 3.0043 | 0.5000 | -0.3029 | -1.3876 | 0.4096 | 0.1138 | -0.0076 | NA | no |
