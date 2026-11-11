# Roadmap (agreed 2026-11-11)

Goal: a 24/7 system that reads live market data and sends a Telegram signal (symbol, side, entry,
SL, TP, confidence) **only when the evidence is strong enough**. Two phases, run in order.

## Signal policy (both phases)

**Live data.** Stream Level 1 data:
- the broker's bid/ask for NQ, SPX and gold;
- Binance trades plus the best bid/ask for BTC and ETH.

Build the 1-minute bid/ask bars on our own machine, the same way the history was built. Record
the raw ticks for later retraining. Level 2 is deferred. CFDs have no order book, and the free
crypto depth history starts in 2023, after the development period.

**Decision moments.** The system checks at every completed 1-minute bar:
- Phase 1: when a setup fires on that bar;
- Phase 2: on every bar.

Between bars, ticks are used only to watch open signals: SL/TP hit, or price has moved too far to
enter.

**Silence is the default.** A signal is sent only when all of these hold:
1. **Data ready:**
   - the feed is fresh (no stale or missing bars);
   - the warm-up history is complete;
   - the spread is normal for that instrument and hour.
2. **Model allowed:** only methods or models graded under the protocol may emit. ✅ Confirmed may
   emit; 🧪 Experimental is paper-only.
3. **Enough edge:** expected R after costs and uncertainty shrinkage is above the threshold (now
   0.05R), and the neighbouring SL/TP choices are positive too (`decision.choose`). Confidence is
   judged through expected R, not raw probability: 40% with TP = 3R is good, 60% with
   TP = 0.5R may not be.
4. **Free to trade:**
   - no open signal on that symbol (the next one is allowed at `label_end_ts + 1 min`);
   - no blackout filter is active.

There is no minimum signal rate. Days without signals are expected.

## Phase 1: finish the current plan (method tournament), now

1. **Event-scan fix** (17 of 29 detectors produced no events). Then replay events for NQ, SPX,
   XAU, BTC and ETH.
2. **Flow features:**
   - review and commit;
   - check the 80%-of-source coverage rule;
   - keep 0 (no activity) separate from NaN (no data).
3. **Benchmark and gating:** ETH costs in the random-direction benchmark; `research/gating.py`.
4. **Live shadow loop:** paper mode, public feeds and the Telegram format.
5. **Downloader merges:**
   - merge the bookDepth parser fix and rebuild the depth features;
   - merge the vectorised Bybit reader (a50dfb8);
   - raise ticks to 4 workers after the 1m campaign.
6. **DEV tournament** on production4 plus the replayed events: a report card per method.
7. **Final Roihu bundle;** the user submits the sequence CNN DEV run, then we grade its OOF
   predictions.
8. **Stage 9 for the remaining markets** (Dow, DAX, silver, FX, oil, FTSE, Nikkei).
9. **Test grading** (2023–2024) of the frozen configurations, once (protocol v2 §5).

Phase 1 is done when:
- every method has a report card and a Test grade;
- the CNN is graded;
- the live loop runs in paper mode with whatever passed.

## Phase 2: every-minute model families plus a combiner (after Phase 1)

- **Protocol v3 first.** Written before any Phase 2 result:
  - task: at each 1-minute close, P(TP before SL) for the 2 sides × 5 SL × 7 TP grid;
  - the same purged folds for every model;
  - how the combiner is graded.
- **Families**, each writing out-of-fold predictions in one shared format:
  - A. LightGBM/CatBoost on features, with the setups as input flags;
  - B. sequence nets (the CNN, then LSTM/Transformer variants), trained on all minutes;
  - C. Chronos/TimesFM, tested first as extra inputs to A;
  - D. Kronos fine-tuned on our 1m bars (Roihu).
- **Combiner:**
  - start with a plain average (Krauss et al. 2017);
  - then a small stacking judge with regime inputs;
  - it counts only if it beats every member on unseen DEV years, then on Test once.
- Background: `trading-model-research-findings.md`.

## Rules that protect both phases

- **Phase 1 Test results must not steer Phase 2:**
  - Phase 2 chooses inputs and models on DEV data only;
  - every setup flag enters, whatever its Phase 1 grade.
- **Every run is logged** in `reports/trials.csv`, and multiple-testing control counts trials from
  both phases.
- **The Final period** (2025 onward) stays locked until both phases end, then is evaluated once.
- **Paper first:** at least 3 months of forward paper results before any real money.

## Decisions and open items

- **Raw data:** keep all raw archives, including Bybit 2024–2026. User decision, 2026-11-11.
- **Live broker feed:** to be decided. The live code has a Capital.com client.
- **24/7 machine:** to be decided (small cloud server or mini-PC). Roihu is for training only.
