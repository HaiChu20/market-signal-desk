# Predictive Trading Models — Research Findings by Category

A working reference of what's actually been tested, on what data, with what architecture, and what the reported result was. Use this to decide what to rebuild/reproduce first. Every row below is paraphrased from the cited source — go to the link for exact numbers/methodology before relying on anything.

**How to read the "Caveat" column**: this is the single most important column. Backtest Sharpe/return numbers routinely collapse once realistic transaction costs, slippage, and out-of-sample regimes are applied. Treat every number here as "promising, needs reproduction" rather than "proven."

---

## 1. Tree Ensembles (XGBoost / LightGBM / CatBoost / Random Forest)

**Architecture type**: Gradient-boosted decision trees (and Random Forest) over hand-engineered tabular features (technical indicators, factor exposures, price/volume ratios). No native sequence modeling — temporal info has to be injected via lag features.

| Finding | Market / Data | Metric reported | Caveat | Source |
|---|---|---|---|---|
| Multi-factor stock selection (RF, XGBoost, LightGBM, LightGBM-Bayes) on 5 factor categories (valuation, profit, scale, risk, momentum) | China CSI 300, daily, 2013 onward | LightGBM-Bayes portfolio: **19.1% annualized return, 0.96 Sharpe** vs. CSI 300 index's 9.6% / 0.24 | Single market, single period; no explicit transaction cost modeling mentioned | [ScienceDirect paper](https://www.sciencedirect.com/science/article/pii/S1877050922020130/pdf) |
| LightGBM vs OLS, long-short factor strategy | Chinese A-shares | LightGBM long-short: **2.63% monthly return, 1.77 Sharpe** vs OLS 1.82% / 1.09–1.11 | Liquidity/volatility factors dominate — may not transfer to other factor sets | [ACM DL paper](https://dl.acm.org/doi/10.1145/3727353.3727490) |
| XGBoost vs OLS, long-short strategy | Chinese A-shares | XGBoost long-short: **2.73% monthly return, 1.76 annualized Sharpe** vs OLS 2.01% / 1.17 | Same market as above — results may be correlated, not independent confirmation | [ACM DL paper](https://dl.acm.org/doi/10.1145/3724154.3724237) |
| Regime-aware LightGBM pipeline with HMM regime detection, SHAP explainability, walk-forward validation, block-bootstrap + Deflated Sharpe Ratio significance testing | 51 NASDAQ-100 constituents, 2015–2026 | **Sharpe 1.18** (95% CI [0.53, 1.84]); outperformed XGBoost (0.795 Sharpe) and 3 other baselines; strategy stays profitable even at 5× baseline transaction costs | Most methodologically rigorous paper in this list (uses DSR to correct for multiple testing) — good template to copy | [MDPI Electronics 2026](https://www.mdpi.com/2079-9292/15/6/1334) |
| LightGBM vs XGBoost vs Random Forest, tri-class (buy/sell/hold) signals | BTC/USD daily, 2015–2024, backtested Jan 2023–Jun 2024 | LightGBM: **+366% cumulative return, 2.64 Sharpe, 3.86 Sortino**, beat buy-and-hold (264% / 2.20); XGBoost actually *lost* money (-46%, -0.70 Sharpe) | Shows model choice *within* tree family matters a lot — don't assume all boosters perform alike | [AISeL paper](https://aisel.aisnet.org/cgi/viewcontent.cgi?article=1715&context=isd2014) |
| XGBoost vs CatBoost vs LightGBM vs linear vs NN, daily excess-return forecasting, decile long-short portfolios | US stocks, 2001–2023 (18M+ obs, ~10,000 securities) | CatBoost best: **46.50% annualized return, 6.79 Sharpe** (window=252 days); XGBoost 6.53 Sharpe max; LightGBM 6.12 Sharpe max | **No transaction costs included** — daily rebalancing with zero costs is unrealistic; treat as upper bound, not achievable return | [arXiv 2511.18578](https://arxiv.org/pdf/2511.18578) |

**Takeaway**: Most reproducible, most consistently positive category. Realistic expectation band: monthly returns ~2–3%, Sharpe ~1–2 with costs included. The outlier 46% backtest number above is gross-of-cost on a huge dataset — don't anchor your personal expectations to it.

---

## 2. Deep Sequence Models (LSTM / GRU / Transformer variants)

**Architecture type**: Recurrent (LSTM/GRU) or attention-based (Transformer/Autoformer/Informer) models that consume raw or normalized price sequences directly, learning temporal dependencies instead of relying on hand-crafted lag features.

| Finding | Market / Data | Metric reported | Caveat | Source |
|---|---|---|---|---|
| Momentum Transformer (attention + change-point detection module) vs LSTM-based Deep Momentum Network | Futures/cross-asset, 1995–2020 and 2015–2020 subperiods | Transformer **Sharpe improved 50% over LSTM (1995–2020)** and **109% (2015–2020)**; CPD module added further 17% in 2015–2020 | Five repeated runs, median reported — good practice, but still single-dataset | [arXiv 2112.08534](https://arxiv.org/pdf/2112.08534), code: [kieranjwood/trading-momentum-transformer](https://github.com/kieranjwood/trading-momentum-transformer) |
| Transformer vs LSTM vs CNN vs MLP, long-short portfolio | S&P 500 vs NASDAQ | Transformer wins on S&P 500 (highest return/Sharpe, lowest drawdown); **LSTM wins on NASDAQ instead** | Direct evidence that "best architecture" is market-dependent — no universal winner | [arXiv 2411.13555](https://arxiv.org/pdf/2411.13555) |
| Transformer vs LSTM, cross-asset futures timing, net of transaction costs | Liquid futures | Pre-cost: Transformer 0.55 vs LSTM 0.50 Sharpe (close). **Post-cost (2bp): LSTM collapses to 0.33, Transformer barely moves to 0.54** (lower turnover) | Turnover/cost-sensitivity matters more than raw architecture choice — critical lesson for your own cost modeling | [arXiv 2607.00475](https://arxiv.org/pdf/2607.00475) |
| LSTM vs Transformer-based models (Autoformer, vanilla Transformer) in simulated electronic/HFT trading | Limit order book data | **LSTm-based models outperformed Transformer-based models** in trading simulation despite Transformer having better classification metrics | Classification accuracy ≠ trading profitability — a recurring theme across this whole research area | [arXiv 2309.11400](https://arxiv.org/pdf/2309.11400) |
| Methodological warning: backtest return-compounding bug found in prior financial-Transformer literature | N/A (meta-finding) | Bug **inflated reported Sharpe ratios by a factor of √5** before correction | Reminds you to audit your own backtest compounding logic before trusting any Sharpe number, including your own | [arXiv 2606.29347](https://arxiv.org/html/2606.29347) |

**Takeaway**: No consistent architecture winner (Transformer vs LSTM flips depending on market and cost assumptions). The one consistent lesson: **low-turnover strategies survive transaction costs much better regardless of architecture** — design for low turnover if you go this route.

---

## 3. Generic Time-Series Foundation Models, Pre-trained/Fine-tuned on Your Own Financial Data

**Architecture type**: Transformer-based foundation models (TimesFM = decoder-only continuous embeddings; Chronos = decoder/encoder-decoder with discrete tokenization) originally pretrained on generic time series, then either fine-tuned or pretrained from scratch specifically on financial return data.

| Finding | Model / Data | Metric reported | Caveat | Source |
|---|---|---|---|---|
| TimesFM fine-tuned on financial data, market-neutral long-horizon strategy, mock trading | S&P 500 + other markets, 2023 onward | **Sharpe up to 1.68 on S&P 500**; the only tested model to achieve positive returns on every market tested | Explicitly weaker on **currencies and crypto** — underperformed a simple AR(1) model there | [Preferred Networks blog](https://tech.preferred.jp/en/blog/timesfm/), paper: [arXiv 2412.09880](https://arxiv.org/pdf/2412.09880) |
| Chronos zero-shot + fine-tuned, statistical arbitrage via PCA residuals | US equities, 2002–2016 (15-year window) | Zero-shot gross Sharpe **3.17** (α=0.3) | **Collapses to negative Sharpe (-1.49) after a 3bp trading cost** — single clearest cost-collapse example in this whole research set | [arXiv 2412.09394](https://arxiv.org/pdf/2412.09394) |
| Chronos (tiny/mini/small/base/large) + TimesFM (v1, v2), pretrained from scratch each year on financial data only (no look-ahead), vs CatBoost benchmark | US stocks, 2001–2023 expanding window | Chronos (small) from scratch: **36.84% annualized return, 5.42 Sharpe** (window=512); TimesFM (20M) from scratch: 30.36% / 3.66 — both closing most of the gap to CatBoost's 46.50% / 6.79 | Zero-shot (no from-scratch training) versions of the same models performed far worse — the *domain-specific pretraining* is what did the work, not the architecture | [arXiv 2511.18578](https://arxiv.org/pdf/2511.18578) |
| Chronos-Bolt on daily futures returns vs LightGBM | Futures, daily bars, 1-day and 5-day holding horizons | Chronos-Bolt: **+1.38 / +1.30 gross Sharpe** across horizons, beating LightGBM's intraday +0.69 | Different holding horizons/timeframes compared (not apples-to-apples with the LightGBM number) — worth re-running fair side-by-side yourself | [Quantai Lab substack](https://quantailab.substack.com/p/do-time-series-foundation-models) |
| Broad caution: 43 public foundation models tested across ~117,000 financial series (FinVerse benchmark) | Mixed global financial series | Strong generic time-series forecasting rank **does not reliably predict** financial forecasting usefulness | Author-run preprint, not yet widely replicated — but aligns with everything else in this table | [arXiv 2609.04917](https://arxiv.org/pdf/2609.04917) |

**Takeaway**: This is the most promising *frontier* category — from-scratch or fine-tuned financial pretraining can close the gap to (or beat) tree ensembles, but (a) it only works if you actually have enough financial data to pretrain/fine-tune meaningfully, (b) results are asset-class dependent (equities > crypto/FX in the evidence found), and (c) gross returns are highly cost-sensitive.

---

## 4. Finance-Native Foundation Model (Kronos)

**Architecture type**: Decoder-only transformer, purpose-built and pretrained from scratch on financial candlestick (OHLCVA) sequences specifically — not adapted from a generic time-series or language model. Uses a specialized tokenizer for K-line data.

| Finding | Market / Data | Metric reported | Caveat | Source |
|---|---|---|---|---|
| Original paper's own evaluation: price forecasting, volatility, synthetic data generation, long-only top-K investment simulation | 45+ global exchanges (pretraining); **Chinese A-shares (investment simulation)** | **93% RankIC improvement** over best prior TSFM baseline; 9% lower volatility-forecast MAE; 22% better synthetic data fidelity; best AER + Information Ratio in A-share simulation among all baselines | Self-reported by the model's authors — treat as upper bound until independently reproduced | [arXiv 2508.02739](https://arxiv.org/html/2508.02739v1), code: [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos) |
| Independent third-party breakdown of the above paper's own numbers | Chinese A-shares (CSI 300, CSI 800) | Kronos-small: 17.89% annual excess return, IR 1.42. Kronos-base: 18.89%, IR 1.52. Kronos-large: 20.84%, IR 1.65 (21.93% on CSI 300, 19.74% on CSI 800) | Still describing the *same* in-paper Chinese A-share results, just itemized by model size | [AI Driven Trading substack](https://aidriventrading.substack.com/p/kronos-ai-and-the-real-test-promise) |
| **Independent out-of-sample test, direction accuracy + volatility ranking** | 13 large US stocks (direction test); separate volatility comparison | Direction accuracy only **54.6%** (barely above coin-flip); in a volatility-forecasting ranking, Kronos **ranked last**, with errors 2.4–2.6× higher than a simple HAR-RV model | Clear evidence the A-share result does **not** automatically transfer to US equities | Same substack as above |
| **Independent out-of-sample test on forex/CFDs** | 25 forex and CFD pairs, post-training-cutoff price history only | **No usable directional signal found** out of the box; larger 102M-parameter model performed no better than the smaller one | Most important caveat in this whole document if you plan to trade FX — the paper's home-turf results clearly don't generalize here | [Medium: Testing Kronos on Forex/CFDs](https://florinelchis.medium.com/testing-kronos-price-prediction-model-on-forex-and-cfds-b9d4d0e76e3c) |
| Built-in fine-tuning pipeline (via Microsoft Qlib) for adapting Kronos to your own market/data | Any market with OHLCV data you supply | N/A — tooling exists, not pre-validated for every market | Repo README itself flags that a "high-fidelity backtest should meticulously model transaction costs, slippage, and market impact" before trusting results | [Kronos GitHub — finetuning section](https://github.com/shiyu-coder/Kronos#-finetuning-on-your-own-data-a-share-market-example) |

**Takeaway**: Strong, specifically-validated results on the exact market it was tuned/tested on (Chinese A-shares) — but the independent replications on US equities and forex found weak-to-no edge out of the box. This strongly suggests: **don't trust Kronos zero-shot outside Chinese equities** — fine-tune it on your own market's data first (the repo has tooling for this) and benchmark it against your own tree-ensemble baseline before relying on it.

---

## 5. A+ Tier — Hybrid / Ensemble Approaches (combining model families)

**Architecture type**: Not a single model — a *combination* of model families (tree + neural net + random forest, or tree + tabular deep learning, or multiple RL agents), aggregated by averaging, rank-aggregation, or performance-based selection. The evidence below is why this tier earns the higher grade: combining uncorrelated model errors consistently beat every individual constituent model in its own paper.

| Finding | Architecture combined | Market / Data | Metric reported | Caveat | Source |
|---|---|---|---|---|---|
| **Krauss, Do & Huck (2017)** — the foundational paper in this space, published in *European Journal of Operational Research*, 174+ citations | Equal-weighted ensemble of 1 deep neural network + 1 gradient-boosted tree + 1 random forest | S&P 500 constituents, daily, **Dec 1992 – Oct 2015** (23-year out-of-sample period) | Ensemble: **0.45% return/day pre-cost** (vs 0.33% DNN, 0.37% GBT, 0.43% RAF individually); **73% annualized return post-transaction-costs** (vs 27–67% for individual models); statistically **significant daily alpha of 0.14–0.24%** depending on factor model used | Pre-2015 data, and statistical arbitrage edges like this tend to decay over time as more capital chases them (the paper itself discusses this decay) | [ScienceDirect / EJOR](https://www.sciencedirect.com/science/article/abs/pii/S0377221716308657), free working paper: [EconStor PDF](https://www.econstor.eu/bitstream/10419/130166/1/856307327.pdf) |
| **Hybrid XGBoost + TabNet (rank-aggregation ensemble)**, explicitly tested against each model standalone with ~161 trialled configurations | Gradient-boosted trees + tabular deep learning (FT-Transformer also tested but excluded from final hybrid) | US equities | Hybrid: **51.26% annualized return, 2.44 Sharpe ratio, -7.76% max drawdown** (best of all constituents); **statistically significant CAPM alpha of 0.423 (p=0.011)** — the *only* model in the paper to achieve significant OOS alpha | Authors explicitly note Deflated Sharpe Ratio was **not** applied (per-trial Sharpes weren't retained) — so some of this is likely optimistic from configuration search | [arXiv 2608.27076](https://arxiv.org/html/2608.27076v1) |
| **FinRL Ensemble Strategy** — classic paper from the FinRL authors, selects the best-performing RL agent by rolling Sharpe ratio | PPO + A2C + DDPG agents, retrained every 3 months, best one selected dynamically | Dow Jones 30 constituents | Ensemble: **Sharpe 1.30** vs DJIA buy-hold 0.47 and min-variance allocation 0.45; beat each individual agent (A2C 1.12, PPO 1.10, DDPG 0.87) | RL backtests are historically the most prone to overfitting/inflated Sharpe in this whole research area — treat with extra skepticism, paper trade before trusting | [arXiv 2511.12120](https://arxiv.org/html/2511.12120v1), code: [AI4Finance-Foundation ensemble repo](https://github.com/AI4Finance-Foundation/Deep-Reinforcement-Learning-for-Automated-Stock-Trading-Ensemble-Strategy-ICAIF-2020) |
| **Ensemble-HMM voting framework** — tree ensembles (bagging + boosting) combined with Hidden Markov Model regime detection, feeding a hybrid voting classifier | Boosting/bagging tree ensembles + HMM regime labels | A diversified ETF and a Vanguard ETF, regime-labeled (bull/bear/neutral) | **17.86% annualized return, 1.34 Sharpe** (vs HMM alone: 12.89%, 0.92 Sharpe) on one ETF; **18.77%, 1.47 Sharpe** on the Vanguard ETF (vs HMM alone ~8.4%, ~0.6 Sharpe) | Regime detection quality directly gates the whole system's performance — a regime-misclassification cascades into bad trades | [AIMS Press DSFE 2025](http://www.aimspress.com/aimspress-data/dsfe/2025/4/PDF/DSFE-05-04-019.pdf) |

**Why this is the A+ tier**: every single paper above shows the **combined model beating every one of its own constituent models**, not just beating a weak baseline. That's a structurally different and more defensible claim than "my one architecture got a high Sharpe ratio" — it's direct evidence that different model families are making *different* mistakes, and combining them cancels out some of each one's blind spots. The Krauss et al. paper in particular is worth treating as your gold-standard template: long out-of-sample period, published/peer-reviewed, reports both pre- and post-cost numbers, and tests statistical significance of the alpha.

**What would push this to S-tier**: everything above is still backtest-only. None of these ensemble papers report a live or paper-trading track record spanning multiple real-time market regimes with real slippage — that gap (backtest → live, cost-adjusted, multi-year validation) is what separates "very promising research result" from a provably S-tier system.

---

## Cross-cutting lessons to build your own experiment around

1. **Always report both gross and net-of-cost results.** The single biggest number-killer across every category above is transaction costs — several "great" backtests turn negative once costs are added.
2. **Use Deflated Sharpe Ratio or block-bootstrap confidence intervals**, not a single point-estimate Sharpe ratio, if you want a result you can trust (see the regime-aware LightGBM paper for a template).
3. **Validate out-of-market, not just out-of-sample-in-time.** Kronos's starkest lesson: a model can be genuinely excellent on the market/period it was built for and nearly useless elsewhere.
4. **Match architecture to turnover tolerance.** If your strategy trades frequently, prioritize low-turnover-friendly architectures (the futures transformer-vs-LSTM cost study is the clearest evidence for this).
5. **An ensemble of uncorrelated model families is the most defensible "advanced" starting point** (see Section 5, A+ tier) — the Krauss et al. 2017 paper and the XGBoost+TabNet hybrid both show the combined model beating every one of its own constituents, not just a weak baseline. That's a structurally stronger claim than any single architecture's backtest number.
