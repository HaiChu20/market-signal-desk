# SPX cash-era minute-gap audit, December 2018–June 2020

**Proposal: leave the SPX gaps unfilled from HistData.** The available HistData cash-era bars have the same minute set and bid closes as Dukascopy, so they add no missing SPX minutes. Carrying the 0.66 spread onto invented bars would not restore observed quotes. Retain the existing Dukascopy bars and their source/spread information; revisit only if an independent tick or bar source covers the holes.

## Clock and comparison basis

HistData parquet `ts` is already UTC-normalized. Its source wall clock is New York local time but changes DST on EU dates; `histdata.parse_csv` applies that rule. No second clock correction or timestamp lag is applied here. The cash comparison starts at 2018-12-16 23:00 UTC and ends before 2020-07-01 UTC. A missing SPX minute is a minute present in NQ and absent in SPX; the reverse defines missing NQ. This is an observed same-session reference, not an estimate of every theoretically tradable minute.

## Month-by-month coverage and possible additions

| Month | Duka SPX | Duka NQ | SPX absent while NQ trades | HistData SPX present in those | **SPX minutes addable** | NQ absent while SPX trades | HistData NQ present in those |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2018-12 | 13,036 | 13,160 | 128 | 0 | **0** | 4 | 0 |
| 2019-01 | 28,386 | 29,211 | 825 | 0 | **0** | 0 | 0 |
| 2019-02 | 24,216 | 26,319 | 2,105 | 0 | **0** | 2 | 0 |
| 2019-03 | 25,223 | 28,080 | 2,857 | 0 | **0** | 0 | 0 |
| 2019-04 | 23,173 | 27,989 | 4,817 | 0 | **0** | 1 | 0 |
| 2019-05 | 28,659 | 30,370 | 1,713 | 0 | **0** | 2 | 0 |
| 2019-06 | 24,553 | 26,811 | 2,259 | 0 | **0** | 1 | 0 |
| 2019-07 | 25,755 | 30,302 | 4,550 | 0 | **0** | 3 | 0 |
| 2019-08 | 28,517 | 29,250 | 733 | 0 | **0** | 0 | 0 |
| 2019-09 | 25,874 | 27,958 | 2,084 | 0 | **0** | 0 | 0 |
| 2019-10 | 28,442 | 30,674 | 2,235 | 0 | **0** | 3 | 0 |
| 2019-11 | 23,912 | 27,457 | 3,547 | 0 | **0** | 2 | 0 |
| 2019-12 | 22,322 | 27,694 | 5,386 | 0 | **0** | 14 | 0 |
| 2020-01 | 26,698 | 29,143 | 2,453 | 0 | **0** | 8 | 0 |
| 2020-02 | 25,699 | 26,502 | 803 | 0 | **0** | 0 | 0 |
| 2020-03 | 26,772 | 26,394 | 82 | 0 | **0** | 460 | 0 |
| 2020-04 | 28,027 | 28,035 | 8 | 0 | **0** | 0 | 0 |
| 2020-05 | 27,774 | 27,837 | 64 | 0 | **0** | 1 | 0 |
| 2020-06 | 29,331 | 29,370 | 39 | 0 | **0** | 0 | 0 |

Total SPX candidate gaps: **36,688**; covered by HistData SPX: **0**. Total NQ candidate gaps: **501**; covered by HistData NQ: **0**.

## Shape and timing of absent minutes

### SPX

36,688 absent minutes in 23,787 runs; longest 19 minutes. Of 23,477 runs with adjacent SPX bars, 4,413 have identical bid closes across the gap and 7,080 touch a zero-range bar. The preceding bar is zero-range before 17.6% of missing candidate minutes versus 3.1% of present candidate minutes (where a preceding bar exists). This association and the short runs support a no-tick explanation, but cannot prove that no ticks occurred.

| Run length | Number of runs |
|---|---:|
| 1 minute | 16,789 |
| 2–5 | 6,644 |
| 6–59 | 354 |
| 60–239 | 0 |
| 240+ | 0 |

NY local hour counts (minutes absent while the other index trades):

| Hour | Absent minutes |
|---:|---:|
| 00 | 4,941 |
| 01 | 3,440 |
| 02 | 2,010 |
| 03 | 669 |
| 04 | 1,008 |
| 05 | 1,485 |
| 06 | 1,805 |
| 07 | 1,919 |
| 08 | 1,184 |
| 09 | 598 |
| 10 | 144 |
| 11 | 223 |
| 12 | 387 |
| 13 | 450 |
| 14 | 372 |
| 15 | 108 |
| 16 | 129 |
| 17 | 0 |
| 18 | 3,713 |
| 19 | 2,735 |
| 20 | 1,179 |
| 21 | 1,277 |
| 22 | 2,466 |
| 23 | 4,446 |

Largest runs:

| UTC start | UTC end | Minutes |
|---|---|---:|
| 2019-06-12 23:11 | 2019-06-12 23:29 | 19 |
| 2019-07-04 04:35 | 2019-07-04 04:53 | 19 |
| 2019-12-26 03:54 | 2019-12-26 04:12 | 19 |
| 2019-11-12 04:07 | 2019-11-12 04:24 | 18 |
| 2019-12-12 04:41 | 2019-12-12 04:58 | 18 |
| 2019-01-11 06:23 | 2019-01-11 06:38 | 16 |
| 2019-04-15 23:38 | 2019-04-15 23:53 | 16 |
| 2019-04-25 04:41 | 2019-04-25 04:56 | 16 |
| 2019-12-20 04:03 | 2019-12-20 04:18 | 16 |
| 2019-12-24 05:12 | 2019-12-24 05:27 | 16 |

### NQ

501 absent minutes in 75 runs; longest 123 minutes. Of 41 runs with adjacent NQ bars, 6 have identical bid closes across the gap and 8 touch a zero-range bar. The preceding bar is zero-range before 12.0% of missing candidate minutes versus 0.0% of present candidate minutes (where a preceding bar exists). This association and the short runs support a no-tick explanation, but cannot prove that no ticks occurred.

| Run length | Number of runs |
|---|---:|
| 1 minute | 53 |
| 2–5 | 12 |
| 6–59 | 7 |
| 60–239 | 3 |
| 240+ | 0 |

NY local hour counts (minutes absent while the other index trades):

| Hour | Absent minutes |
|---:|---:|
| 00 | 58 |
| 01 | 56 |
| 02 | 62 |
| 03 | 5 |
| 04 | 39 |
| 05 | 60 |
| 06 | 55 |
| 07 | 8 |
| 08 | 2 |
| 09 | 1 |
| 10 | 1 |
| 11 | 0 |
| 12 | 2 |
| 13 | 0 |
| 14 | 0 |
| 15 | 0 |
| 16 | 0 |
| 17 | 0 |
| 18 | 9 |
| 19 | 4 |
| 20 | 0 |
| 21 | 23 |
| 22 | 48 |
| 23 | 68 |

Largest runs:

| UTC start | UTC end | Minutes |
|---|---|---:|
| 2020-03-17 02:45 | 2020-03-17 04:47 | 123 |
| 2020-03-20 09:04 | 2020-03-20 10:54 | 111 |
| 2020-03-17 05:26 | 2020-03-17 06:51 | 86 |
| 2020-03-17 01:52 | 2020-03-17 02:16 | 25 |
| 2020-03-20 08:08 | 2020-03-20 08:29 | 22 |
| 2020-03-17 08:31 | 2020-03-17 08:41 | 11 |
| 2020-03-17 04:49 | 2020-03-17 04:56 | 8 |
| 2020-03-17 05:02 | 2020-03-17 05:09 | 8 |
| 2020-03-12 11:56 | 2020-03-12 12:01 | 6 |
| 2020-03-17 05:13 | 2020-03-17 05:18 | 6 |

## HistData overlap price test

Exact means absolute difference ≤0.001 index point. Differences use unadjusted HistData `bid_c` versus Dukascopy bid close and `(bid_c + ask_c)/2`. Return correlations use only consecutive one-minute returns, with the HistData timestamp shifted by the stated lag.

| Index | Duka/HistData common minutes | HistData-only | Dukascopy-only | HistData feed | Duka bid exact | Bid median absolute diff | Duka mid exact | Mid median absolute diff |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| SPX | 485,574 | 0 | 795 | cash_cfd | 100.000000% | 0.000000 | 0.000824% | 0.330000 |
| NQ | 521,715 | 0 | 841 | cash_cfd | 100.000000% | 0.000000 | 0.000000% | 1.535000 |

| Index | Target | Lag −60 | −2 | −1 | 0 | +1 | +2 | +60 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| SPX | bid | -0.0047 (403,358) | -0.0088 (427,482) | -0.0060 (442,680) | 1.0000 (461,465) | -0.0060 (442,680) | -0.0088 (427,480) | -0.0046 (403,287) |
| SPX | mid | -0.0047 (403,358) | -0.0089 (427,482) | -0.0056 (442,680) | 0.9998 (461,465) | -0.0059 (442,680) | -0.0087 (427,480) | -0.0046 (403,287) |
| NQ | bid | -0.0040 (496,095) | -0.0150 (519,639) | 0.0022 (520,304) | 1.0000 (520,986) | 0.0022 (520,305) | -0.0150 (519,639) | -0.0039 (496,035) |
| NQ | mid | -0.0040 (496,095) | -0.0151 (519,639) | 0.0025 (520,304) | 0.9998 (520,986) | 0.0023 (520,305) | -0.0150 (519,639) | -0.0041 (496,035) |

HistData's minute set is a strict subset of Dukascopy's in this period; its 795 SPX and 841 NQ absent bars cannot help fill gaps. The matching bid closes on every overlapping minute are consistent with the two vendors sharing a cash-CFD quote source. The stored series do not supply independent observations of SPX's missing minutes. The data cannot distinguish omitted no-tick minutes from missing collection or vendor-feed minutes. The constant 0.66 spread in the early SPX era is a quote convention, not evidence that a bid can safely be synthesized for absent minutes.

## Decision

**Leave gaps.** A HistData-based fill would add the per-month counts in the bold column above (zero if the feeds are coterminous). Do not create `source=histdata` or `spread_modeled` bars where HistData has no observation. If independent coverage is obtained later, require timestamp and bid validation against observed adjacent minutes, and mark any inserted bars with both provenance and modeled-spread flags.
