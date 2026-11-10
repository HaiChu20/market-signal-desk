# Overnight log (2026-11-10)

Append-only notes from the autonomous review loop while the user sleeps.

- 06:10: User authorised overnight work (200 GB disk, accuracy first, Rust/C where useful).
  - Wrote docs/protocol.md (pre-registered evaluation rules).
  - Queued Codex: msg 373/374 (HistData DST fix + data reorg + start downloads) → stage 8 data lake → msg 375 (stage 9 pipeline: HTF bars, levels, dense features, Rust label kernel, 3 pilot methods).
  - Hourly check-in at :23 and a resume check at 10:07 are scheduled.
- 06:40: Codex milestone. Stage 7 tz fix + reorg done (37 tests). Stage 8 downloads running. BTC spot re-download matched the legacy data 111/111 months, so data/binance/ was removed (approved).
  My review found 3 more data problems (sent as msg 377):
  - (1) msd.data.load(source="dukascopy") silently returned 0 rows for NQ/SPX (wrong symbol remap). This made one of my own checks vacuous; caught and redone.
  - (2) HistData timestamps switch DST on non-US dates: every March and late Oct/early Nov in 2019–2026 is misaligned vs Dukascopy.
  - (3) HistData NSXUSD changed feed ~Dec 2018. Before that it is front-month-FUTURES-based (quarterly basis sawtooth 3–20 pts, i.e. roll jumps); after that it is identical to the Dukascopy cash CFD.
  Plan: NQ/SPX = HistData futures-era (roll-adjusted, flagged) until the switch, Dukascopy after. Databento CME futures remains the homogeneous gold-standard option (paid) for the user to decide.
- 06:55: Stage 8 downloads all running (HistData GRX/WTI, Binance ETH spot, UM futures, funding, metrics, Dukascopy backfill; Cboe done). Told Codex msg 377 index fixes come before stage 9 uses NQ/SPX; stage 9 starts on BTC/ETH/gold.
- 07:05: Dukascopy stage 8 runner failed on most new symbols (http CannotSendRequest = connection-reuse bug; BTCUSD empty-frame dtype bug). Gold not downloaded yet. Sent fix + restart in Tier order (XAUUSD first). HistData WTIUSD blocked (token not found), asked for diagnosis without workarounds.
- 07:15: Codex restarted the Dukascopy campaign (PID 20915), probably before reading msg 381, so the connection fix may not be in yet; the hourly check will verify. HistData GRXEUR done to 2023; WTIUSD stopped at 2023 (HistData page without download token, no bypass). DAX/WTI 2014+/2012+ come from Dukascopy anyway.
- 06:50 (hourly check): disk 261 GB free.
  - Downloads: Binance spot/UM/funding done, metrics running, Dukascopy retry (PID 20915) at USA500 2013 (no BLOCKED lines yet in the retry log). HistData WTIUSD blocked by the site (no bypass).
  - Stage 9 code appeared: processing/{timeframes,levels,features,labels,pipeline}.py, methods/{sr_touch,rsi2_mean_reversion,liquidity_sweep}.py, Rust crate. 44 tests pass.
  - Label kernel review sent (msg 383): time-based 5-day deadline instead of a bar count; a single shared Rust simulate fn (batch and single entry points duplicated logic and batch lacked limits); limit-order risk, fill and same-bar rules; financing rollover at 17:00 NY (crypto daily, no triple); store gross+net R and audit fields; 10k-case Rust==Python tests; gitignore build artifacts.
- 07:05: Codex milestone. Stage 9 scaffolding done (HTF bars, float32 feature store builder, levels/events, batched Rust labels, 10k-case Rust/reference test; Rust ≈ 512k labels/s vs Python ≈ 2.1k/s). Bounded BTCUSDT 2024 production batch running (PID 28238).
  NOTE: CAO shows Codex in ONE continuous turn for ~1h54m, and the inbox only delivers when the terminal is idle. My msgs 377 (HistData), 379 (priority), 381 (Dukascopy fix) and 383 (label-kernel review) are queued and will arrive in order when this turn ends.
  The current BTC-2024 labels predate the label fixes and must be regenerated after msg 383. BTC is not affected by the HistData issues.
- 07:12: BTCUSDT 2024 pipeline batch running (12 monthly feature files written). Codex still in its long turn; queued msgs pending.
- 07:20: Tests 51 pass. My spot-check of BTC 2024 features (401 cols, known_at = ts + 1 min) found:
  - spread_atr constant, i.e. BTC spot bid = ask and zero cost. CRITICAL for labels; the per-year modeled CFD spread must be embedded.
  - 240 inf values.
  - funding_z20 all NaN (funding not joined).
  - Meaningless 1d_return_1440.
  Sent msg 385: fix these, assert ask > bid in labels, auto feature-QA report, no cross-index features until the HistData fixes land.
- 07:30: Codex received msg 377 (inbox delivered). Loader remap fixed, with a missing-source test.
  - HistData clock rule found empirically: same as NY except +60 min during the US-vs-EU DST mismatch windows (spring: US start → EU start; fall: EU end → US end). Effectively an EST base with EU DST dates.
  - Feed switch pinned to 2018-12-16 23:00 UTC for NSXUSD and SPXUSD (100% exact closes thereafter).
  - Next: parser/schema + roll-adjusted futures-era series. No index stage 9 run yet (correct).
- 07:50 (hourly check): 259 GB free, data/ 3.9 GB. Binance metrics DONE. Dukascopy retry at XAGUSD 2003.
  - BLOCKED: USA30IDXUSD (conn reset), DEUIDXEUR (remote disconnected); XAUUSD aborted on one "implausible" day (2003-05-08).
  - Sent msg 389: quarantine bad days instead of aborting a symbol, verify the gold scale, neighbour-spike bad_tick flag, restart with XAUUSD first.
  - Codex still in one long turn (2h23m), so messages are queued. BTC 2024 stage 9 batch was interrupted (KeyboardInterrupt), presumably by Codex for the fixes.
- 07:58: Verified the gold scale /1000 is correct (2003 ≈ 341, 2010 ≈ 1233, 2024 ≈ 2315). The block was caused by the plausibility range (500–10000) excluding pre-2008 gold; silver/WTI (negative 2020-04-20) ranges were wrong too. Sent msg 391 with history-based ranges. Gold 2003 is sparse (~460 bars/day); the catalog will decide where usable history starts.
- 08:15: Verified msg 377 progress. The HistData DST reconstruction is CORRECT (95/95 months 2019–2026 ≥ 97.7% identical to Dukascopy, NQ and SPX). The feed switch at 2018-12-16 23:00 UTC is fine.
  Found a ROLL bug: adjustments sit at calendar-guessed bars (e.g. Mon 2016-03-21 04:00, raw jump 0.24) instead of the real switch (expiry Fri 2016-03-18 ~14:29–14:51 UTC gap). That creates fake adjusted jumps (median 21.5 pts NQ, max 141).
  Sent msg 392: detect real switch bars, measure the gaps via the Dukascopy offset change point (2014+) or FRED daily cash closes (2010–13), flat-offset checks, per-roll report, test. Index features stay blocked until it passes.
- 08:20: The Dukascopy downloader has exited (BTCUSD/ETHUSD blocked by connection errors). Told Codex the order: (1) downloader fixes 381/389/390 + restart detached with XAUUSD first, (2) roll fix 392, (3) label fixes 383 + feature fixes 387.
- 08:30: msg 377 milestone (written before 392): DST + feed switch verified, 56 tests. GRXEUR/WTIUSD HistData can't be validated, so Dukascopy is primary for DAX/WTI. Stage 9 BTC 2024 smoke >15 min per instrument-year: sent msg 396 (profile first, target ≤2 min/instrument-year, Rust for touch tracking, process pool, optimized path must equal the current outputs row-for-row).
- 08:40: Stage 9 smoke: sr_touch emitted 2.96M events for BTC 2024 (level-triggered on every bar near any of many overlapping swing levels). Codex stopped before labels. Sent msg 398:
  - edge-triggered sr_touch: TF ≥ 15m levels, clustered within 0.25 ATR(1h), ≥2 touches, re-arm after 0.5 ATR away, 4h cooldown per cluster;
  - same clustering for sweeps;
  - event-volume guard (>50/instrument-day fails);
  - no tool output outside the repo.
  NOTE FOR USER: a diagnostic `sample` profiler wrote a report under /tmp/python_...sample.txt (outside the repo, harmless, not deleted).
- 08:50: Codex reduced sr_touch to 65k/yr via 'nearest S/R per 15-min slot'. That's a time-grid sampler, not a touch trigger. Re-sent the msg 398 edge-triggered definition (msg 400). BTC smoke RSS 10.7 GB: asked for streaming by month, ≤3 GB/worker, ≤6 workers.
- 08:55: liquidity_sweep had the same combinatorics (8.86M events/yr). Codex applied its 15-min-slot dedup to sweeps too, before receiving msgs 398/400 (still queued behind its long turn). Those msgs replace it with the edge-triggered + clustered + 4h-cooldown definitions. No resend needed.
- 09:00: BTC smoke: capped events (65k S/R, 68k sweeps; definitions to be replaced by msg 398/400). Fixed a pandas duplicate-index bug in label-grid timestamp attachment; batch rerunning. Codex still in its long turn.
- 09:05: 58 tests pass. BTC smoke rerun active.
- 08:50 (hourly check): 251 GB free, data 4.2 GB.
  - BTC 2024 stage 9 final smoke COMPLETED (527k feature rows, 1.18M level rows, 2.46M grid labels, events). It still uses the pre-fix label kernel and capped events, so it's throwaway as data but useful as a baseline.
  - No downloader running since the Dukascopy exit. Codex is still in one long turn (3h23m), but dukascopy.py was edited at 08:49 (XAUUSD range 200+, broad except), so the downloader fix is in progress. Did not touch the file, to avoid conflicts.
- 09:00: Downloader fix in (61 tests). Restarted detached with XAUUSD first (fetching 2003-05, no errors so far). Gold 2003 data validated as genuine (~). HistData WTI: page returns HTTP 200 but has no download form; left alone.
- 09:10: Stage 9 smoke complete on BTC 2024 (+370 d warm-up) in 251 s.
  - Checked the outputs: they still predate the queued fixes. Labels use the bar-count deadline; two separate Rust paths; no 17:00 NY rollover; BTC spot bid == ask (spread 0, so stop-outs at exactly −1.0R = cost-free labels); funding not joined; sr/sweep use the 15-min-slot cap.
  - => These outputs are INVALID for modelling (baseline timing only). Msgs 383/387/392/396/398/400 are queued behind Codex's long turn (since ~05:20) and will arrive when it idles. No model training until they're implemented and re-reviewed.
- 09:15: Downloader PID 46185 running 8 workers, 0 BLOCKED. Rate ≈13 days/min on 2003 gold → ~8 h for full gold history, other symbols after. Acceptable; will re-measure on later years.
- 09:20: Codex is now receiving queued msgs (387 being implemented): explicit per-TF return names, inf→NaN guard, funding as-of join + z20, OI change, positive-spread validation for label inputs, yearly feature QA. 20 pipeline tests pass. ETH correctly fails until Dukascopy ETHUSD spread history is downloaded (no invented table).
- 09:25: msgs 389/390 implemented: quarantine CSV per day, year-abort only >1%, bad_tick flag excluded from features/labels, gold scale/range confirmed (2003-05-08 bid 340.97 / ask 341.37). 70 tests. Runner being restarted on the new code in tier order.
- 09:30: New downloader PID 51071 (quarantine-aware) running. Gold 2003–2006 complete (48 months, all complete-flagged, 0 quarantined). Rows/yr 2003 104k → 2006 333k (early gold sparse); the catalog will set the usable start. Now on 2007.
- 09:35: Silver band widened to $3–200; downloader restarted (PID 51882), gold resuming at 2007-09.
- 09:45: Codex report:
  - BTC 2024 features+labels regenerated (spread now applied, 0 inf; the inf came from open_interest_change with a zero denominator); feature QA report; 72 tests.
  - Funding was MISSING despite a "DONE" log. My root cause: wrong archive filename ({sym}-YYYY-MM.zip → 404; correct {sym}-fundingRate-YYYY-MM.zip → 200, verified) plus a silent return on 404 while still logging success.
  - Sent msg 409: fix + audit all downloaders for silent-success logging + mocked-404 test.
  - Reaffirmed the next priorities: msg 383 label kernel (still not done) → 392 rolls → 398/400 events → 396 perf.
- 09:55: Roll fix progress: exact post-gap switch bars located (e.g. NQ 2016-03-18 14:51 UTC after a 22-min gap), 60-min offsets per side, adjust before the switch only, roll flags propagated to HTF, returns spanning rolls masked; synthetic test passes; 75 tests.
  - Ranges corrected (WTI −60–300 etc.). Gold bars/day: 2003 562 → 2008+ ~1,400.
  - Pre-2014 rolls: FRED unhealthy (HTTP/2 INTERNAL_ERROR, http1.1 90 s timeout, tested by me). Stooq has a JS bot challenge (real block, not used).
  - Sent msg 416: FRED retry with backoff later; validate and use Dukascopy 2012–13 bid prices for gap measurement; mark unmeasurable rolls (≈2010-11–2011) as unmeasured and start NQ/SPX dev data at the first measured segment rather than guessing.
- 10:05: Roll report review: the NQ Mar 2016 gap was measured as −36.8, but the true value is ≈ −9.5 (daily medians −1.25/−1.55 → −11.3/−10.0).
  - Cause: on expiry Friday 13:30–14:29 UTC HistData shows the EXPIRED contract frozen after SOQ (std 0.9 while cash moved 14 pts), and the "before" window sat on it.
  - The "<1pt residual" check was circular (same windows).
  - Sent msg 417: full-day-median gaps, flag + exclude stale expired segments, independent day−1/day+1 acceptance test < 2 pts. Index builds stay blocked.
- 10:10: Downloader restarted once more (PID 56394, single instance verified), XAU at 2011-10, 0 quarantined.
- 10:15: Profiling baseline (BTC 2024-07): HTF 0.4 s, levels 2.9 s (hotspot _vwap_snapshots 2.3 s from ~101k iloc calls), features 0.7 s, events 1.7 s; ~6 s/month before labels. Sent order (msg 418): 383 labels → 416 rolls → 398/400 events → perf (vectorize with identical-output checks).
- 10:20: msg 383 in progress. 1 failing test (Rust==Python 10k), expected mid-change (new 15-arg API vs old built extension); Codex is leaving it visible, correctly.
- 09:50 (hourly check): 254 GB free, data 4.4 GB, single downloader running.
  - Gold aborted again at 2013-01 on a transient Dukascopy HTTP 503, so gold is complete only 2003-01..2012-12; the runner moved on to USA30 (now 2018-07).
  - Sent msg 421: 503s must not abort a symbol (long backoff, missing-days CSV, final pass, summary, test, consider 4 workers).
  - src/msd/methods/sr_touch.py is absent from disk (Codex screen shows "Deleted"), presumably mid-rewrite for msg 398/400; asked Codex to confirm.
  - msg 383 label kernel in progress.
- 10:07 (resume check): no usage-limit stop. Codex in a new turn (26 min) rewriting sr_touch + new level_clusters.py (msg 398/400); 3 tests failing mid-change, 76 pass. Downloader on BTCUSD 2021 after USA30/DAX.
- 10:10: USA30 aborted at 2019-07 (conn reset), DAX at 2014-01 (remote disconnected), same no-abort issue as gold. Addendum to msg 421 sent: the rule covers all transport errors; resume XAU 2013→, USA30 2019-07→, DAX 2014-01→.
- 10:25: Codex done with msg 398/400.
  - Edge-triggered clustered sr_touch + sweep; BTC 2022: S/R 3.32/day, sweep 11.83/day; guards pass; definitions in docstrings and trial ledger; 80 tests. BTC 2022 full in-memory feature build peaks 4.44 GiB (streaming not done yet).
  - My review: the truncation test uses a single hand-made level on 360 1m bars. It can't catch leakage via a full-history levels table (touches_so_far / invalidated_at) and may be vacuous for S/R.
  - Sent msg 424: end-to-end real-data truncation test (BTC 2022-01, 20 cuts, rebuild levels/features/events, non-empty assertion, levels_asof() in detectors). Then msg 383.
- 10:40: msg 383 label kernel + funding DONE (85 tests).
  - Funding: filename fixed; the Binance CSV schema was also misparsed (1970 timestamps); 82 months each BTC/ETH rebuilt; BTC 2024 features rebuilt with causal funding_z20.
  - Kernel: shared Rust simulate_one, timestamp deadlines, limit rules, 17:00 NY rollover (Friday triple, crypto daily), audit fields, 10k cases for both entry points.
  - MY INDEPENDENT CHECK: 500 random real BTC trades, label kernel == backtest.simulate (0 mismatches), Rust == Python 500/500. ACCEPTED.
  - Found: msd.data.load("BTCUSDT") still returns bid == ask (cost-free outside the pipeline). Sent msg 427: load() returns executable prices by default, raw=True opt-in, assertion + test.
- 10:55: Roll rebuild claimed a "0.0000" residual (circular). My independent day±1 check (adjusted − Dukascopy, full-day medians) FAILS:
  - NQ 2014-03 +22.6, 2015-03 +10.2, 2016-03 +26.7; SPX 2014-03 −11.2, 2015-03 +5.8, 2016-12 −4.6, 2017-03 −2.9, 2018-03 +5.2.
  - Missing NQ rolls (2016-12, 2017-06/09/12, 2018-03); doubtful SPX 2017 switches with zero raw step.
  - Other 2014–2016 rolls pass (<2 pts).
  - Sent msg 429: full msg 416 (full-day gaps, one switch per quarter, convention per year, stale-expired flags), acceptance = independent check on every roll + 4 rolls/yr.
- 10:50 (hourly check): 254 GB free, data 4.5 GB, 85 tests pass.
  - Downloads keep losing symbols to transient errors (fix msgs 421/422 still queued; Codex "waiting for background terminal" 34 min). Partial: XAU→2012-12, USA30→2019-07, DAX→2014-01, BTCUSD→2021-10, XAG→2004-04; EURUSD/ETHUSD not started.
  - Started a resumable download supervisor (scratchpad duka_supervisor.sh, PID 69788). It reruns the campaign after each exit, never 2 copies, ≤12 passes, disk guard. Told Codex how to stop it before restarting with its own fix (msg 431).
- 11:00: Codex end-of-pass report (86 tests).
  - Funding verified (7,488 prints each BTC/ETH; funding_z20 finite on 95% of BTC 2024 rows).
  - Label grid optimized 4.1 s → 0.8 s/month with an exact row-for-row match.
  - Event counts 2024 BTC (counts only, no outcomes): S/R 2.75/day, sweep 12.6/day.
  - Detectors ~64 s/yr each; full-year feature pass 4.44 GiB, so month streaming is still needed.
  - Its roll "0.0000" claim and the FRED no-retry stance are superseded by my queued msgs 414/416/428. With its turn ended, the queued msgs (414, 416, 419, 421/422, 424, 426, 428, 429) will now be delivered.
- 11:15: Roll correction v2 reviewed. The full-day method is right (Mar 2016 −10.04 ± 0.25 vs my ≈ −9.5); 19 NQ / 18 SPX validated with held-out ≤ 1.7. But adjusted values are NaN before 2018-06 (NQ) / 2017-12 (SPX) because the classification is too strict:
  - near-zero gaps were called "unmeasured";
  - from 2016-12 HistData rolls at the Thursday daily close, so there's no stale segment and "switch evidence failed" on well-measured rolls.
  Sent msg 433:
  - (A) UNBLOCK the NQ/SPX stage 9 run on the clean cash era 2018-12-16→ (Dukascopy primary);
  - (B) new MEASURED rule (switch located, uncertainty ≤ 1 pt, held-out < 2), stale evidence only for post-SOQ switches, diagnose the true failures (NQ 2018-03/06), report the longest contiguous validated futures-era segment.
- 11:40: Old runner exited, so my supervisor launched pass 1 (PID 78539) with the on-disk fixed downloader code. Stopped the supervisor loop (69788) to avoid duplicates with Codex's planned relaunch; told Codex (msg 435) not to launch another while 78539 runs.
- 11:50 (hourly check): 253 GB free, data 4.7 GB. Single downloader (78539, fixed code, 4 workers): gold at 2015-08 (~1 month/min, ~2 h to finish gold), no missing days logged. Codex in a new turn (19 min), presumably msg 433 (cash-era NQ/SPX stage 9 + roll classification).
- 12:00: Codex perf milestone: VWAP snapshots 2.33 s → 0.003 s (exact match), events ~40% faster (exact match), 92 tests; full label grid 2.7 s/month under download load. Codex's view of the downloader is stale (old runner already exited; patched runner 78539 active, XAU 2015+); msg 434 queued tells it not to duplicate.
- 12:05: Codex mistook the patched runner 78540 (log stage8_dukascopy_supervised.log, XAU 2016) for the stuck old campaign (it read the stale stage6 log). Sent a correction (msg 437): don't kill or duplicate it, monitor the right log, move on to msg 432 (cash-era NQ/SPX stage 9 + roll classification).
- 12:10: Codex (same turn, hasn't received msg 437 yet) is waiting rather than duplicating, which is safe. Patched runner keeps progressing.
- 12:20: Codex stopped runner 78540 (believing it wedged) and restarted with the fixed code (log stage8_dukascopy_resume.log); resumable, so no data loss. ALSO: the end-to-end real-data truncation test (msg 424) found a REAL look-ahead mismatch in partial-day volume-profile levels; Codex fixed it.
- 12:55 (hourly check): 253 GB free, data 4.9 GB. Gold at 2024-08 (nearly done), 0 quarantined, 0 missing. Suite: 95 pass, 5 FAIL (cash-era index guard blocks USATECH; HistData single-price input reaches labels; ask_o attribute; 2 stage1 asserts). Full suite now 215 s because of the real-data truncation test.
  - Roll rebuild v3: only 2–3 of 32 rolls applied, unstable dates, so it is not converging.
  - ARCHITECT DECISION (msg 440): park the futures era (2010-11→2018-12-16) for NQ/SPX, excluded pending a homogeneous source (CME/Databento, user's call). The pipeline uses the cash era 2018-12-16→ with Dukascopy primary; dev for indices = 2019–2022. Guard scoped to the futures era only; fix the 5 failing tests; run cash-era stage 9; mark the slow test.
- 13:55: Cash-era NQ/SPX stage 9 done (96 feature months 2018-12→2026-11, QA clean, 103 fast tests pass). Review:
  - (1) RSI(2) emits 0 events for indices: the detector requires known_at == 1d_bar_known_at (17:00 ET CME close), but index data has no bars 16:15–17:00, so it can never fire. Fix sent (as-of transition trigger + gap test + grep for the same pattern).
  - (2) The "event_counts" log reports candidate rows (×~42), not events; unique events are sane (SPX 2022: 4,216 sweeps, 256 S/R). Asked to rename the field and make guards use unique events, and for SPX events through 2026 like NQ.
  The user is awake (asked status 13:43): morning summary given; pending answers on git commit, /tmp file, tick data.
