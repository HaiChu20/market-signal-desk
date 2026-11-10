# Trading method families: evidence and fit for this project (2026-11-10)

Five parallel literature reviews were combined here: price-structure TA, indicators and
volume, quant/systematic, fundamental/sentiment, and machine learning. The goal is to show
what each family is, what independent evidence says about it, and how it can feed a model
that sends **buy/short, entry, SL, TP and confidence**. The model reads 1-minute candles,
places SL and TP at meaningful levels (for example BTC at 86, SL at the 84 support, TP at 90),
and has **no fixed holding time**.

Evidence labels used below:
- ✅ independent peer-reviewed support;
- ⚠️ mixed results, weak evidence, or only works as a filter;
- ❌ no independent support, or fails after costs.

Every method is **ML-eligible**. A method can supply inputs, candidate levels or regime
information to a learned model; it does not have to be a fixed rule. The hard constraint is
**causality**: at decision time the model sees only data that existed then.

---

## 1. Two facts that shape everything

### 1.1 Costs depend on the timeframe, not the method
| Instrument | Spread | Spread as % of a typical stop: 1-min setup | 1-hour setup | 4-hour/daily setup |
|---|---|---|---|---|
| Nasdaq CFD | ~1–1.5 pt | 20–50% | ~2–4% | <1% |
| S&P 500 CFD | ~0.5 pt | similar | similar | <1% |
| BTC CFD | $50–130 (5–13 bp) | very high | 10–25% of a 1h range | a few % |

Our own tests matched the literature. Simple setups on 1–5 min bars (S/R fade and breakout,
ICT sweep+FVG) had about zero edge before costs and negative edge after. **Decisions can
still use 1-min data,** but the setups should live on 15m–4h structure, with holding times of
hours to days. Manual execution also adds a 30–120 s delay, which by itself rules out
minute-scale targets.

### 1.2 Choosing SL/TP cannot create an edge on its own
If price has no predictable drift (a "martingale"), then
P(TP before SL) = SL distance ÷ (SL distance + TP distance).
That makes **every** SL/TP pair worth 0R before costs and negative after costs. A 2R target
wins about 33% of the time purely by geometry, and a 0.5R target wins about 67%. A high
win rate is not an edge (Krause & Fairbank 2020; Lo & Remorov 2017). A placement model only
adds value where price **departs** from this baseline, through momentum, reversal at levels,
or order clustering. Our earlier model (AUC 0.57) mostly relearned this geometry.

**Consequence for ML:** the model must be measured, and preferably trained, as **skill over the
geometric baseline**, not as raw hit probability.

---

## 2. Family 1: Technical analysis (price structure)

| Method | Evidence | Can it be made causal? | Natural SL/TP | Role for us |
|---|---|---|---|---|
| Support/resistance + round numbers | ✅ modest. Osler 2000/2003 (NY Fed, FX): published levels and round numbers predicted where intraday trends stopped better than 10,000 random level sets. Stops cluster just beyond levels, take-profits at them. Index barrier evidence is mixed; BTC round-number barriers were found by Lee & Seong 2019. | Yes. Swing pivots are confirmed after k bars (use the confirmation time). Levels are clustered within 0.25 ATR; round numbers are 100 (NQ), 50 (SPX) and 1,000 (BTC). | SL beyond level + 0.2–0.5 ATR; TP at next level | **Core level source** for SL/TP candidates and features. Not a standalone 1-min signal (already failed). |
| Supply & demand zones | ❌ none peer-reviewed. It is S/R plus a momentum condition. | Yes. Base of N small bars, then an impulse of more than X ATR; known only after the impulse. | Zone edge / opposite zone | Feature (merged into levels) |
| Trendlines & channels | ❌ no peer-reviewed test | Hard: many arbitrary choices, and pivots are easy to back-date | Beyond line / parallel line | Low priority. A regression-channel feature at most. |
| Market structure (HH/HL, BOS/CHoCH) + Dow theory | ✅ the trend/range-break family. Brock-Lakonishok-LeBaron 1992; Brown-Goetzmann-Kumar 1998 (Dow); crypto rule survival in Hudson & Urquhart 2021. The edge is fragile after data-snooping corrections (Sullivan-Timmermann-White 1999; Bajgrowicz-Scaillet 2012). | Yes, with a causal ZigZag/fractal. Standard ZigZags repaint. | SL below the last confirmed HL; TP at the prior swing or a measured move | **Core:** trend state on 1h/4h, pullback entries |
| Chart patterns (H&S, double top, flags, ...) | ⚠️ Lo-Mamaysky-Wang 2000: patterns carry "incremental information", not proven profit. Savin et al. 2007: H&S modestly useful as part of a strategy. Bulkowski's figures are hindsight-identified. | Yes, via pivot sequences. The pattern exists only once its last pivot is confirmed. | Beyond the pattern extreme / measured move | Filter feature (H&S, double top/bottom on 1h/4h) |
| Candlestick patterns | ❌ Marshall-Young-Rose 2006: no value on DJIA stocks. Intraday futures also negative. | Trivial | Wick extreme | Entry-trigger feature only |
| Al Brooks price action | ❌ none peer-reviewed | Mostly discretionary | Signal-bar extreme | Covered by structure and pullback features |
| Fibonacci | ❌ Batchelor & Ramyar 2006; Tsinaslanidis 2022: Fib levels are no better than other levels | Yes, after the swing is confirmed | 78.6% / extensions | A plain "pullback depth %" feature instead |
| SMC/ICT (OB, FVG, sweep, killzone, OTE) | ❌ none peer-reviewed. A sweep resembles Osler's stop cascades, and killzones resemble time-of-day effects. **Our test:** small gross edge on BTC only, eaten by costs. | Yes (FVG known at the 3rd bar close; OB only after the break of structure) | Beyond sweep wick / opposite liquidity | Features: sweep-and-reclaim on BTC 1h/4h; time-of-day |
| Wyckoff | ❌ none. The spring is the same as a sweep. | Only the spring | — | Covered by the sweep feature |
| Elliott, harmonics, Gann | ❌ no rigorous support. Wave counts are relabelled with hindsight. | Not reliably | — | **Skip.** A raw-candle sequence model can learn any real structure without the labels. |

## 3. Family 1b: Indicators and volume

| Method | Evidence | Role for us |
|---|---|---|
| Moving averages / crossovers (50/200) | ⚠️ long-horizon trend timing: Neely-Rapach-Tu-Zhou 2014 (monthly); Hsu & Kuan 2005 (young markets). Fails after snooping or costs on S&P (STW 1999, Bajgrowicz-Scaillet 2012). BTC: Detzel 2021 positive, Hudson-Urquhart 2021 out-of-sample negative. | Regime feature (price vs 200-day MA); BTC 4h/daily trend feature |
| RSI(2) short pullback (Connors) | ⚠️ practitioner backtests only. Fits the documented post-2000 index reversal (section 5). | **Candidate** on NQ/SPX daily, long-only with trend filter |
| MACD, Stochastic, Ichimoku | ❌ duplicate MA/RSI/Donchian; no independent value | Skip as signals (fine as model inputs, low expectation) |
| Bollinger Bands | ⚠️ reversion fails after costs (Lento 2007). Bandwidth works as a volatility regime measure. | Volatility-regime feature |
| ATR / Donchian / Keltner | ✅ the trend family: Hurst-Ooi-Pedersen (67 markets since 1880); Donchian on BTC. | ATR for stop/size scaling everywhere; Donchian trend feature |
| VWAP / anchored VWAP | ⚠️ Gao et al. 2018 intraday momentum ✅. VWAP-trail strategy decayed in 2025–26 (our test). No peer-reviewed VWAP signal study. Index CFD VWAP uses **tick volume**. | Level source (VWAP, anchored VWAP from confirmed pivots) and context feature |
| Volume / market profile (POC, value area) | ❌ no peer-reviewed predictive tests | Level source to test (prior POC/VAH/VAL) |
| Order flow (delta, OFI, footprint, DOM) | ✅ microstructure: Cont-Kukanov-Stoikov 2014 (contemporaneous); Cont-Cucuringu-Zhang 2023. A 2026 Binance study found order imbalance predicts BTC over 4–12 h (costs not tested). | **BTC only:** Binance klines include taker-buy volume; aggTrades give the trade side. Impossible for index CFDs (no trade side, no order book). |

## 4. Family 2: Fundamental and news

| Item | Evidence | Role for us |
|---|---|---|
| Scheduled macro releases (CPI, NFP, FOMC, GDP, PMI) | ✅ Prices adjust within ~1 second (Takahashi 2025; ABDV 2003/2007). The sign of the reaction depends on the business cycle. ~40% of the move can happen in the 30 min before the release (Kurov 2019). Announcement days carry most of the equity premium (Savor-Wilson 2013), a daily risk premium rather than a timing edge. The pre-FOMC drift (Lucca-Moench 2015) has been ~gone since 2015. | **Blackout filter:** no new signals from T−15 to T+30 min (FOMC 14:00–15:00 ET). Event-day volatility switch. Test "post-event at T+5 min" ourselves; the literature is unsettled. |
| News / Twitter text sentiment | ⚠️ Tetlock 2007: noise that reverts within a week. Crypto Twitter evidence is weak and bot-polluted. Retail latency removes any headline edge. | Skip (X API is paid). A volatility-spike "unscheduled shock" flag instead. |
| Earnings (megacaps = >50% of NDX) | ⚠️ no index-level timing edge; large gap risk after hours | **Filter:** no new NAS100 signals around top-10 megacap reports |
| Economic-calendar data | FRED/ALFRED give release dates. Times come from BLS (08:30 ET), BEA, ISM (10:00), Fed (14:00). Consensus/surprise data is paid. | Build a free CSV calendar. Use the first 1–5 min move as the "surprise" proxy. |

## 5. Family 3: Quantitative / systematic

| Family | Evidence | Role for us |
|---|---|---|
| Trend following / TSMOM | ✅ MOP 2012, HOP (since 1880, net Sharpe ~0.77), Lempérière 2014. Strongest at monthly horizons and across 50+ markets; per-asset Sharpe ~0.3–0.5. CTAs had a poor 2025. Our BTC Donchian failed in 2025–26. | Regime/bias feature (daily/4h trend); not standalone |
| Intraday momentum | ✅ Gao 2018; Baltussen et al. 2021 (60+ futures since 1974), which links it to dealer **gamma** hedging. In S&P it works mainly when gamma is negative. Our Noise Area decayed from 2023, plausibly from 0DTE-driven long gamma (unverified). | Conditional feature: prior-day loss, high realized vol, index below its 20-day mean |
| **Short-term index mean reversion (1–5 days)** | ✅ Baltussen-van Bekkum-Da 2018: S&P daily autocorrelation turned **negative** after ~2000 (ETF/futures arbitrage). Fading the 5-day mean gives Sharpe ~0.67 since 1999, stronger in high-vol periods. RSI(2) practitioner results are consistent. 1–5 **minute** reversal is mostly bid-ask bounce (Heston-Korajczyk-Sadka 2010). | **Top candidate:** edge per trade (30–60 bp) is far above the spread |
| Opening-range / volatility breakouts | ⚠️ ORB gross edge real, net ≈ 0 on CFDs (independent replication 2015–26) | Feature only (NR4/NR7 + trend context) |
| Seasonality / time of day | ⚠️ turn-of-month and pre-FOMC effects largely gone. BTC hour/day effects show up in volatility, not returns. | Confidence/volatility features only |
| Pairs / stat-arb (NQ–SPX, BTC–ETH) | ❌ decayed (Gatev 2006 → Do-Faff 2010). Two spreads plus manual two-leg execution make it unsuitable. | Skip |
| Volatility targeting / sizing | ✅ Harvey et al. 2018 (smoother risk, better tails). Moreira-Muir gains fragile out-of-sample (Cederburg 2020). | **Always:** ATR stops + vol-scaled size + ESMA caps |

## 6. Family 4: Sentiment and positioning

| Indicator | Evidence | Role for us |
|---|---|---|
| VIX level, VIX/VIX3M term structure | ✅ as a regime variable: intraday momentum is stronger in high vol, backwardation predicts dispersion. Free daily history (FRED, Cboe). | **Regime feature:** size, stop width, trend vs reversion. Our own realized vol is a lag-free substitute. |
| BTC funding rate + open interest | ⚠️ BIS "Crypto Carry" (2023/25): high carry predicts crashes. Funding is an analogue. Free Binance funding history since 2019. | **BTC crowding feature/filter** |
| COT, AAII, put/call, CNN Fear & Greed | ⚠️/❌ too slow, decayed (AAII), non-public information (Pan-Poteshman), or duplicative | Skip |
| Broker retail positioning (IG) | No independent test; no history | Log forward only |
| BTC exchange flows, ETF flows, Google Trends | ❌/⚠️ flows follow price. Trends (Liu-Tsyvinski) is a weekly effect with look-ahead risk. | Skip / low priority |

---

## 7. ML across all families: how the "learn the SL/TP" idea works

### 7.1 What the evidence says
- The strongest deep-learning results are **cross-sectional** (Jiang-Kelly-Xiu 2023 chart CNNs; Gu-Kelly-Xiu 2020), use **diversified daily futures** (Deep Momentum Networks), or use **order books** (DeepLOB, Sirignano-Cont).
- **Single-instrument intraday timing is mostly null after costs.** MNQ 5-min LSTM/GBM 2021–25 was at chance (2026). BTC 1–60 min was negative after costs (Jaquart 2021). Fischer-Krauss LSTM was ~0 after 2010.
- **Pooling many instruments helps** (Sirignano-Cont "universal" model). Finance-specific pretraining beats generic time-series foundation models (Rahimikia 2025). Kronos (12B candles) is promising but self-reported.
- **Reinforcement learning:** mostly fails to replicate (seed variance, simulator overfitting, unrealistic fills). It only helps as fine-tuning after a supervised model (Wang et al. 2026).

### 7.2 Architecture for this project
1. **Candidate levels (causal)** from every family:
   - swing S/R (confirmed pivots), round numbers, prior day/week high/low;
   - VWAP / anchored VWAP, prior POC/VAH/VAL;
   - zone edges, sweep extremes;
   - ATR multiples as a fallback grid.
2. **Encoder.** A pooled multi-instrument model reads multi-timeframe windows (1m/15m/1h/4h) of OHLC, spread and volume channels, plus family features:
   - structure and trend state;
   - indicators;
   - BTC taker-flow imbalance and funding;
   - VIX/realized-vol regime;
   - event calendar; time of day.
   Start with gradient boosting on features. Then try a 1D-CNN or transformer, with optional pretraining on many Dukascopy instruments (indices, FX, gold, ETH) on Roihu. Kronos embeddings are a cheap extra feature.
3. **Multi-barrier head.** For an up-level × down-level grid (e.g. 8×8 in ATR units, snapped to the nearest structural level), predict P(TP first) **as an offset over the geometric baseline**. Apply monotonicity constraints: P(TP first) rises as the SL moves further away and falls as the TP moves further away. A competing-risks hazard head is the alternative; it also gives time-to-hit.
4. **Decision:**
   - expected R = p·TP_R − (1−p)·1 − spread_R − financing_R;
   - pick the pair with the best **shrunk** edge (guards against the winner's curse);
   - require positive edge on neighbouring pairs too;
   - signal only above a threshold;
   - confidence = calibrated p.
5. **Calibration:** isotonic regression on a later, time-ordered fold; reliability checked per year and per volatility regime.
6. **Execution realism:**
   - bid/ask fills;
   - stop slippage and weekend/overnight gaps;
   - CFD financing;
   - a simulated **30–120 s manual entry delay**.

### 7.3 Pitfalls to guard against
- **Leakage:** pivots must be used only from their confirmation time; prior-day levels need correct session boundaries; normalisation must be rolling only; overlapping labels must be purged with an embargo. Also use the truncation test from this project (`assert_causal`).
- **Selection bias from big searches:**
  - use CPCV for model selection, plus walk-forward;
  - log every trial;
  - report the deflated Sharpe ratio and PBO.
  More GPU compute makes this risk **worse**.
- **Decay:** predictors earn 26% less out-of-sample and 58% less after publication (McLean-Pontiff 2016).
- **Sample size:** with trade-R standard deviation of ~1.2, a deflated t ≥ 3 needs **~1,300 trades at +0.10R** or **~5,200 trades at +0.05R**. The binding constraint is independent samples, not compute.
- **Test windows:** 2025–26 has already been viewed by earlier strategies, so it is only semi-clean. **Forward paper trading of at least 3 months** is the real test.

### 7.4 What counts as success
- Out-of-sample Brier skill > 0 against the geometric baseline, stable across years.
- Net ≥ +0.05–0.10R per trade over ≥1,000 out-of-sample + forward trades, with deflated t ≥ 3.
- Beats a random-direction benchmark with the same SL/TP policy, and beats a simple vol-scaled trend benchmark.

---

## 8. What fits this project now: ranked

1. **Level-aware multi-barrier ML model** (section 7.2) on NQ, SPX and BTC: 1-min inputs, setups on 15m–4h structure, holds of hours to days, SL/TP snapped to structural levels. Features come from every family. This is the user's design, and the evidence supports it as the best-founded version.
2. **Index 1–5 day reversal** (fade the 5-day mean or RSI(2) inside the 200-day trend; NQ/SPX). It is the strongest *simple* candidate (Baltussen et al. 2018) and serves as both a standalone benchmark and a model feature. Main risk: crash regimes and overnight gaps.
3. **Trend structure on 1h/4h** (causal HH/HL, pullback to the broken swing, SL beyond the last confirmed swing). Trend evidence is the broadest; structural stops fit the signal format.
4. **BTC-specific inputs:** taker-flow imbalance (Binance), funding crowding, sweep-and-reclaim at round numbers/swings on 1h/4h. BTC is less efficient and the only market with real trade-side data.
5. **Filters for everything:**
   - event blackout (CPI/NFP/FOMC; megacap earnings for NAS100);
   - volatility regime (realized vol, VIX, VIX/VIX3M);
   - ATR stops and vol-scaled size under the ESMA caps.

**Skip:** Elliott, harmonics, Gann, standalone candlesticks, MACD/Stochastic/Ichimoku signals, pairs trading, text sentiment, COT/AAII/put-call, 1–5 min scalps, RL from scratch.

### Data to add
- Binance kline taker-buy volume (already in the files we download; the loader currently drops it) and/or aggTrades.
- Binance funding-rate history (free, from 2019).
- A free macro calendar: BLS/BEA/ISM/Fed schedules plus FRED release dates.
- VIX and VIX3M daily (FRED/Cboe).
- Megacap earnings dates.
- Optionally more Dukascopy instruments for pooled pretraining.

---

## 9. Key sources
- Osler 2000 (S/R levels): https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.pdf
- Osler 2003 (stop/TP clustering): https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf
- Lo, Mamaysky & Wang 2000: https://www.nber.org/system/files/working_papers/w7613/w7613.pdf
- Brock, Lakonishok & LeBaron 1992: https://econpapers.repec.org/RePEc:bla:jfinan:v:47:y:1992:i:5:p:1731-64
- Sullivan, Timmermann & White 1999: https://econpapers.repec.org/RePEc:bla:jfinan:v:54:y:1999:i:5:p:1647-1691
- Bajgrowicz & Scaillet 2012: https://econpapers.repec.org/RePEc:eee:jfinec:v:106:y:2012:i:3:p:473-491
- Marshall, Young & Rose 2006 (candlesticks): https://econpapers.repec.org/RePEc:eee:jbfina:v:30:y:2006:i:8:p:2303-2323
- Marshall, Cahan & Cahan 2008 (7,846 intraday rules, none survive): https://ideas.repec.org/a/eee/empfin/v15y2008i2p199-210.html
- Hudson & Urquhart 2021 (crypto TA): https://centaur.reading.ac.uk/85715
- Batchelor & Ramyar 2006 (Fibonacci): https://openaccess.city.ac.uk/16276/
- Hurst, Ooi & Pedersen (trend since 1880): https://fairmodel.econ.yale.edu/ec439/hurst.pdf
- Moskowitz, Ooi & Pedersen 2012: https://fairmodel.econ.yale.edu/ec439/jpde.pdf
- Baltussen, van Bekkum & Da 2018 (index reversal): https://personal.eur.nl/vanbekkum/2018%20JFE%20BaltussenVanBekkumDa.pdf
- Baltussen, Da, Lammers & Martens 2021 (gamma, intraday momentum): https://www3.nd.edu/~zda/intramom.pdf
- Gao, Han, Li & Zhou 2018: https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414
- Heston, Korajczyk & Sadka 2010: https://arxiv.org/pdf/1005.3535.pdf
- Harvey et al. 2018 (vol targeting): https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf
- Cont, Kukanov & Stoikov 2014 (OFI): https://arxiv.org/abs/1011.6402
- Binance order-imbalance 4–12h (2026): https://arxiv.org/abs/2607.09426
- Savor & Wilson 2013: https://ideas.repec.org/a/cup/jfinqa/v48y2013i02p343-375_00.html
- Kurov, Wolfe & Gilbert (pre-FOMC drift gone): https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf
- Andersen, Bollerslev, Diebold & Vega 2007: https://www.federalreserve.gov/pubs/ifdp/2006/871/ifdp871.htm
- BIS Crypto Carry: https://www.bis.org/publ/work1087.htm
- Jiang, Kelly & Xiu 2023 (chart CNN): https://papers.ssrn.com/abstract=3756587
- Gu, Kelly & Xiu 2020: https://www.nber.org/papers/w25398.pdf
- Sirignano & Cont 2019: https://arxiv.org/abs/1803.06917
- Deep Momentum Networks: https://arxiv.org/abs/1904.04912
- Kronos (candle foundation model): https://arxiv.org/abs/2508.02739
- Rahimikia et al. 2025 (finance pretraining): https://arxiv.org/abs/2511.18578
- MNQ 5-min LSTM/GBM null result: https://arxiv.org/abs/2605.17724
- Krause & Fairbank (baseline win rates): https://researchportal.bath.ac.uk/en/publications/baseline-win-rates-for-neural-network-based-trading-algorithms/
- Lo & Remorov 2017 (stop-loss): https://dspace.mit.edu/handle/1721.1/107017
- Gort et al. 2022 (DRL overfitting): https://arxiv.org/abs/2209.05559
- Bailey et al. (PBO): https://papers.ssrn.com/abstract=2326253
- CPCV comparison 2024: https://doi.org/10.1016/j.knosys.2024.112477
- McLean & Pontiff 2016: https://www.gwern.net/doc/economics/2016-mclean.pdf
- ORB CFD replication (net ≈ 0): https://www.mql5.com/en/blogs/post/776235

Full per-family briefings (with ~120 sources) came from the research agents. Items they could
not verify against full texts are flagged as such in their reports.
