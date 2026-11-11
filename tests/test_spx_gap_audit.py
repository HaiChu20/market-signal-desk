"""Offline checks for the read-only cash-index gap audit."""
import numpy as np
import pandas as pd

from msd.data.spx_gap_audit import lag_correlations, minute_runs, preceding_flat_rate


def test_minute_runs_and_flat_predecessor() -> None:
    ts = pd.date_range("2019-01-02", periods=9, freq="min", tz="UTC")
    missing = ts[[2, 3, 6]]
    runs = minute_runs(missing)
    assert runs.length.tolist() == [2, 1]
    assert runs.start.tolist() == [ts[2], ts[6]]
    observed = ts.difference(missing)
    bars = pd.DataFrame({"bid_c": np.arange(len(observed)), "bid_h": np.arange(len(observed)),
                         "bid_l": np.arange(len(observed))}, index=observed)
    missing_rate, present_rate = preceding_flat_rate(ts, bars)
    assert missing_rate == present_rate == 1.0


def test_lag_correlation_finds_timestamp_shift() -> None:
    ts = pd.date_range("2019-01-02", periods=180, freq="min", tz="UTC")
    prices = pd.Series(100 + np.cumsum(np.random.default_rng(3).normal(size=len(ts))), index=ts)
    delayed = prices.copy()
    delayed.index += pd.Timedelta(minutes=1)
    scores = lag_correlations(prices, delayed)
    assert max(scores, key=lambda row: row[2])[0] == 1
    assert next(value for lag, _, value in scores if lag == 1) > 0.999999
