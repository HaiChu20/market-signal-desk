# Strategy research (2026-11-09)

Scope: a 24/7 signal bot sending Telegram alerts (pair, entry, stop loss, take profit,
confidence) for manual, leveraged trading of Nasdaq-100, S&P 500 and BTC.

## Bottom line

No published strategy is "the most profitable". The ones below have the best evidence
(peer-reviewed or well-documented, with costs and out-of-sample checks), and each should
be re-validated on the exact instrument and spread we trade before real money goes in.

| # | Strategy | Market | Evidence | Reported result |
|---|----------|--------|----------|-----------------|
| 1 | Intraday momentum, "Noise Area" breakout + VWAP trailing stop | SPY / QQQ → NQ, ES | Zarattini, Aziz, Barbon (SFI 24-97, 2024) | SPY 2007–2024, net of IBKR costs: 19.6%/yr, vol 14.3%, Sharpe 1.33, MDD 25%, hit rate 43%, leverage ≤ 4x |
| 2 | Donchian-channel trend ensemble, volatility-sized | BTC | Zarattini, Pagani, Barbon (SFI 25-80, 2025) | Net-of-fees Sharpe > 1.5 (top-20 coin rotation); BTC-only figures need checking in the paper |
| 3 | Intraday trend on BTC (supporting evidence) | BTC | Shen, Urquhart, Wang, *Financial Review* 2022; Concretum note 2026 | Intraday momentum predictive in and out of sample; ensemble benchmark Sharpe ~1.6 *gross*, 2018–2025 |

Background that backs these: time-series momentum in futures (Moskowitz, Ooi, Pedersen,
JFE 2012); first-half-hour predicts last-half-hour return (Gao, Han, Li, Zhou, JFE 2018);
volatility-scaled sizing improves Sharpe (Moreira & Muir, JF 2017).

## Strategy 1 — Noise Area intraday momentum (indices)

Rules as published (SPY, regular session 09:30–16:00 ET):

1. For each time-of-day `HH:MM`, `σ(HH:MM)` = mean over the last 14 days of
   `|Close(HH:MM) / Open(09:30) − 1|`.
2. Bands: `Upper = max(Open, PrevClose) × (1 + σ)`, `Lower = min(Open, PrevClose) × (1 − σ)`.
3. Only at `HH:00` and `HH:30`: long if price > Upper, short if price < Lower.
4. Trailing stop, also only checked at `HH:00`/`HH:30`: long stop = `max(Upper, VWAP)`,
   short stop = `min(Lower, VWAP)`. Flip on crossing the opposite band. Flat at the close.
5. Size: `capital × min(4, 2% / σ_daily(14d)) / price`.

Progression in the paper: opposite-band stop Sharpe 0.61 → current band + VWAP stop
Sharpe 1.24 → plus volatility sizing Sharpe 1.33. It does best in high-volatility regimes
(Sharpe ~3.5 on days with VIX > 40). Costs used: $0.0035/share + $0.001 slippage, which is
much cheaper than a typical CFD spread.

Things that change for us:
- The edge depends on letting winners run (best trade +9.1%, worst −2.9%, 43% hit rate).
  A fixed take-profit cuts that tail. TP must be calibrated in the backtest, and the bot
  should also send "move stop" / "exit now" updates.
- The authors' slides show QQQ at Sharpe ~2.0; we could not confirm it is net of costs.
- A replication of the *related* opening-range-breakout paper on index CFDs reproduced
  the gross edge but found it **zero after spreads** (MQL5 blog, 2015–2026). Same risk applies
  here: we must backtest with our broker's real spread.

## Strategy 2 — BTC trend ensemble

Multiple Donchian channel breakout lookbacks averaged into one position, sized to a
volatility target. Robust to costs of 0.10–0.50% per trade according to the paper. Lower
trade frequency than strategy 1, so costs and funding matter less. Signals will be rarer
(days, not hours).

## Technical analysis: support/resistance, trend, patterns (added after user question)

- Evidence is mixed. In Park & Irwin's 2007 survey, about 56 of 95 modern studies find
  trading rules profitable, but many of those studies are exposed to data snooping. Profits
  are weaker in recent decades and in equity indices than in FX and commodity futures.
- Inside the Noise Area paper, daily patterns used as *filters* helped. Avg PnL per day
  (bps) and Sharpe ratio, against an unconditional 12 bps / 1.7:
  NR4 22 bps / 3.2 (t 5.1), NR7 16 / 2.5, Triangle 14 / 2.0. Inside days, outside days
  and trend days were not significant.
- Use in this project: S/R levels (prior-day high/low, overnight high/low, VWAP,
  opening range, recent swing highs/lows) place the SL behind a level and the TP at the
  next level. Patterns act as confidence/size filters. Neither generates trades on its own.
- 1-minute candles: use them as *input* for exact levels, VWAP and fast breakout
  detection. Signals whose expected move is only a few 1-min bars are dominated by the CFD
  spread. A 1-min scalp variant will still be backtested, so the data decides.

## Model design: rule setups + ML filter (meta-labeling)

From López de Prado, *Advances in Financial Machine Learning* (2018), ch. 3 and 7:

1. **Primary rules** propose candidate trades with side, entry, SL and TP: the Noise Area
   breakout, a support/resistance fade that stops and reverses into the breakout, an
   ICT-style liquidity sweep + fair value gap retest, and the BTC Donchian trend.
2. **Triple-barrier labels**: each candidate's label is whichever comes first of TP,
   SL, or a time limit. These are the exact levels sent in the signal.
3. **Meta-model** (start with logistic regression, then gradient-boosted trees) on
   features: indicators, distance to levels, NR4/NR7/triangle, time of day, volatility
   regime, gap. Output = P(TP before SL) = the confidence field. Send only when expected
   R after spread > 0.
4. **Feature selection**: purged walk-forward + permutation importance, not p-value
   backward elimination (which overfits on noisy, overlapping financial labels).
5. **Overfitting control**: purged/embargoed CV, a random-entry benchmark, the deflated
   Sharpe ratio counting every variant tried, and a final holdout that is looked at once.

Prior ML evidence: Krauss, Do, Huck (EJOR 2017). DNN/GBT/RF ensembles on S&P 500 stocks
were strong before costs, but profits declined in the late sample and were "even negative
at times".

ICT (Inner Circle Trader: order blocks, fair value gaps, liquidity sweeps, kill zones):
no peer-reviewed or independent tests found, only vendor and self-published backtests.
Definitions vary by source. The project encodes them as fixed mechanical rules and tests
them like any other setup.

## Data and broker (checked 2026-11-09)

History for training and backtests:
- BTC: Binance public 1-min klines, `data.binance.vision`, from 2017. Download tested OK.
- S&P 500 CFD: Dukascopy `USA500IDXUSD` ticks, free. 2013 and 2016 downloads tested OK.
- BTC CFD: Dukascopy `BTCUSD` ticks, 2017 download tested OK.
- Nasdaq-100 CFD: Dukascopy `USATECHIDXUSD` timed out in tests and is unconfirmed.
  Fallback: Databento CME `GLBX.MDP3` NQ/ES `ohlcv-1m` from 2010, pay-per-GB, $125 free
  credit for new accounts.

Live prices: the user trades on Revolut, whose CFDs are supplied by CMC Markets. Revolut
has no public CFD API (Revolut X's API is crypto-exchange only). Options with an API:
IG (REST + streaming) and Capital.com (REST + WebSocket, 10 req/s, 40 streamed
instruments).

CFD vs reference prices: an index CFD tracks the cash index (futures minus basis) plus the
broker's spread, so it is close to the futures price but not identical. The bot computes
levels on reference data and converts them with the live CFD−reference offset, or sends
SL/TP as distances.

EU retail CFD leverage caps (ESMA, 2018): major indices 20:1, crypto 2:1, with negative
balance protection. Higher leverage needs professional-client status.

## Leverage — what the evidence says

- Strategy 1's 25% max drawdown happened at ≤ 4x leverage with volatility targeting.
  At 20x the same path is a wiped account.
- Of 19,646 Brazilians who started day trading index futures, only 1.1% earned more than
  the minimum wage (Chague, De-Losso, Giovannetti 2019).
- Plan: size by risk-per-trade (e.g. 0.5–1% of equity to the stop), not by maximum
  leverage. The signal will include a suggested size.

## Confidence field

It won't be an invented number. Confidence = historical hit rate and average R for
similar setups (same strategy, same volatility regime, same time-of-day) from the
backtest, then tracked against live outcomes.

## Validation before real money

1. Backtest on the traded instrument with realistic spread and slippage.
2. Walk-forward / out-of-sample split; compare against random-direction entries with
   the same stop/target.
3. Deflated Sharpe ratio to account for every parameter variant we tried
   (Bailey & López de Prado 2014).
4. Paper-forward: the bot sends live signals and logs outcomes for 4–8 weeks before
   any real trade.

## Sources

- Zarattini, Aziz, Barbon — Beat the Market (SPY intraday momentum): https://www.sfi.ch/de/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy
- Zarattini, Barbon, Aziz — Can Day Trading Really Be Profitable? (ORB): https://papers.ssrn.com/abstract=4416622
- ORB replication on index CFDs, net of costs: https://www.mql5.com/en/blogs/post/776235
- Gao, Han, Li, Zhou — Market intraday momentum (JFE 2018): https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414
- Shen, Urquhart, Wang — Bitcoin intraday time-series momentum: https://centaur.reading.ac.uk/100181
- Concretum — Seasonality in Bitcoin intraday trend trading: https://concretumgroup.com/seasonality-in-bitcoin-intraday-trend-trading/
- Zarattini, Pagani, Barbon — Catching Crypto Trends: https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/
- Moskowitz, Ooi, Pedersen — Time series momentum: https://papers.ssrn.com/abstract=2089463
- Moreira, Muir — Volatility-managed portfolios: https://amoreira2.github.io/alan-moreira.github.io/VolPortfolios_published.pdf
- Bailey, López de Prado — Deflated Sharpe ratio: https://papers.ssrn.com/abstract=2460551
- Chague et al. — Day trading for a living?: https://econpapers.repec.org/RePEc:spa:wpaper:2019wpecon47
- Telegram bot limits: https://core.telegram.org/bots/faq
- Binance market streams: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- Alpaca market data (free IEX feed): https://docs.alpaca.markets/docs/about-market-data-api
- Park & Irwin — What do we know about the profitability of technical analysis? (2007): https://ideas.repec.org/a/bla/jecsur/v21y2007i4p786-826.html
- López de Prado — Advances in Financial Machine Learning (2018), triple barrier / meta-labeling / purged CV (summary): https://www.quantt.co.uk/resources/purged-cross-validation
- Krauss, Do, Huck — DNN, GBT, RF statistical arbitrage on the S&P 500 (EJOR 2017): https://econpapers.repec.org/RePEc:eee:ejores:v:259:y:2017:i:2:p:689-702
- ICT backtests (vendor/self-published, unverified): https://backtrex.com/en/blog/liquidity-sweep-strategy-backtest-results
- ESMA CFD product intervention (leverage caps): https://www.esma.europa.eu/node/85445
- Databento pricing / CME history: https://databento.com/pricing
- Capital.com API: https://open-api.capital.com/
- IG API: https://www.ig.com/en/trading-platforms/trading-apis/how-to-use-ig-api
- CMC Markets as Revolut's CFD partner: https://www.financemagnates.com/executives/neobanks-want-trading-were-the-partner-that-delivers-it-cmc-markets-uk-head/
