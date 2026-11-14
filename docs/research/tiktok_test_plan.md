# TikTok strategies A and B: test plan (frozen 2026-11-14, before any result)

Supplements `docs/research/tiktok_strategy_specs.md` (the spec). Where the spec is silent, this file decides.
Nothing below may be changed after results are seen. A genuine bug found later is fixed and reported as such.

## 1. Markets (three tiers, all local 1-minute data, no new downloads)

| Tier | Markets | Source | Session used for "open"/"RTH" |
|---|---|---|---|
| 1. Own market | USATECHIDXUSD (Nasdaq 100) | Dukascopy bid/ask via `msd.data.load` | 09:30–16:00 America/New_York |
| 2. Similar (other indices) | USA500IDXUSD (S&P 500), USA30IDXUSD (Dow) | Dukascopy bid/ask | 09:30–16:00 America/New_York |
| | DEUIDXEUR (DAX) | Dukascopy bid/ask | 09:00–17:30 Europe/Berlin |
| | GBRIDXGBP (FTSE 100) | Dukascopy bid/ask | 08:00–16:30 Europe/London |
| | JPNIDXJPY (Nikkei 225) | Dukascopy bid/ask | 09:00–15:00 Asia/Tokyo |
| 3. Different | XAUUSD, XAGUSD (gold, silver), LIGHTCMDUSD, BRENTCMDUSD (WTI, Brent), EURUSD, GBPUSD, USDJPY | Dukascopy bid/ask | 09:30–16:00 America/New_York (the NY cash open, same clock as the original) |
| | BTCUSDT, ETHUSDT | Binance spot 1-minute trade prices | 09:30–16:00 America/New_York |

- Strategy A's "full day" variant uses each market's 24-hour day ending 17:00 America/New_York for Tier 1, Tier 3 and US indices,
  and the local calendar day for DAX, FTSE, Nikkei.
- Days without a complete session (holidays, half days, data gaps > 5 minutes inside the session) are skipped and counted.

## 2. Costs

- Dukascopy: real bid/ask; buy at ask, sell at bid. The 1.5× cost row widens each fill's half-spread by 1.5.
  Assert that spreads are present and positive; never silently fall back to mid.
- Binance BTC/ETH (trade prices only): 0.05% per side (fee + slippage) on entry and exit; 1.5× row = 0.075% per side.
- Results are in R (1R = initial stop distance in price); fixed 1R risk, no compounding.

## 3. Periods

- Dev 2019-01-01 → 2022-12-31; Holdout 2023-01-01 → end of local data. Indicator warm-up may use 2018 data.
- Trades are assigned to the period of their entry. A trade still open at the end of the data is dropped and counted.

## 4. Selection (Nasdaq dev only) and freezing

- For each strategy, every cell of the spec's grid is run on **USATECHIDXUSD dev** (A: k × session × stop × direction = 24
  cells; B: fast EMA × slow EMA × stop ATR = 27 cells, each in the default variant — close-exit, one position at a time,
  no time stop; the touch-exit, one-new-per-day and 10-day-stop variants are reported only for the chosen cell).
- **Chosen cell** = the highest dev net avg R on Nasdaq. The spec's defaults are also always reported.
- The chosen cell (and the defaults) are then frozen and applied **unchanged** to every other market (dev and holdout).
  No per-market tuning. Each market's full grid is also reported, for the "stable region or lone spike" view only.

## 5. Verdicts (per strategy)

- **Nasdaq verdict** = the spec's decision rule on the chosen cell: dev net > 0 and 1.5× cost ≥ 0, ≥ 3 of 4 dev years
  positive, above the 95th percentile of the random-entry benchmark (1,000 sims, same entry times, random direction,
  same exits), neighbouring grid cells (differ by one grid step in one parameter) mostly positive, holdout net > 0.
  Otherwise **no edge**.
- **Generalisation** (reported, not a separate tuning step): for the frozen chosen cell, net avg R, t-stat, 1.5× cost,
  and random percentile per market, per tier pooled (equal weight per market), dev and holdout separately.
- Random benchmark: 1,000 seeds for the chosen and default cells in every market; not for every grid cell.

## 6. Running

- The holdout is run **once**, by the supervisor, after the Nasdaq dev selection is written to disk. Code must refuse
  to compute any holdout number unless called with an explicit once-only flag and a recorded dev selection.
- One row per strategy in reports/trials.csv. Reports in reports/research/tiktok/.

## 7. Prior

A similar session-open momentum rule already tested negative here (intraday_momentum, wide_v1). Strategy A's own
video shows the edge fading since 2024. Expect "no edge" unless the evidence is clear.

## Amendment 2026-11-14 (dev bug, before any holdout number)

The first Strategy A dev run produced 0 complete `full_day` sessions for all index CFDs and Brent, because the
5-minute gap rule treated each market's normal daily trading break (e.g. Nasdaq CFD has no bars 16:15–18:00 ET) as
missing data. Fix: a `full_day` session is the bars present inside its 24-hour window; it is complete when that day's
RTH session is complete (same rule as `rth`) and the first bar is within 3 hours of the window start. "Today's open" is
the first bar in the window, the exit is the last bar's close, and the prior range is the previous complete window's
high − low. The gap rule still applies to `rth`. The Nasdaq dev grid and selection are rerun after the fix.
