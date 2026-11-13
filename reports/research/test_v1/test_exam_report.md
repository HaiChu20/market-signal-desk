# One-time protocol Test exam v1

> **Post-exam implementation addendum (2026-11-13):** the event-label helper passed microsecond-resolution bar integers to a kernel expecting epoch seconds, while its deadline was in true epoch seconds. Consequently the intended one-trading-day deadline did not fire; unresolved positions could remain open until the end of the loaded look-ahead window. This exam therefore did **not** test the preregistered exit rule. The recorded verdict remains FAIL, the already-seen 2023–2024 Test period is spent and will not be regraded, and the positive index contribution from Donchian remains only a hypothesis for the still-locked Final period. No Test-period input was read to prepare this addendum.

**Test was graded once using the preregistered fixed rules. The 2025+ Final period was not loaded for decisions or labels.**

| Rule | Events | Trades | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Random pct | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| funding_extreme_fade | 98 | 96 | 0.3542 | -0.1633 | -1.2269 | 0.7597 | -0.9029 | -0.0926 | 25.0000 | FAIL |
| donchian_atr_breakout | 690 | 379 | 0.3113 | 0.0206 | 0.2468 | 1.0306 | 0.1683 | -0.1502 | 74.5000 | FAIL |

## funding_extreme_fade

Boundary-crossing trades dropped: 0.

| Scope | n | Hit | Net avg R | t | PF | Sharpe | MDD |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 96 | 0.3542 | -0.1633 | -1.2269 | 0.7597 | -0.9029 | -0.0926 |
| year 2023 | 42 | 0.3333 | -0.1972 | -1.0040 | 0.7025 | -1.0468 | -0.0699 |
| year 2024 | 54 | 0.3704 | -0.1370 | -0.7514 | 0.8022 | -0.7893 | -0.0455 |

## donchian_atr_breakout

Boundary-crossing trades dropped: 0.

| Scope | n | Hit | Net avg R | t | PF | Sharpe | MDD |
|---|---:|---:|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 98 | 0.3265 | 0.2067 | 1.1324 | 1.3041 | 0.7915 | -0.0531 |
| USA500IDXUSD | 111 | 0.2973 | 0.1680 | 0.9616 | 1.2346 | 0.7463 | -0.0469 |
| XAUUSD | 81 | 0.2593 | -0.1307 | -0.7622 | 0.8195 | -0.5491 | -0.0900 |
| BTCUSDT | 89 | 0.3596 | -0.2305 | -2.0006 | 0.5913 | -1.4283 | -0.1332 |
| year 2023 | 177 | 0.3164 | 0.0926 | 0.7232 | 1.1368 | 0.6588 | -0.1020 |
| year 2024 | 202 | 0.3069 | -0.0425 | -0.3886 | 0.9365 | -0.3992 | -0.1344 |
