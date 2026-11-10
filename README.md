# Market Signal Desk

A strategy-agnostic historical data, spread-aware backtest, and paper-forward signal system. The engine sends alerts and records simulated outcomes; it does not place orders.

## Architecture

- `msd.data` loads UTC OHLC bars with bid/ask prices. Index CFD bars are downloaded from Dukascopy; BTCUSDT bars come from checksum-verified Binance archives with the modeled spread embedded into bid/ask.
- `msd.backtest.simulate(bars, orders)` applies side-specific fills, intrabar stop/TP rules, and timestamp-keyed stop updates. An update at time `t` takes effect on the next bar.
- `msd.strategy_check.assert_causal(module, bars)` checks random truncations and future-volume perturbations.
- The live engine polls Capital.com and stores signals, exits, and processing checkpoints in SQLite. `live.toml` currently has **zero strategies enabled**. Paper mode is the default.
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

Each order has `decision_ts`, `side` (`+1` long, `-1` short), and `stop`; it may also have `tp`, `exit_ts`, `stop_path` (a `{timestamp: stop_level}` mapping), `confidence`, `size`, and `note`. The decision bar must be closed. The live engine announces a new order when the next bar is forming and uses that bar's open as the approximate entry. Stops and targets are checked on completed bars, with the stop taking priority if both are touched. Strategy authors should run `assert_causal` before backtesting or enabling a module.

To add a strategy, create one module implementing this contract and add one `[[strategies]]` entry to `live.toml` with its import path and `enabled = true`. No engine changes are needed. Strategy entries are deliberately absent until a new strategy is reviewed.

CME equity index hours are modeled in New York time: Sunday 18:00 through Friday 17:00, with a daily 17:00–18:00 break. BTC is 24/7. The market-hours helper is DST-aware; holidays are not separately modeled. Data quality reports retain cash-session metrics and include full-day coverage, missing in-hours minutes, and longest in-hours gaps.

## Setup

```sh
uv sync --dev
uv run pytest
uv run python -m msd.data.dukascopy --symbol USATECHIDXUSD --start 2018-01-01
uv run python -m msd.data.quality --symbol USATECHIDXUSD --hours cme_equity
```

Configure Capital.com demo credentials and Telegram variables from `.env.example` into a local `.env` (never commit it), then run `docker compose up -d`. `uv run python -m msd.live.engine --check` validates the Capital connection. `--dry-run` and `--replay START END --symbol SYMBOL --strategy package.module` support local replay; `--verify-live package.module SYMBOL START END` compares replayed signals and exits against the backtest simulator. Tests use synthetic fixtures and do not make network calls.

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
