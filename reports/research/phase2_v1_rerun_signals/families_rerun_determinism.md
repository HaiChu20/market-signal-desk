# Phase 2 family signal determinism rerun

Frozen Family 3–5 configs were rerun solely to recover the previously unpersisted selected OOF signals. No model, threshold, feature, gate, label or seed changed. No trial-ledger row was appended.

Ledger unchanged: yes. All 15 units deterministic: yes.

| Family | Market | OOF rows | Signals | Net R match | Hit match | Brier match | Deterministic |
|---|---|---:|---:|---|---|---|---|
| f3_order_flow | USATECHIDXUSD | 4,561,550 | 0 | yes | yes | yes | yes |
| f3_order_flow | USA500IDXUSD | 4,453,650 | 12 | yes | yes | yes | yes |
| f3_order_flow | XAUUSD | 17,923,250 | 0 | yes | yes | yes | yes |
| f3_order_flow | BTCUSDT | 5,253,450 | 7 | yes | yes | yes | yes |
| f3_order_flow | ETHUSDT | 5,253,450 | 18 | yes | yes | yes | yes |
| f4_regime | USATECHIDXUSD | 4,561,550 | 15 | yes | yes | yes | yes |
| f4_regime | USA500IDXUSD | 4,453,650 | 0 | yes | yes | yes | yes |
| f4_regime | XAUUSD | 17,923,250 | 35 | yes | yes | yes | yes |
| f4_regime | BTCUSDT | 5,253,450 | 2 | yes | yes | yes | yes |
| f4_regime | ETHUSDT | 5,253,450 | 17 | yes | yes | yes | yes |
| f5_cross_market | USATECHIDXUSD | 4,561,550 | 9 | yes | yes | yes | yes |
| f5_cross_market | USA500IDXUSD | 4,453,650 | 0 | yes | yes | yes | yes |
| f5_cross_market | XAUUSD | 17,923,250 | 0 | yes | yes | yes | yes |
| f5_cross_market | BTCUSDT | 5,253,450 | 8 | yes | yes | yes | yes |
| f5_cross_market | ETHUSDT | 5,253,450 | 19 | yes | yes | yes | yes |
