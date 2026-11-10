# Method index

Frozen trigger definitions and natural levels are in each module docstring. Signals use completed bars only. Expected volume for each new detector is at most twelve events per instrument-day after a four-hour same-side cooldown.

| # | Method | Role | Markets | Natural levels | Definition |
|---:|---|---|---|---|---|
| 2 | `round_number_reaction` | core level | all | Beyond level/bar +0.2 ATR / 2R | At an active confirmed round-number level, emit on a one-minute bar whose range enters +/-0.15 ATR(1h); direction is the close side of the level. Stop beyond the bar/level by 0.2 ATR; target 2 stop distances. |
| 3 | `session_level_reaction` | core level | all | Beyond level/bar +0.2 ATR / 2R | React to a causal prior-day/week high or low, overnight high/low, or confirmed 15-minute opening-range edge when the bar enters +/-0.15 ATR(1h). Direction follows the close side; stop beyond level/bar plus 0.2 ATR; target 2R. |
| 4 | `supply_demand_zone_retest` | feature | all | Beyond zone edge/bar +0.2 ATR / 2R | At first qualifying retest of an active supply/demand zone edge within 0.15 ATR(1h), place a four-minute limit at the edge in the direction of the close. Stop beyond edge/bar by 0.2 ATR; target 2R. |
| 5 | `trendline_channel` | low priority feature | all | Beyond projected line +0.2 ATR / 2R | Project a line through the last two confirmed lows/highs with rising/falling slope, and emit on a reclaim touch within 0.2 ATR. Stop beyond line/bar; target 2R. |
| 6 | `market_structure_pullback` | core | all | Beyond last confirmed opposite swing +0.2 ATR / prior swing or 2R | After confirmed 1h/15m swing and positive/negative EMA50-200 trend, emit when a bar retests and closes beyond the broken high/low. Stop beyond the last confirmed opposite swing by 0.2 ATR; target prior high/low. |
| 7 | `dow_trend_confirmation` | filter feature | all | Beyond signal bar by 1.2 ATR / 2R | Emit on a fresh 1h EMA50/200 trend cross that agrees with the last completed daily EMA50/200 regime and has positive 20-bar volume z-score. Stop beyond the bar by 1.2 ATR; target 2R. |
| 8 | `chart_patterns` | filter feature | all | Beyond pattern extreme +0.2 ATR / 2R | Use confirmed 15m-4h alternating pivots: double top/bottom has two similar extremes; H&S has a higher/lower middle extreme and similar shoulders. Emit only on neckline break after final pivot confirmation. Stop beyond pattern extreme plus 0.2 ATR; target 2R. |
| 9 | `candlestick_at_level` | entry feature | all | Beyond wick/level +0.2 ATR / 2R | At a currently active confirmed level cluster candidate within 0.15 ATR, a bullish/bearish candle with a wick of at least 0.3 ATR emits toward the candle body. Stop beyond wick/level plus 0.2 ATR; target 2R. |
| 10 | `price_action_h2l2` | feature | all | Beyond opposite swing +0.2 ATR / prior swing or 2R | In 1h EMA50/200 trend, two alternating pullback legs followed by close beyond prior bar high/low trigger H2/L2 continuation. Stop beyond last confirmed opposite swing plus 0.2 ATR; target prior swing. |
| 11 | `fib_pullback` | depth feature | all | Beyond opposite swing +0.2 ATR / prior extreme | In positive/negative 1h EMA50/200 trend, first entry into 40-60% retracement of a confirmed high-low swing emits with trend. Stop beyond opposite swing plus 0.2 ATR; target prior extreme. |
| 12 | `order_block_retest` | feature | all | Beyond block far edge +0.2 ATR / 2R | The opposite candle immediately preceding a confirmed swing break forms a block; retest its near edge within 60 bars by four-minute limit. Stop beyond far edge plus 0.2 ATR; target 2R. |
| 13 | `fvg_retrace` | feature | all | Beyond gap far edge +0.2 ATR / 2R | A three-candle gap of at least 0.1 ATR is known at bar 3 close; a later retest of its near edge within 60 bars places a four-minute limit. Stop beyond far edge plus 0.2 ATR; target 2R. |
| 16 | `ote_zone` | feature | all | Beyond opposite swing +0.2 ATR / prior extreme | In 1h EMA50/200 trend, first entry into 62-79% retracement of a confirmed high-low swing places a four-minute limit at the 62% boundary. Stop beyond opposite swing plus 0.2 ATR; target prior extreme. |
| 17 | `wyckoff_spring_upthrust` | feature | all | Beyond sweep wick/swing +0.2 ATR / opposite swing or 2R | A spring/upthrust wicks at least 0.1 ATR beyond a confirmed swing low/high and closes back inside on the same bar. Stop beyond wick/swing plus 0.2 ATR; target opposite swing. |
| 21 | `ma_cross` | regime | all | Beyond signal bar by 1.2 ATR / 2R | Emit on fresh 1h EMA20/50 or EMA50/200 gap sign cross. Stop beyond signal bar by 1.2 ATR; target 2R. |
| 23 | `macd_signal` | low expectation | all | Beyond signal bar by 1.2 ATR / 2R | Emit on fresh 1h MACD histogram zero cross. Stop beyond signal bar by 1.2 ATR; target 2R. |
| 24 | `bollinger` | volatility feature | all | Beyond signal bar by 1.2 ATR / 2R | Variant band_reversion emits on 1h percent-b reentry inside 0/1 after outside close; variant squeeze_breakout emits when width is below trailing 100-observation 20th percentile and percent-b breaks outside. Stop 1.2 ATR; target 2R. |
| 25 | `stochastic` | low expectation | all | Beyond signal bar by 1.2 ATR / 2R | Emit on fresh 1h stochastic K-D cross with K under 25 for long or over 75 for short. Stop 1.2 ATR; target 2R. |
| 26 | `vwap_reclaim_reject` | level feature | all | Beyond signal bar by 1.2 ATR / 2R | Emit on fresh crossing of session VWAP distance from negative to positive or reverse. Session VWAP is accumulated only through current bar; stop 1.2 ATR; target 2R. |
| 27 | `donchian_atr_breakout` | trend feature | all | Beyond signal bar by 1.2 ATR / 2R | Emit on first 1h Donchian-20 channel position crossing 0.99 or 0.01. Stop 1.2 ATR; target 2R. |
| 28 | `ichimoku_cloud` | low expectation | all | Beyond signal bar by 1.2 ATR / 2R | Causal Tenkan(9)/Kijun(26) high-low midpoint cross on completed one-minute bars, with close on crossing side. No forward-shifted cloud is used. Stop 1.2 ATR; target 2R. |
| 29 | `volume_profile_poc_vah_val` | level source | all | Beyond profile level/bar +0.2 ATR / 2R | React when price touches an active prior-day POC/VAH/VAL within 0.15 ATR. Direction follows close side of level; stop beyond level/bar plus 0.2 ATR; target 2R. |
| 30 | `btc_order_flow` | BTC feature | BTC/ETH | Beyond signal bar by 1.2 ATR / 2R | BTC/ETH only: taker-buy ratio freshly crosses 0.65 up or 0.35 down with 20-bar volume z-score above 1. Stop 1.2 ATR; target 2R. |
| 33 | `post_macro_event_reaction` | event experiment | all | Beyond signal bar by 1.2 ATR / 2R | At first bar with macro_minutes_since_event >=5 after having been <5, emit both follow and fade variants of the five-minute move if magnitude exceeds 0.2 ATR. External calendar supplies the event clock; no event without it. Stop 1.2 ATR; target 2R. |
| 34 | `post_earnings_index_reaction` | inputs pending; event experiment | NQ | Beyond signal bar by 1.2 ATR / 2R | NQ only: at first bar five minutes after a tagged megacap earnings event, follow the five-minute move if above 0.2 ATR. Stop 1.2 ATR; target 2R. |
| 37 | `trend_following` | regime | all | Beyond signal bar by 1.2 ATR / 2R | On first observation of a newly completed daily bar, emit when both 20-day and 60-day time-series returns have same sign. Stop 1.2 ATR; target 2R. |
| 38 | `intraday_momentum` | conditional feature | indices | Beyond signal bar by 1.2 ATR / 2R | After 30 session minutes, emit on first breakout beyond trailing 20-bar mean absolute distance from session open. Record gamma and VIX percentile when present. Stop 1.2 ATR; target 2R. |
| 40 | `range_breakout_nr4_nr7` | feature | all | Beyond signal bar by 1.2 ATR / 2R | When completed daily ATR is below the preceding seven observations, emit on crossing of a causal prior-day high/low distance. Stop 1.2 ATR; target 2R. |
| 44 | `vix_spike_dip_buy` | regime feature | indices | Beyond signal bar by 1.2 ATR / 2R | On newly completed daily bar for an index, emit long when VIX is above its trailing one-year 90th percentile and daily return is below -2%. Stop 1.2 ATR; target 2R. |
| 45 | `funding_extreme_fade` | BTC feature | BTC/ETH | Beyond signal bar by 1.2 ATR / 2R | BTC/ETH only: fade first crossing of published 20-observation funding z-score beyond +2 or -2. Stop 1.2 ATR; target 2R. |

Existing pilots: #1 `sr_touch`, #14 `liquidity_sweep`, #39 `rsi2_mean_reversion`.

Add-ons (filters only): #15 killzones, #32 macro_blackout, #41 time_of_day_calendar, #43 vol_sizing.

Skipped: #49 broker retail positioning has no historical data; #52 has no data.

#34 inputs pending: SEC 8-K acceptance timestamps are filing times, not earnings-release times. A verified release-time calendar and causal feature clock are required before evaluation.
