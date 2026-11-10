# Data catalog

Dataset manifests and local bar inventories. Sizes include Parquet only.

| Source | Symbol | First ts | Last ts | Bars | Parquet size | Columns | Price type | Volume type |
|---|---|---|---|---:|---:|---|---|---|
| dukascopy | BTCUSD | 2017-05-07 23:59:00+00:00 | 2019-06-30 23:59:00+00:00 | 772,446 | 28.7 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bidask | tick |
| dukascopy | DEUIDXEUR | 2014-01-01 00:10:00+00:00 | 2014-01-31 21:50:00+00:00 | 25,568 | 1.0 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bidask | real |
| dukascopy | USA30IDXUSD | 2014-01-02 11:00:00+00:00 | 2017-12-29 20:59:00+00:00 | 991,134 | 56.1 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bidask | tick |
| dukascopy | USA500IDXUSD | 2012-01-19 16:20:00+00:00 | 2026-11-09 23:59:00+00:00 | 4,096,139 | 173.6 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bidask | tick |
| dukascopy | USATECHIDXUSD | 2012-01-19 16:15:00+00:00 | 2026-11-09 23:59:00+00:00 | 4,262,121 | 228.1 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bidask | tick |
| dukascopy | XAUUSD | nan | nan | 0 | 0.0 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bidask | tick |
| histdata | GRXEUR | 2010-11-15 07:00:00+00:00 | 2026-11-06 20:58:00+00:00 | 3,816,520 | 156.9 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bid | none |
| histdata | NSXUSD | 2010-11-14 23:01:00+00:00 | 2026-11-06 21:13:00+00:00 | 5,326,825 | 267.9 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bid | none |
| histdata | SPXUSD | 2010-11-14 23:00:00+00:00 | 2026-11-06 21:13:00+00:00 | 4,691,937 | 196.3 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bid | none |
| histdata | WTIUSD | 2010-11-15 01:15:00+00:00 | 2023-12-01 21:58:00+00:00 | 4,203,945 | 115.5 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | bid | none |
| binance_spot | BTCUSDT | 2017-08-17 04:00:00+00:00 | 2026-10-31 23:59:00+00:00 | 4,833,919 | 437.3 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | trade | real |
| binance_spot | ETHUSDT | 2017-08-17 04:00:00+00:00 | 2026-10-31 23:59:00+00:00 | 4,833,918 | 352.8 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | trade | real |
| binance_um | BTCUSDT | 2020-01-01 00:00:00+00:00 | 2026-10-31 23:59:00+00:00 | 3,592,800 | 289.3 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | trade | real |
| binance_um | ETHUSDT | 2020-01-01 00:00:00+00:00 | 2026-10-31 23:59:00+00:00 | 3,592,800 | 267.0 MiB | ts, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, volume | trade | real |

## Primary source per instrument and period

| Instrument | Period | Primary source | Reason |
|---|---|---|---|
| Nasdaq-100 | 2018-12-16 23:00 UTC onward | Dukascopy USATECHIDXUSD | Cash CFD bid/ask and tick volume; HistData cash-era closes are retained only as a cross-check |
| S&P 500 | 2018-12-16 23:00 UTC onward | Dukascopy USA500IDXUSD | Cash CFD bid/ask and tick volume; HistData cash-era closes are retained only as a cross-check |
| Gold | all available | Dukascopy XAUUSD | primary bid/ask source |
| BTC / ETH spot | all available | Binance spot | trade OHLC and real volume/flow |
| BTC / ETH futures | 2019-09 onward | Binance USD-M | futures trade OHLC and flow |
| FX, metals, indices, energy context | all available | Dukascopy | primary multi-asset source |

NQ/SPX HistData changes from futures-based prices to cash-index-like prices at 2018-12-16 23:00 UTC. The entire 2010-11 through 2018-12-16 23:00 UTC futures era is excluded from features, labels and models; raw HistData files and their `feed`, `stale_expired` and `roll` metadata are retained, while `adj_bid_*` is NaN. Status: **excluded, pending a homogeneous source (for example CME futures via Databento); user decision**. The pipeline development period for these indices is 2019-01-01 through 2022-12-31. From 2018-12-16 23:00 UTC onward, the primary source is Dukascopy cash CFD bid/ask and tick volume; HistData is identical there and is kept only as a cross-check. No stitching is used. A homogeneous real-volume alternative is CME futures through Databento (paid; $125 credit); no account was created.

HistData GRXEUR can be checked against only one Dukascopy DEUIDXEUR month (2014-01), and no LIGHTCMDUSD overlap is present for WTIUSD. Their feed regime and DST behavior therefore remain unverified against a second source; the files are marked `unclassified` rather than assumed to be cash or futures.

## Quality and coverage

Per-source/year coverage and recurring gaps are in `reports/data/data_quality_<SYMBOL>.md`; HistData/Dukascopy cross-validation is in `reports/data/histdata_vs_dukascopy.md`.


## Gold bars per day

UTC calendar-day counts from Dukascopy XAUUSD. Median and 10th–90th percentile expose sparse early history.

| Year | Days | Median bars/day | P10 | P90 | Days ≥ 1,000 bars |
|---:|---:|---:|---:|---:|---:|
| 2003 | 198 | 562 | 12 | 755 | 0 |
| 2004 | 314 | 797 | 15 | 917 | 5 |
| 2005 | 312 | 1006 | 67 | 1281 | 157 |
| 2006 | 313 | 1285 | 84 | 1363 | 246 |
| 2007 | 313 | 1314 | 113 | 1397 | 258 |
| 2008 | 314 | 1390 | 141 | 1413 | 259 |
| 2009 | 313 | 1397 | 144 | 1415 | 258 |
| 2010 | 50 | 1412 | 92 | 1420 | 40 |

