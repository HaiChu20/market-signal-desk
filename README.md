# Market Signal Desk

A strategy-agnostic historical data, spread-aware backtest, and paper-forward signal system. The engine sends alerts and records simulated outcomes; it does not place orders.

## Architecture

- `msd.data` loads UTC OHLC bars with bid/ask prices. Index CFD bars are downloaded from Dukascopy; BTCUSDT bars come from checksum-verified Binance archives with the modeled spread embedded into bid/ask.
- `msd.backtest.simulate(bars, orders)` applies side-specific fills, intrabar stop/TP rules, and timestamp-keyed stop updates. An update at time `t` takes effect on the next bar.
- `msd.strategy_check.assert_causal(module, bars)` checks random truncations and future-volume perturbations.
- The public spot shadow loop uses Binance closed 1-minute candles for BTCUSDT and ETHUSDT. It backfills gaps through REST, computes causal offline features and supported method events, and records preliminary candidates in SQLite. The Capital.com index adapter awaits credentials and implementation.
- Historical results and research remain in `reports/` and `docs/`. The prior strategy and ML implementations were removed; none is selected for live operation.

## Strategy contract

A strategy is a Python module with:

```python
NAME = "example"
SYMBOLS = ("USATECHIDXUSD",)
RESOLUTION = "MINUTE"  # MINUTE, HOUR, or DAY

def orders(bars):
    """Return causal order dictionaries using only bars through decision_ts."""
    return []
```

Each order has `decision_ts`, `side` (`+1` long, `-1` short), and `stop`; it may also have `tp`, `exit_ts`, `stop_path` (a `{timestamp: stop_level}` mapping), `confidence`, `size`, and `note`. The decision bar must be closed. Market orders use the next forming bar's open as the approximate entry. A limit order adds `entry_type="limit"`, `entry_price` (limit price), and `expiry_ts`; it remains pending until the ask low reaches the limit for a long or the bid high reaches it for a short. A favorable gap fills at the open. Stops and targets are checked on completed bars, with the stop taking priority if both are touched. On a limit fill bar only the stop is active. Pending orders persist in SQLite and expire at the first bar whose open time reaches `expiry_ts`. Strategy authors should run `assert_causal` before backtesting or enabling a module.

To add a strategy, create one module implementing this contract and add one `[[strategies]]` entry to `live.toml` with its import path and `enabled = true`. No engine changes are needed. Strategy entries are deliberately absent until a new strategy is reviewed.

CME equity index hours are modeled in New York time: Sunday 18:00 through Friday 17:00, with a daily 17:00–18:00 break. BTC is 24/7. The market-hours helper is DST-aware; holidays are not separately modeled. Data quality reports retain cash-session metrics and include full-day coverage, missing in-hours minutes, and longest in-hours gaps.

## Setup

```sh
uv sync --dev
uv run pytest
uv run python -m msd.data.dukascopy --symbol USATECHIDXUSD --start 2018-01-01
uv run python -m msd.data.quality --symbol USATECHIDXUSD --hours cme_equity
```

`docker compose up -d --build` runs the Binance shadow loop without credentials. It records one structured audit row per completed minute and symbol, with reason `data`, `model`, `edge`, `position`, `blackout`, or `emitted`; a bar without a setup is `edge` with detail `no_setup`. Preliminary candidates remain in SQLite and never reach Telegram. The feed backfills missing closed bars through REST; a stale bar, incomplete ten-day warmup, or abnormal same-hour spread suppresses alerts. Spread percentiles, warmup, validity minutes, and the ATR don't-chase band are CLI options on `uv run python -m msd.live.shadow --help`.

The loop never sends Telegram messages. Qualified paper signals are stored in SQLite and included in the structured stdout audit line; connecting a real chat requires separate user approval. A model needs a matching artifact manifest, a candidate-aware probability model, an explicit live policy with costs, a calibrated `expected_net_R` curve, and a report card graded ✅ or 🧪. The shared `decision.choose` must pass the 0.05R edge threshold and its neighbouring-candidate check. All alerts are labelled PAPER. Current development report cards are ungraded. Binance REST gap bars contain trade prices and therefore fail the executable-spread gate; live bars combine the public trade and bookTicker streams into volume plus bid/ask OHLC. The five checkpointed rules `ma_cross`, `macd_signal`, `stochastic`, `bollinger`, and `donchian_atr_breakout` join the pilot detectors online; other frozen methods are marked unavailable until their input and state parity is verified.

The older Capital.com path remains at `uv run python -m msd.live.engine --check` and supports `--dry-run`, `--replay START END --symbol SYMBOL --strategy package.module`, and `--verify-live package.module SYMBOL START END`.

## Strategy status

The previous Noise Area, setup, Donchian and ML code was removed for this strategy-agnostic rebuild. Historical evaluation tables remain available in `reports/` and research notes in `docs/`; they are historical results and are not a current strategy recommendation.

## Historical data sources

HistData NSXUSD and SPXUSD minute bars are retained in `data/bars/histdata/` from 2010-11 through 2026-11. They are bid-only; ask is copied from bid as a neutral placeholder, and volume is NaN because the source's volume field is always zero. Source wall times are New York local with DST. Fall-back duplicate times are assigned in chronological fold order; nonexistent spring-forward times are dropped and recorded. The Stage 7 comparison is in [the full report](reports/data/histdata_vs_dukascopy.md) and [full-day coverage](reports/data/data_quality_NSXUSD.md), [S&P coverage](reports/data/data_quality_SPXUSD.md).

For research coverage, use HistData for 2010-11 through 2018-05 and Dukascopy from 2018-06 onward. The corrected DST-aware overlap comparison determines timestamp alignment empirically; Dukascopy supplies actual bid/ask prices for cost realism. HistData spread is modeled from each symbol's same-year Dukascopy median spread. Before 2018, where Dukascopy full-day coverage is not representative, the earliest full-day year (2018) median is carried backward: USATECHIDXUSD 2.881 points and USA500IDXUSD 0.462 points. The yearly observed Dukascopy medians are:

| Year | USATECHIDXUSD spread | USA500IDXUSD spread |
|---:|---:|---:|
| 2018 | 2.881 | 0.462 |
| 2019 | 2.961 | 0.461 |
| 2020 | 3.234 | 0.520 |
| 2021 | 3.214 | 0.524 |
| 2022 | 3.212 | 0.518 |
| 2023 | 3.262 | 0.514 |
| 2024 | 3.406 | 0.514 |
| 2025 | 1.515 | 0.516 |
| 2026 (partial) | 1.172 | 0.522 |

Older v1 strategy reports are in [the archived results folder](reports/archive/2026-11-v1-strategies/README.md). Document indexes are in [docs/README.md](docs/README.md).
