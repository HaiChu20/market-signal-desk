# Backtest spec: two Nasdaq strategies from TikTok (QuantBuilder)

Source videos (rules extracted by Gemini, 2026-11-14):
- A. https://www.tiktok.com/@thequantbuilder/video/7706579238593318177 (Larry Williams volatility breakout)
- B. https://www.tiktok.com/@thequantbuilder/video/7707290068049792289 (first 5-min candle vs MA)

Anything marked **NOT SHOWN** was not specified in the video. Use the stated default and sweep only the listed grid. Do not tune anything else.

---

## Common setup (both strategies)

| Item | Value |
|---|---|
| Instrument | Nasdaq 100 (NQ/MNQ futures or a Nasdaq 100 CFD). In my repo: Dukascopy `USATECHIDXUSD` 1-minute bid/ask bars (UTC), loaded with `msd.data.load("USATECHIDXUSD", start, end, source="dukascopy")` |
| Time zone | America/New_York with DST handled. RTH = 09:30–16:00 ET |
| Costs | Real bid/ask: buy at ask, sell at bid. If only mid prices exist, charge 1 index point round trip for NQ. Also report results with costs × 1.5 |
| Risk unit | Report everything in **R**, where 1R = the initial stop distance. Fix risk at 1R per trade; don't compound for the main stats |
| Periods | **Dev: 2019-01-01 → 2022-12-31** (tune grid here only). **Holdout: 2023-01-01 → latest**, run once with the dev-chosen parameters and never re-tuned |
| No lookahead | Indicators use closed bars only. Higher-timeframe bars must be fully closed before use. Same-bar stop/target ambiguity → assume the stop is hit first |

### Required outputs (per strategy, per parameter set)
1. Trades, win rate, avg win R, avg loss R, **net avg R/trade**, profit factor, t-stat of R, max drawdown in R, longest losing streak
2. Results by year, and long vs short separately
3. **Random-entry benchmark:** 1,000 simulations with the same number of trades per day and the same entry times, random direction, and identical stop/exit rules. Report the strategy's percentile against that distribution
4. Equity curve in R (dev and holdout marked)
5. A table of the full parameter grid (to show whether the result is a lone spike or a stable region)

---

## Strategy A: Larry Williams volatility breakout

**Shown in the video:**
- Data: Nasdaq 100 CFD, 5-minute bars, 2020–2026, with spread and commission
- `range_y = High_yesterday − Low_yesterday`
- **Long:** buy stop at `Open_today + 0.5 × range_y`
- **Short:** sell stop at `Open_today − 0.5 × range_y`
- **Exit:** at the close of the same day
- Risk 1% per trade
- Their results were reported as prop-challenge pass rates, not trade stats: 77.1% vs 44.2% for random entries over 2020–2026. From 2024 it was 64.6%, inside the random band (6–86%), ranking 78 of 100.

**NOT SHOWN → defaults:**
| Item | Default | Sweep grid |
|---|---|---|
| Session for "today's open" and "yesterday's range" | RTH: open = 09:30 ET first print; range = prior RTH high − low | Also: full Globex day (18:00 ET → 17:00 ET) |
| Breakout multiplier `k` | 0.5 | 0.3, 0.5, 0.7 |
| Initial stop | Opposite trigger level (long stop = open − k·range_y) | Also: entry ∓ 0.5 × range_y |
| Both sides trigger same day | Take only the **first** trigger; one trade per day max | — |
| Exit time | RTH close 16:00 ET (15:59 bar close) | — |
| Take profit | None (time exit only) | — |
| Direction | Both | Also report long-only (Williams' original style) |

---

## Strategy B: First 5-minute candle vs fast MA, trail on hourly slow MA

**Shown in the video:**
- Nasdaq 100. Entry is decided on the **5-minute** chart; the trade is managed on the **1-hour** chart
- Only one candle matters: the **09:30–09:35 ET** candle
- **Long** if that candle closes **above** the fast MA (5-min). **Short** if it closes **below**
- Enter at 09:35 (market at the candle close; order type NOT SHOWN, so assume market at the next bar open)
- Initial stop placed "far away" to avoid noise
- Once in profit, the stop **trails the slow MA on the hourly chart**. Exit when price crosses it
- **No fixed take profit; can hold for several days**
- Risk 1% per trade
- Their results: since 2019, 1,792 trades, 56.4% win rate (1,011 W / 781 L), +505.8% total (probably compounded). Max drawdown, profit factor and Sharpe NOT SHOWN.

**NOT SHOWN → defaults:**
| Item | Default | Sweep grid |
|---|---|---|
| Fast MA (5-min) | EMA 20 | EMA 9, 20, 50 |
| Slow MA (1-hour) | EMA 50 | EMA 20, 50, 100 |
| Initial stop | 1.5 × ATR(14) on the 1-hour chart from entry | 1.0, 1.5, 2.5 × ATR(14, 1h) |
| When does trailing start | Once the hourly close is beyond entry by ≥ 1R, OR the hourly slow MA is beyond the entry price in the trade's favour | — |
| Trail rule | Exit when an **hourly candle closes** on the wrong side of the slow MA. The stop never loosens | Also: exit on a touch instead of a close |
| Overlapping signals | **One position at a time**: skip a new day's signal if a trade is open | Also report "allow one new position per day" |
| Max hold | None | Also report a 10 trading-day time stop |
| Overnight/weekend | Hold (futures). Gaps fill at the first available price | — |

Note: 1,792 trades over about 7 years is roughly one trade per trading day, which suggests they open a new trade every day, even while earlier trades are still open. Test both overlap modes and report which one matches their trade count.

---

## Decision rule (state before running)
A parameter set is worth pursuing only if **all** of these hold:
- Dev net avg R > 0 after costs, with costs × 1.5 still ≥ 0
- At least 3 of 4 dev years positive
- Above the 95th percentile of the random-entry benchmark
- Neighbouring grid cells are also positive (no lone spike)
- Holdout net avg R > 0 with the parameters frozen beforehand

Otherwise report it as **no edge** and don't keep tweaking.

### Prior evidence (from my own research)
A similar session-open momentum rule on USATECHIDXUSD/USA500IDXUSD tested **negative** (net ≈ −0.03 to −0.07 R/trade, t ≈ −2 to −4, dev 2019–2022). Strategy A's video also shows its edge fading since 2024. Treat both as unlikely and require the full checklist above.
