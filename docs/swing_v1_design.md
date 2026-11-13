# Swing v1: multi-day futures signals, design (frozen before any results)

Date: 2026-11-13. The user switched to multi-day trades (days to weeks) on futures, at most 3 markets, with
volatility-based sizing. Trades are held until SL or TP (the time cap is only a safety cap). The user
delegated rule details to the supervisor; this file freezes them before any swing data is examined.

Periods: DEV = data up to 2022-12-31 (all development). 2023–24 is spent and is not used. Final 2025+
stays locked and is evaluated once, later, only with the user's approval.

## 1. Markets and data

Traded (verdict is taken on these three, pooled):

| Contract | Underlying data (1-minute, local) | DEV years used |
|---|---|---|
| MNQ (Micro Nasdaq-100, $2/pt, tick 0.25) | Dukascopy USATECHIDXUSD, bid/ask mid | 2012–2022 |
| MGC (Micro Gold, 10 oz, $10/pt, tick 0.1) | Dukascopy XAUUSD, bid/ask mid | 2003–2022 |
| MBT (Micro Bitcoin, 0.1 BTC, $0.1/pt, tick 5) | Binance spot BTCUSDT, trade prices | 2018–2022 |

The first year of each market is warm-up only (indicators), never traded.

Evidence markets (same frozen code, no tuning, never traded): Dukascopy USA500IDXUSD, USA30IDXUSD,
DEUIDXEUR, LIGHTCMDUSD, BRENTCMDUSD, XAGUSD, EURUSD, GBPUSD, USDJPY; Binance spot ETHUSDT. They answer
"does the rule work broadly, or only on our three by luck?"

Spot/CFD prices stand in for futures prices. For multi-day holds they move together; the differences
(carry and roll) are charged explicitly in section 6.

## 2. Daily bars and timing

- Daily bars are built from 1-minute mid prices with the day closing at **17:00 New York** (the CME
  session end), all markets including BTC.
- Signals are computed at the daily close from completed daily bars only.
- **Entry: the open of the 07:00 UTC 1-minute bar on the next trading day** (09:00–10:00 Finland), so the
  user can act on a signal in the morning. Sensitivity row: entry at the 18:00 New York reopen.
- SL and TP are fixed at entry and never moved.

## 3. Futures hours

SL/TP are checked on 1-minute bars **inside CME Globex hours only** (Sunday 18:00 – Friday 17:00 New York,
daily break 17:00–18:00). If the first in-session bar opens beyond SL or TP (weekend or overnight gap),
the exit fills at that bar's open, not at the SL/TP price. This matters most for BTC, whose spot market
trades through the weekend while MBT is closed. If SL and TP fall inside the same minute, SL is assumed
first.

## 4. Setups (what decides the direction)

At most one open trade per market. A new setup is ignored while a trade is open in that market.

- **S1 Breakout 20:** daily close above the highest close of the previous 20 days → long; below the
  lowest close → short.
- **S2 Breakout 55:** the same with 55 days.
- **S3 Trend (time-series momentum):** when flat, go long if the 126-day (≈6-month) return is positive,
  short if negative. This re-enters after every exit while the trend lasts.

ATR = daily ATR(20) at decision time.

## 5. SL/TP menu

SL: **1, 2 or 3 ATR** from entry. TP: **1.5R, 2R, 3R or 5R**. That is 3 × 4 = 12 options per setup.
Safety cap: **30 trading days** (≈6 weeks); then exit at the next in-session 1-minute open.
**Primary option (named in advance): SL 2 ATR, TP 3R.** The other 11 are reported, and the best of them is
marked as chosen in hindsight.

## 6. Costs (futures, per micro contract, converted to R by the SL distance)

| | Spread (round trip) | Commission + fees (round trip) | Extra stop slippage | Roll (when held across) |
|---|---|---|---|---|
| MNQ | 1 tick = 0.25 pt | $2.50 = 1.25 pt | 1 tick on SL/gap exits | 1 spread + 1 commission |
| MGC | 1 tick = 0.1 pt | $2.50 = 0.25 pt | 1 tick | 1 spread + 1 commission |
| MBT | 2 ticks = $10/BTC | $6.00 = $60/BTC | 1 tick | 1 spread + 1 commission |

- Roll charged at the expected rate: holding days ÷ roll period (MNQ 91 days, MGC 61, MBT 30) × roll cost.
- **Carry:** futures prices include financing. Longs pay it and shorts receive it, at a fixed annual rate:
  NQ 3%, gold 4%, BTC 8% of price, pro rata by calendar days held. Rows without carry and at 2× costs are
  also reported.
- Evidence markets use the cost row of their closest traded contract, scaled to price (same % of price).

## 7. Stage 1: raw rules (no ML)

For every setup × option × market: trades, trades/year, mean hold in days, hit rate, net R per trade,
t-stat, positive-year share, max drawdown (R), exits split into SL/TP/cap. Each setup counts as one
configuration (3 in total) in reports/trials.csv.

Random baseline: the same entry times and options with a random direction (200 seeds).

**Stage 1 passes** if at least one setup's primary option (SL 2 ATR, TP 3R) has, pooled over the three
traded markets:
- net R per trade > 0 with t ≥ 2;
- a positive result in at least 2 of the 3 markets;
- a positive result in ≥ 60% of DEV years;
- a result above the 95th random-direction percentile;
- a positive average over the evidence markets.

If no setup passes, swing v1 stops here and the result is reported to the user.

## 8. Stage 2: the model picks SL/TP (only if stage 1 passes)

One LightGBM classifier gives P(TP before SL) for each (setup trade, option), with the option geometry as
an input. The other inputs are causal daily features: trend strength at 20/60/126 days, ATR percentile,
distance to the 20/55-day extremes, market, and day of week. The decision is `msd.research.decision.choose`
(expected R after costs, shrunk for uncertainty, threshold 0.05R): take the best option or skip.
Validation is purged walk-forward by year, pooled across the three markets. To pass, stage 2 must beat
the stage 1 primary option on the same trades, with the same tests as stage 1. At most 10 stage 2
configurations.

## 9. Sizing (applied after research; results are in R)

- Risk **1% of the account per trade**: contracts = floor(account × 1% ÷ (SL points × $ per point)).
- Skip the trade if that is 0 contracts.
- At most 3 open trades, so at most 3% total risk.
- The report shows, for given account sizes, what share of trades is too large to take with even one
  micro contract.
