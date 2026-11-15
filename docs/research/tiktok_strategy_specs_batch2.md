# Backtest spec, batch 2: ICT/FVG strategies + ATR stop sizing (TikTok)

Rules were extracted by Gemini from the videos on 2026-11-15. Anything marked **NOT SHOWN** is not specified in the video, so the stated **default** is used and only the listed **grid** is swept. Do not tune anything else.

| ID | Video | What it is |
|---|---|---|
| A | https://www.tiktok.com/@onlyansss/video/7708383094272822535 | IFVG model, NQ 1-min, 09:30–11:30 NY |
| B | https://www.tiktok.com/@luxalgo/video/7706964325134634253 | "First candle rule": 5-min opening range → FVG retest → engulfing, 3R |
| C | https://www.tiktok.com/@hophowall.vtmarkets/video/7702690880527846677 | ICT Silver Bullet, textbook version |
| D | https://www.tiktok.com/@fxtactix/video/7705291184100429077 | ICT Silver Bullet, 25,000-variation study → "practitioner" version + ablation |
| E | https://www.tiktok.com/@huuducgroup/video/7701582148502932756 | ATR × √hold-time stop sizing (gold), a stop-placement study rather than an entry strategy |

---

## 0. Common setup (applies to all)

### Data
- **NQ:** Dukascopy `USATECHIDXUSD` 1-minute bid/ask bars (UTC). `msd.data.load("USATECHIDXUSD", start, end, source="dukascopy")`
- **ES:** Dukascopy `USA500IDXUSD`, used only for cross-market validation (never tuned on)
- **Gold (E):** Dukascopy `XAUUSD`
- Convert to **America/New_York** with DST. RTH = 09:30–16:00 ET. Build higher timeframes (5m, 15m, 1h, daily) only from completed 1-minute bars.
- Daily boundary for "previous day high/low" (PDH/PDL): **RTH day** by default; variant = Globex day (18:00 ET → 17:00 ET).

### Periods
- **Dev:** first available → 2022-12-31. All choices and grid selection happen here.
- **Holdout:** 2023-01-01 → latest. Run **once**, with frozen parameters, after everything else is final.

### Execution and costs (critical for 1-minute strategies)
- Buy at the ask and sell at the bid using the real spread.
- **Market/stop orders:** +1 tick slippage (NQ 0.25 pt, ES 0.25 pt, XAU 0.10).
- **Limit orders:** filled only if price **trades through the limit by ≥ 1 tick**. A touch is not a fill. Also report the optimistic "touch = fill" result separately so the difference is visible.
- **Same bar hits both SL and TP → count it as a LOSS** (video D's rule).
- **Commission:** report net of a round-trip fee equal to 0.5 NQ point (≈ $10/NQ contract RT incl. exchange fees). Also report results at **costs × 1.5 and × 2**.
- **Minimum stop:** skip trades with a stop < 4 NQ points (or < 0.25 × ATR(14) on 15m, whichever is larger). Tiny stops make costs dominate R. Report how many trades this removes.
- **Stop-distance distribution:** report median stop distance in points and **median cost per trade in R**.
- Force-flat at 16:00 ET for every intraday strategy unless its section says otherwise.

### Results unit
Everything is in **R** (1R = initial stop distance), at fixed 1R risk per trade with no compounding.

### Required outputs (every strategy × every grid cell)
1. Trades, trades/year, win rate, avg win R, avg loss R, **net avg R/trade**, total R, profit factor, t-stat, Sharpe (daily R series), max drawdown in R, longest losing streak (trades and days)
2. Results **by year**, **long vs short**, and **by entry hour**
3. **Random-entry benchmark:** 1,000 simulations with the same trade count, same entry timestamps, **random direction**, and identical stop/target/exit geometry. Report the strategy's percentile.
4. % winning days / weeks / months
5. Cost sensitivity (×1, ×1.5, ×2) and fill sensitivity (trade-through vs touch)
6. A grid heat-map showing whether the result is a stable region or a lone spike
7. **Total number of configurations tried** across the whole project, plus a deflated Sharpe ratio (DSR) or White's Reality Check on the winner

---

## 1. Shared ICT primitives (precise, causal definitions)

All definitions use only information available at the bar's close. `L` = swing lookback.

| Concept | Definition used in this spec | Default | Grid |
|---|---|---|---|
| **Swing high** | Bar *i* whose high is greater than the highs of the `L` bars before and after it. It is **confirmed only at bar i+L**; never use it before then | L = 3 (1m) | 2, 3, 5 |
| **Swing low** | Mirror of swing high | | |
| **Liquidity level** | A confirmed swing high/low that price has not yet traded through. Also PDH/PDL and the session highs/lows: Asia 18:00–00:00 ET, London 02:00–05:00 ET | | |
| **Liquidity sweep (sell-side)** | A bar trades **below** a liquidity low by ≥ 1 tick, and that bar **or one of the next `M` bars closes back above** the level | M = 3 | 1, 3, 5 |
| **Liquidity sweep (buy-side)** | Mirror of the sell-side sweep | | |
| **Displacement** | A candle in the reversal direction with body ≥ `k` × ATR(14) of the same timeframe **and** body/range ≥ 0.6 | k = 1.0 | 0.7, 1.0, 1.5 |
| **Bullish FVG** | 3 bars (i−2, i−1, i) with `low[i] > high[i−2]`. Zone = [high[i−2], low[i]] | min size ≥ 0.1 × ATR(14) | 0.05, 0.1, 0.25 × ATR |
| **Bearish FVG** | `high[i] < low[i−2]`. Zone = [high[i], low[i−2]] | | |
| **FVG expiry** | The FVG is invalid once a bar **closes** beyond its far edge, or after `X` bars | X = 60 (1m) | 30, 60, 120 |
| **FVG entry price** | **Proximal edge** (first edge price reaches on the retrace) | proximal | midpoint (the "consequent encroachment" or CE level) |
| **IFVG (inversion FVG)** | A bearish FVG becomes a **bullish IFVG** when a bar's **body closes fully above the FVG's top**; mirror for a bearish IFVG | | |
| **Retest** | After formation, a later bar trades back into the zone | | |
| **Engulfing (bullish)** | Previous bar bearish (close < open); current bar bullish with `open ≤ prev close` and `close ≥ prev open` (body engulfs body) | | also the "close > prev high" variant |
| **DOL near (target)** | The nearest unswept opposing liquidity level beyond entry that is at least 1R away | | |
| **DOL far (target)** | The **next** opposing liquidity level beyond DOL-near, or PDH/PDL if closer | | |

### Bias definitions (the videos never define "bias")
Pre-register these. Each is causal and can be computed at the session open:
- **B0: none**
- **B1, daily close vs open:** long-only if yesterday closed above its open, else short-only
- **B2, midnight open:** long-only if price at entry is above the 00:00 ET open, short-only if below (common ICT usage)
- **B3, daily trend:** long-only if yesterday's close is above the 20-day EMA of daily closes, else short-only
- **B4, 15-minute trend:** long-only if the 15m EMA 20 is above the 15m EMA 50 at entry, else short-only (this is video D's "15m bias", which they found hurts)
- **B∞, perfect hindsight (diagnostic only, not tradeable):** direction = sign of (16:00 close − 09:30 open). Video D reported Sharpe 1.02 with this. Use it only to measure the most any bias filter could add.

---

## Strategy A: IFVG model (onlyansss)

**Shown in video:**
- Instrument and timeframe: NQ futures, **1-minute**, session **09:30–11:30 NY**
- Tested over **593 sessions** (21/06/2024 → 08/10/2026), with results **before fees and slippage**
- **Long rules:**
  1. Price sweeps a prior swing low
  2. A down-move creates a **bearish FVG**
  3. A candle **body closes fully above** that FVG, so it becomes a **bullish IFVG**
  4. Price **retests** the IFVG and a bar closes
  5. Enter with a **market order at the next bar's open**
- **Exits:** SL below the sweep low / setup structure. TP at DOL (near or far)
- **Short:** the exact mirror of the long rules
- **Reported results (total R, not per trade):**

| Round | Rules | Trades | Total R | ≈ R/trade |
|---|---|---|---|---|
| 1 | No bias, DOL near | 1,561 | +2.40R | **+0.002** |
| 2 | + bias filter, DOL near | 723 | +181.32R | +0.25 |
| 3 | + bias filter, DOL far | 675 | +558.92R | +0.83 |

- Compared with their "ICT 2022 model": rounds 1/2/3 gave +2.27R / +67.32R / +186.38R. That model isn't defined, so it is out of scope.

**NOT SHOWN → defaults:**
| Item | Default | Grid |
|---|---|---|
| Bias rule | test **all** of B0–B4 (main question: does any *causal* bias reproduce round 2/3?) | B0–B4, plus B∞ diagnostic |
| Swing lookback `L` | 3 | 2, 3, 5 |
| Max time from sweep → FVG → inversion | 30 bars each step | 15, 30, 60 |
| Retest window after inversion | 30 bars | 15, 30, 60 |
| SL | Sweep extreme − 1 tick | Also: IFVG far edge − 1 tick |
| TP | DOL near / DOL far (as in the video) | Also fixed 2R, 3R |
| Trades per day | Multiple allowed, one open position at a time | Also max 1/day |
| Unfilled / still open at 11:30 | No new entries after 11:30; open trades managed to TP/SL or 16:00 flat | — |

**Key check:** round 1 (no bias) is roughly zero edge, so the whole claim rests on the undefined bias filter. Run B∞ to see the ceiling a perfect bias could reach. If B1–B4 don't get close, round 2/3 was most likely built on hindsight bias.

---

## Strategy B: First candle rule (LuxAlgo / VELA)

**Shown in video:**
- NQ and ES futures. **Opening range (OR)** = high and low of the **09:30–09:35 ET 5-minute candle**
- Executed on the **1-minute** chart. Setups are tracked until **10:00 ET**
- **Long rules:**
  1. A 1-minute **breakout candle with a strong body closes above the OR high**, forming a **3-candle bullish FVG** (the breakout candle is the middle bar)
  2. Price **retraces into that FVG**
  3. A **bullish engulfing** candle forms inside or at the FVG
  4. **Enter at the close of the engulfing candle**
- **Short:** the mirror of the long rules
- **SL:** beyond the engulfing structure (below its low for longs, above its high for shorts)
- **TP:** **fixed 3R**
- **1 trade per day**
- No statistics shown, only chart examples. The host found that setups are rare and recommended a **30-minute opening range breakout** instead.

**NOT SHOWN → defaults:**
| Item | Default | Grid |
|---|---|---|
| "Strong body" | body/range ≥ 0.6 | 0.5, 0.6, 0.7 |
| SL anchor | min(low of engulfing bar, low of previous bar) − 1 tick (long) | Also: FVG far edge − 1 tick |
| Setup deadline | Engulfing entry must happen by 10:00 ET | 10:00, 10:30, 11:00 |
| Exit if neither SL nor TP hit | 16:00 ET flat | — |
| TP | 3R | 2R, 3R |

**B-alt: 30-minute ORB (the host's recommendation; their rules aren't given, so these are our defaults):**
- OR = 09:30–10:00 ET high and low
- Entry: first **5-minute close** beyond the OR, entering at the next bar's open. Max 1 trade/day, first breakout only
- SL: opposite side of the OR (variant: OR midpoint)
- TP: 2R (grid 1.5R, 2R, 3R). Force-flat at 16:00

---

## Strategy C: ICT Silver Bullet, textbook (VT Markets)

**Shown in video:**
- **Time windows (NY time):** 03:00–04:00, **10:00–11:00 (primary)**, 14:00–15:00
- **Before the window:**
  1. Decide the **daily bias**
  2. Mark **target liquidity**: PDH/PDL or major swings
- **Inside the window:**
  1. Price **sweeps a short-term low**
  2. **Displacement** up that creates an **FVG fully formed inside the window**
  3. Price retraces into the FVG
  4. **Buy at the FVG**
- **SL:** below the swept low. **TP:** the pre-marked liquidity level (e.g. PDH)
- **Target must be ≥ 10 points** (indices). Skip the trade if it's smaller
- **1 trade per window.** If stopped out, done for the day. If no FVG forms in the window, no trade
- **No statistics:** the video says there's no audited proof that it makes money

**NOT SHOWN → defaults:**
| Item | Default | Grid |
|---|---|---|
| Instrument / timeframe | NQ, 1-minute | Also 5-minute |
| Daily bias | B1 | B0, B1, B2, B3 |
| Sweep target | Confirmed 1m swing low/high (L=3) formed before the sweep | L = 2, 3, 5 |
| Entry | Limit at the FVG proximal edge, valid until window end | Also midpoint (CE) |
| SL | Swept extreme − 1 tick | — |
| TP | The nearest of PDH/PDL / major (L=20) swing in the bias direction; must be ≥ 10 NQ pts (ES: ≥ 2.5 pts) **and** ≥ 1R | min distance 10, 20 pts |
| Exit if neither hit | Hold to 16:00 flat | Also close at window end (video D's textbook rule) |
| Windows | 10–11 only | All three windows |

---

## Strategy D: ICT Silver Bullet, "practitioner" version + ablation (fxtactix)

**Shown in video (their setup; reproduce it):**
- NQ (develop) and ES (cross-market check, **no re-tuning**). **1-minute** data, 16 years
- **Split:** 14 years in-sample, **last 2 years locked out-of-sample**, tested once
- **Costs:** commission plus **slippage on stop orders**. **Same-bar SL+TP = loss**
- **Practitioner rules:**
  - **Liquidity** = nearest recent swing high/low
  - **Sweep is mandatory**. **Direction is opposite the sweep** (sweep a low → buy only)
  - **1-minute FVG**, entered with a **limit order at the FVG edge/midpoint**
  - **SL** beyond the swing/displacement extreme
  - **TP** at the opposing liquidity level or **fixed 2R** (1R variant)
  - **No 15m bias**, **all ~23 hours** of the session, **every valid setup** taken (~1,906 trades/yr, 7–8/day)
- **Their results:**
  - **Funnel:** 25,000 configs → 9,481 with ≥ 100 trades → 6,190 net profitable → 2,191 with Sharpe ≥ 0.5 → 1,614 after their multiple-testing correction → **420 also pass on ES**
  - **Win rates:** textbook 5m 46% / 48% (NQ/ES), textbook 1m 37% / 34%, practitioner 42% / 42%, median survivor ~52%
  - **Ablation (cumulative Sharpe):**

    | Step | Sharpe |
    |---|---|
    | FVG only, all day | 0.33 |
    | + sweep | **0.69** |
    | + displacement | 0.59 |
    | + 3 hour windows | 0.56 |
    | + 15m bias | 0.16 |
    | Perfect-hindsight bias (benchmark) | 1.02 |

  - **% winning months:** textbook 5m 43%, textbook 1m 48%, practitioner 62%, best config 68%
  - **Longest losing run of the best config:** 19 days
  - **Out-of-sample, 2 years, 1 NQ contract:** best config **+$455k, Sharpe > 13, 24/24 winning months**; practitioner +$251k; textbook 1m +$34k (254 trades); textbook 5m +$12k (79 trades)

**⚠️ Red flag:** an out-of-sample Sharpe above 13 with 24 out of 24 winning months is far beyond any realistic result for a 1-minute strategy. The usual causes on 1-minute data:
- (a) limit orders counted as filled on a touch;
- (b) the order of high and low within a bar is unknown;
- (c) swings or FVGs used before they were confirmed (lookahead);
- (d) costs that are too low relative to small stops.

The backtest must show the trade-through vs touch fill comparison and the cost-per-trade in R. It should also do a **lookahead audit:** shift all signals one bar later, and expect a strategy with a real edge to degrade only mildly.

**What to run:**
1. **Ablation ladder** (reproduce their table, NQ dev): FVG-only all day → + sweep → + displacement → + windows (03–04, 10–11, 14–15) → + B4 bias. Also B∞ as a diagnostic.
2. **Practitioner config** with these defaults:

| Item | Default | Grid |
|---|---|---|
| Swing lookback L | 3 | 2, 3, 5 |
| Sweep confirmation M | 3 | 1, 3 |
| Displacement | **off** (the ablation says it hurts) | on (k=1.0) |
| Entry | Limit at FVG proximal edge | midpoint (CE) |
| FVG must form within N bars of the sweep | 10 | 5, 10, 20 |
| SL | Sweep extreme − 1 tick | — |
| TP | 2R | 1R, 2R, opposing liquidity (DOL near) |
| Session | All Globex hours except 16:00–18:00 ET | RTH only |
| Concurrency | One position at a time | — |
| Time exit | 120 minutes after entry | 60, 120, 240 min |

3. **Textbook 1m and 5m:** use strategy C's rules, but with all 3 windows and closing at window end, to match their benchmarks.
4. **Cross-market check:** run the frozen NQ-chosen configs on ES with no changes. Count only configs that are net-positive on **both** markets.
5. Then the holdout (2023+), once.

---

## Strategy E: ATR × √hold-time stop sizing (huuducgroup)

**Shown in video (gold, 1-hour chart, ATR period 14):**
- **Formula:** expected move over N hours ≈ **ATR(14, 1h) × √N**. Their 1h ATR was ~$15 (2-year median $13.5)

| Hold N | Formula | Measured |
|---|---|---|
| 8h | $38 | $37 |
| 24h | $66 | $65 |
| 48h | $94 | $92 |

- **Stop hit within 24h:** 1×ATR → 73%, 2×ATR → 52%, 3×ATR → 35%. After a 1×ATR stop was hit, price returned to entry **74%** of the time
- **Rule:** place the stop outside "a significant part" of ATR × √N (exact multiplier NOT SHOWN). Size = risk ÷ stop distance
- **No entry signal.** This is a stop-placement study.

### E1: replicate the statistics (XAUUSD, and repeat on NQ)
For **every hourly bar open** (that is the random-entry sample), with ATR = ATR(14) on completed 1h bars:
1. **Range check**, for N ∈ {4, 8, 24, 48, 120}: report the median and mean of **|close(t+N) − close(t)|** and of **(max high − min low) over the next N hours**, next to ATR × √N. The video didn't say which "measured" range it used, so report both. Also split by year and by volatility tercile.
2. **Stop-hit probability**, for long and short separately: stop at entry ∓ k × ATR with k ∈ {1, 2, 3}, holding 24h. Report the % hit within 24h, and the % of hits where price **returns to entry** within the rest of the 24h window **and** within 24h after the hit.
3. **√N stop rule**: stop = c × ATR × √N with c ∈ {0.5, 0.75, 1.0, 1.25} and N ∈ {8, 24, 48}. Report the % stopped before N hours.

### E2: use it as an SL module (most relevant for my bot)
- Re-run any strategy above that holds longer (or my own multi-day signals on MNQ/MGC) with the stop = c × ATR(14, 1h) × √(planned hold hours), c ∈ {0.75, 1.0}
- TP sweep {1R, 2R, 3R}, size = 1R
- Compare net avg R against each strategy's original stop rule
- Feature for my ML SL/TP model: `atr1h * sqrt(N)` for N ∈ {8, 24, 48}, as a normalised stop distance

---

## Decision rule (stated before running)
A configuration is worth keeping only if **all** of these hold:
- Dev **net avg R > 0** after costs, and still ≥ 0 at costs × 1.5 **and** with trade-through fills
- ≥ 3 of 4 dev years positive, **and** positive on ES without re-tuning (A–D)
- Above the **95th percentile** of the random-direction benchmark
- DSR > 0.95 (or survives White's Reality Check), given the total number of configs tried
- Neighbouring grid cells are also positive (no lone spike)
- Signals shifted by 1 bar stay positive (lookahead audit)
- **Holdout net avg R > 0** with everything frozen beforehand

Otherwise report it as **no edge** and stop. Don't add filters after looking at the holdout.

### Prior evidence (from my own research)
A session-open momentum rule on USATECHIDXUSD/USA500IDXUSD already tested **negative** (net ≈ −0.03 to −0.07 R/trade, t ≈ −2 to −4, dev 2019–2022). Treat any 1-minute intraday edge as unlikely until it passes the full checklist. My own trading is multi-day (hold until SL/TP), so E2 and any setup that still works with longer holds matter most.
