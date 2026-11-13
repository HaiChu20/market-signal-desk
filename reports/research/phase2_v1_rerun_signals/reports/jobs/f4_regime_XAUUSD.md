# f4_regime — XAUUSD DEV

Development only. Test and Final were neither loaded nor evaluated.

Training anchors are subsampled to hourly (:00), capped at 25,000 anchors per fold, for the 10 GiB memory cap; OOF evaluation uses every 15-minute anchor.

| n | trades/year | hit | net avg R | t | PF | Brier skill vs p0 | Brier skill vs cell base | random pct | beat base + positive net |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 35 | 2.3344 | 0.6286 | -0.1557 | -1.3861 | 0.5706 | 0.1260 | 0.0021 | NA | no |
