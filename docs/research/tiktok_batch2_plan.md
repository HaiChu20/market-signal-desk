# TikTok batch 2 (ICT/FVG A–D, ATR stop E): test plan (frozen 2026-11-15, before any result)

Supplements `docs/research/tiktok_strategy_specs_batch2.md` (the spec). Where the spec is silent or self-contradictory,
this file decides. User decisions of 2026-11-15 are marked **[user]**. Nothing below may change after results are seen;
a genuine bug found later is fixed and reported as such in the Amendments section.

## 1. Data and periods

- Local Dukascopy 1-minute bid/ask: `USATECHIDXUSD` (NQ), `USA500IDXUSD` (ES, cross-market only), `XAUUSD` (E only).
  No new downloads are needed. Dukascopy NQ/ES quotes have zero spreads in 2012–2013 and partial-day coverage in
  2015–2017, so the long history is not used.
- **Dev 2019-01-01 → 2022-12-31; warm-up 2018 only for indicators. Holdout 2023-01-01 → end of local data [user].**
  The holdout is computed **once, by the supervisor**, after dev selections are written to disk. Code refuses holdout
  numbers unless called with an explicit flag and an existing dev selection file (same guard as batch 1).
- Price path = mid = (bid + ask) / 2. Times in America/New_York with DST. Higher timeframes (5m, 15m, 1h, daily) are
  built only from completed 1-minute bars (`tiktok.common.resample_closed_bars`). "N bars" counts bars present.
- RTH days: skip NYSE holidays and half days (`msd.live.strategies.us_calendar.skip_day`) and days whose 09:30–16:00
  has a gap > 5 minutes (counted and reported). PDH/PDL = previous complete RTH day's high/low (variant: Globex day).
- Asia session high/low = 18:00–00:00 ET, London = 02:00–05:00 ET, both on the current trading day.

## 2. Execution and cost models

One engine; a cost model supplies bid/ask OHLC arrays plus slippage and commission. Prices in points.

| Model | Bid/ask used for fills | Market/stop slippage | Commission RT | Role |
|---|---|---|---|---|
| **futures (primary) [user]** | mid ± 0.5 tick (1-tick spread) | 1 tick | NQ 0.5, ES 0.2 pt | Pass/fail model |
| dukascopy | real Dukascopy bid/ask | 1 tick | NQ 0.5, ES 0.2 pt | Reported |
| capital | mid ± ½ × fixed spread (NQ 1.8, ES 0.5 pt) | 1 tick | none | Reported |

Tick: NQ 0.25, ES 0.25, XAU 0.10. ES commission 0.2 pt = $10 / $50 per point.
Cost multipliers ×1.5 and ×2 scale spread, slippage and commission together.

- **Market entry** (next bar open): buy at ask_o + slip, sell at bid_o − slip.
- **Limit entry** at P: buy fills when ask_l ≤ P − 1 tick (**trade-through**, primary); touch variant ask_l ≤ P.
  Fill price = P (no slippage).
- **Entry "at the close"** (strategy B): market order at the next bar's open (the close is not tradeable after it is known).
- **Stop-loss** at S (long): triggers when bid_l ≤ S; fill = min(S, bid_o) − slip. Mirror for shorts.
- **Take-profit** limit at T (long): fills when bid_h ≥ T + 1 tick (touch variant ≥ T); fill = T.
- **Same bar touches SL and TP → loss.**
  - On a limit-fill bar only the SL is checked.
  - On a market-entry bar both are checked.
- **Time exit / force-flat** (16:00 ET unless the strategy says otherwise): market at the next bar's open, but no later
  than the first bar at/after the deadline; slippage applies.
- **1R** = planned risk = |planned entry price − SL| (limit price, or mid of the next open for market entries).
  Results: gross R, net R, net R at ×1.5 and ×2, all at fixed 1R, no compounding.
- **Minimum stop:** skip trades with planned risk < max(4 pt NQ / 1 pt ES, 0.25 × ATR(14) of 15m mid bars at entry).
  Count and report the skipped trades. Report median stop in points and median cost per trade in R.

## 3. Shared ICT primitives (spec §1, all causal, computed on 1m mid unless stated)

- Swing high/low with lookback L, **usable only from bar i+L**. Liquidity level = confirmed swing not yet traded
  through, plus PDH/PDL and Asia/London highs/lows.
- Sweep (sell-side): bar low < level − 1 tick, and that bar or one of the next M bars closes above the level.
  The sweep is **known at that close** (no earlier). Sweep extreme = lowest low from the sweep bar to the confirming close.
- Displacement: body ≥ k × ATR(14) of the same timeframe and body/range ≥ 0.6.
- FVG (3 bars i−2, i−1, i), known at the close of bar i; size ≥ f × ATR(14).
  - Invalid once a bar closes beyond its far edge, or after X bars.
- IFVG: a bearish FVG becomes a bullish IFVG at the first bar whose body (min(open, close)) closes above its top. Mirror for bearish.
- Engulfing (bullish): previous bar close < open; current bar close > open, open ≤ prev close, close ≥ prev open.
- DOL near: the nearest qualifying opposing liquidity level beyond entry at ≥ 1R. DOL far: the next level beyond
  DOL near, or PDH/PDL if closer. If no level qualifies, the trade is **skipped** (counted).
  Qualifying levels are unswept confirmed swing highs/lows, PDH/PDL, and the Asia/London highs/lows.
- Biases (spec): B0 none; B1 yesterday's RTH close vs open; B2 entry price vs 00:00 ET open; B3 yesterday's close vs
  20-day EMA of RTH daily closes; B4 15m EMA20 vs EMA50 at entry; B∞ sign(16:00 close − 09:30 open), **diagnostic only,
  never eligible for selection**.

## 4. Strategies (defaults from the spec; only these grids)

To limit multiple testing, grids are a full cross of the key parameters plus one-at-a-time (OFAT) steps around the
default for the rest. Every cell counts toward the configuration total.

### A: IFVG (NQ 1m, entries 09:30–11:30, open trades managed to SL/TP or 16:00)

- **Sweep:** the sweep bar is at or after 09:30. The levels it sweeps may be older (overnight).
- **Bearish FVG [user]:** formed up to S bars before the sweep bar or up to S bars after it. It must still be
  valid (not closed through, not expired) until the inversion.
- **Inversion:** within S bars after the later of the sweep and the FVG.
- **Retest:**
  - Within R bars after the inversion, a bar's low ≤ IFVG top and its close ≥ IFVG bottom.
  - A close below the IFVG bottom first cancels the setup.
- **Entry:** market order at the next bar's open.
- **Exits:** SL = sweep extreme − 1 tick (variant: IFVG far edge − 1 tick).
- **Shorts:** mirror of the long rules.
- **Positions:** multiple trades per day are allowed, one position at a time (variant: max 1 per day).
- **Grid:**
  - Full cross: bias {B0, B1, B2, B3, B4} × TP {DOL near, DOL far, 2R, 3R} = 20 cells.
  - OFAT around B0 / DOL near:
    - L {2, 5}
    - S {15, 60}
    - R {15, 60}
    - SL = IFVG edge
    - max 1 per day
  - Defaults: L 3, M 3, S 30, R 30, FVG min 0.1 ATR, expiry 60.
  - Diagnostic: B∞ × 4 TPs.

### B: First candle rule (NQ 1m; ES cross-check)

- **Opening range:** OR = high/low of the 09:30–09:35 bars.
- **Breakout:**
  - A breakout bar j closes above the OR high with body/range ≥ b.
  - Bars j−1, j, j+1 form a bullish FVG (size ≥ 0.1 ATR).
  - Known at the close of j+1.
- **Retrace and entry:**
  - A later bar has low ≤ FVG top.
  - The first bullish engulfing bar whose low ≤ FVG top, before any close below the FVG bottom, triggers entry at
    the next open.
- **SL:** min(low of the engulfing bar, low of the previous bar) − 1 tick (variant: FVG bottom − 1 tick).
- **TP:** R-multiple.
- **Trades:** 1 per day, the first valid setup either side.
- **Deadline:** the entry signal must close by D.
- **Exit:** force-flat 16:00.
- **Grid (full cross):** b {0.5, 0.6, 0.7} × D {10:00, 10:30, 11:00} × TP {2R, 3R} × SL {engulf, FVG} = 36 cells.

**B-alt (30-minute ORB):**

- **Opening range:** OR = 09:30–10:00.
- **Entry:** the first 5m close beyond the OR enters at the next open. First breakout only, max 1 per day.
- **SL:** opposite OR side (variant: OR midpoint).
- **Grid:** TP {1.5R, 2R, 3R} × SL {opposite, mid} = 6 cells.

### C: Silver Bullet, textbook

- **Default:** NQ 1m, window 10–11 ET, bias B1.
- **Sweep target:** a confirmed swing (L = 3) formed before the sweep.
- **Setup:**
  - The sweep happens inside the window.
  - Then an FVG whose middle bar is a displacement candle (k = 1.0) in the bias direction, all three bars inside
    the window.
- **Entry:** limit at the FVG proximal edge, valid until window end.
- **SL:** swept extreme − 1 tick.
- **TP:** the nearest of PDH/PDL and an unswept L=20 swing in the trade direction that is ≥ 10 pts and ≥ 1R from
  entry, else skip.
- **Limits:**
  - 1 trade per window.
  - After a stop-out, no more trades that day.
- **Exit:** hold to 16:00.
- **Grid:**
  - Full cross: bias {B0, B1, B2, B3} × windows {10–11, all three} × entry {proximal, CE} × exit {16:00, window end} = 32 cells.
  - OFAT around the default: L {2, 5}; min target 20; timeframe 5m (5m bars, swings and ATR on 5m).
  - With B0 both directions are allowed.

### D: Silver Bullet, practitioner

**Ablation ladder** (NQ dev):

1. FVG only, all session hours: every FVG, limit at the proximal edge, SL = bar i−2 extreme − 1 tick.
2. Add a mandatory sweep: the FVG forms within N bars after the sweep, in the direction opposite the sweep, and
   the SL is the sweep extreme.
3. Add displacement.
4. Add the windows 03–04, 10–11 and 14–15.
5. Add bias B4.

Plus B∞ as a diagnostic. All rungs use the practitioner defaults below.

**Practitioner defaults:**

- L 3, M 3, displacement off, limit at the proximal edge, N 10, TP 2R.
- Session: all hours except 16:00–18:00 ET, with no entries in that gap.
- One position at a time, time exit 120 min, force-flat at 16:00 ET and before the weekend.
- An unfilled limit order is cancelled when the FVG becomes invalid, after X = 60 bars, or when a new setup replaces it.

**Grid:**

- Full cross: TP {1R, 2R, DOL near} × time exit {60, 120, 240} × entry {proximal, CE} = 18 cells.
- OFAT: L {2, 5}; M {1}; N {5, 20}; displacement on; session RTH only.

**Textbook benchmarks:** C's rules with all three windows and the window-end exit, on 1m and 5m (2 cells, reported).

### E: ATR × √N (stop study, not an entry strategy)

**E1 (XAUUSD and NQ):**

- **Sample:**
  - Every completed 1h mid bar is an entry sample.
  - ATR = ATR(14) on completed 1h bars.
  - N counts hourly bars present.
  - Reported for dev 2019–2022 and, separately, 2023+. These are statistics only: no selection is made, so the
    holdout guard does not apply.
- **Range check** for N ∈ {4, 8, 24, 48, 120}:
  - Median and mean of |close(t+N) − close(t)|.
  - Median and mean of the high − low over the next N bars.
  - ATR × √N alongside both.
  - Split by year and by ATR tercile.
- **Stop-hit, 24-bar hold**, long and short, with k ∈ {1, 2, 3} × ATR, using the 1m path:
  - % hit.
  - % of hits that return to entry within the rest of the 24-bar window.
  - % of hits that return to entry within 24 h after the hit.
- **√N rule:** stop = c × ATR × √N, c ∈ {0.5, 0.75, 1.0, 1.25}, N ∈ {8, 24, 48}: % stopped before N bars.

**E2 [user]:**

- **Strategies:** the swing setups S1 (Breakout 20D) and S2 (Breakout 55D) from `msd.research.swing_stage1` on
  USATECHIDXUSD and XAUUSD. Their entries, cost model and exits are unchanged; only the stop and target change.
- **New stop:** c × ATR(14, completed 1h bars at the signal) × √N.
- **Grid:** c {0.75, 1.0}, N {24, 48, 120} trading hours, TP {1R, 2R, 3R}, against the original 2×ATR stop.
- **Selection:**
  - Dev 2019–2022 selection = the highest net avg R per setup, pooled over the two markets.
  - The holdout is run once by the supervisor.

## 5. Selection, benchmarks, audits (A–D)

- **Chosen cell per strategy** = the highest NQ dev net avg R (futures model) among eligible cells with ≥ 100 dev
  trades. The spec defaults are always reported too.
- **Random-direction benchmark:**
  - 1,000 sims at the same entry timestamps, for the chosen and default cells.
  - Each replay starts from the trade's real fill price and bar. The opposite side uses the same entry price, the
    same stop and target distances in points, and the same time rules.
  - Code asserts that a same-side replay reproduces every actual trade exactly. Batch 1's factory had a look-ahead;
    this check prevents a repeat.
- **Lookahead audit** (chosen cell): every signal is delayed by one bar (orders placed one bar later). Report the change.
- **DSR** (Bailey & López de Prado) on the chosen cell's daily-R Sharpe:
  - N = total batch-2 configurations tried, A–E combined.
  - Daily R = the sum of R per NY trading day; no-trade days count as 0; annualise with √252.
- **ES cross-check:** the frozen NQ chosen cells run on ES with no change (ES tick, commission and minimum stop).
- **Grid heat-maps:** CSV/markdown tables of the full crosses. Neighbours = cells one grid step away in one parameter.

## 6. Decision rule (spec, applied to the chosen cell under the futures model)

A cell is kept only if all of the following hold. Otherwise the verdict is **no edge**.

- Dev net avg R > 0, still ≥ 0 at ×1.5 costs, and still ≥ 0 with trade-through fills (this is the primary fill rule).
- ≥ 3 of the 4 dev years positive, and ES dev net > 0.
- Above the 95th percentile of the random benchmark.
- DSR > 0.95.
- A majority of neighbouring cells positive.
- Still positive in the lookahead audit.
- Holdout net avg R > 0.

## 7. Running and records

- Code: `src/msd/research/tiktok_b2/`. Reports: `reports/research/tiktok_b2/`. One row per strategy in
  `reports/trials.csv` (append-only) after the holdout.
- Workers run dev only. The holdout is run once, by the supervisor.
- Runs must be foreground and parallelised over cells with multiprocessing (≤ 12 processes); no detached jobs.

## Amendments

(none yet)
