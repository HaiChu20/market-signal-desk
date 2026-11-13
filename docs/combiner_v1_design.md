# Range-bounce combiner v1: design (frozen before any results)

Date: 2026-11-13. The user's setup is "buy at the bottom / sell at the top of a sideways range". The user
delegated the rule details to the supervisor; this file freezes them before any data is examined.
DEV data only (up to 2022-12-31). Test 2023–24 is spent. Final 2025+ stays locked and is touched once,
later, only with the user's approval.

## 1. Market

Primary: **XAUUSD** (DEV 2008–2022, 15 years, the longest history; the only market where the Family 2 CNN
was positive on all three seeds). The verdict is taken on gold. The same frozen code also reports NQ, SPX,
BTC and ETH as secondary rows (no separate tuning).

## 2. Candles

- Ranges are found on **15m candles** (main) and on **1h candles** (one variant). Tops and bottoms are
  confirmed swings (`msd.levels.confirmed_swings`, 3 candles each side), usable only after confirmation.
- Entry, stop and target are simulated on **1-minute bars** with bid/ask, as in all other labels.
- Model inputs may use 1m, 15m, 1h and 1d features (all causal, `known_at` ≤ decision time).

## 3. "Sideways" (both bounce and duration)

A range is active when all hold, using ATR = 1h ATR(14) at decision time:
- at least **2 confirmed tops and 2 confirmed bottoms** inside the window;
- the tops are within **0.5 ATR** of each other, and so are the bottoms;
- range height (mean top − mean bottom) is between **1.5 and 6 ATR**;
- the range has lasted at least **8 candles** (2 h on 15m, 8 h on 1h);
- no candle has closed beyond the top or bottom by more than 0.25 ATR since the range formed.

Lookback: the last 48 candles (12 h on 15m, 2 days on 1h).

## 4. Setup (candidate trade)

- When a 1-minute bar comes within **0.1 ATR** of the bottom, the candidate is **buy**; near the top, **sell**.
  Entry is the next 1-minute open (ask for buys, bid for sells).
- Re-arm only after price has moved back to the inner 50% of the range; at most one candidate per edge
  per range per hour.
- **Range ends (stop trading it)** when a 15m (or 1h) candle closes more than 0.25 ATR beyond an edge.
- Direction always comes from the setup. The model never flips it.

## 5. SL/TP menu (the model chooses, not a fixed rule)

Stop: beyond the touched edge by **0.25, 0.5 or 1.0 ATR**.
Target: **middle of the range, 75% of the way across, the far edge**, or a fixed **1R** or **2R**.
That is 3 × 5 = 15 options per setup. Each option is labelled on 1-minute bars until SL or TP is hit
(safety cap 5 trading days, time exit at the next open), net of the measured spread. Funding and
overnight fees are ignored at the user's request; the spread is always charged.

## 6. Model ("combiner")

- One LightGBM classifier: P(TP before SL) for each (setup, option); the option geometry is an input.
- Inputs: range height, age, touch counts, distance of entry from the edge, the volatility forecast
  (predicted absolute move, the part we can predict), trend strength on 15m/1h/1d, time of day, day of
  week, the spread in ATR.
- Decision: `msd.research.decision.choose` (expected R after spread, shrunk for uncertainty, threshold
  0.05R): take the best option or skip the setup. Size is fixed at 1R in v1.
- Validation: purged walk-forward by year on DEV (train on earlier years, predict the next year;
  first predicted year 2012 for gold, 2021 for NQ/SPX, 2022 for crypto).

## 7. Baselines and pass rule (gold)

Compared on the same out-of-fold setups:
- **A. Raw strategy:** take every setup with each fixed option (15 rows; the best one is reported but
  marked as chosen in hindsight).
- **B. Random direction** with the model's chosen options and timing (200 seeds).

Pass, all of: model net R per trade > 0 with t ≥ 2; positive in ≥ 60% of predicted years; better than
the hindsight-best raw option; above the 95th random percentile; at least 200 trades.
At most 20 configurations (the 15m/1h variant counts as 2). Every configuration is appended to
reports/trials.csv.
