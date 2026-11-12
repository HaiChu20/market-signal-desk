import numpy as np
import pandas as pd
import pytest

from msd.processing.crypto_perp import (TAKER_FEE, apply_perp_costs,
                                        executable_perp_bars, spread_in_atr)
from msd.processing.labels import label_grid


def test_perp_cost_has_one_spread_fees_and_signed_funding():
    ts = pd.date_range("2022-01-01", periods=3, freq="1h", tz="UTC")
    raw = pd.DataFrame({"ts": ts})
    for field, values in {"o": [100, 100, 101], "h": [100, 100, 101],
                          "l": [100, 100, 101], "c": [100, 100, 101]}.items():
        raw[f"bid_{field}"] = values; raw[f"ask_{field}"] = values
    bars = executable_perp_bars(raw, "ETHUSDT")
    entry_half = float(bars.perp_half_spread.iloc[1]); exit_half = float(bars.perp_half_spread.iloc[2])
    labels = pd.DataFrame([
        {"entry_ts": ts[1], "exit_ts": ts[2], "side": side, "planned_risk": 1.,
         "fill_price": 100 + side*entry_half, "exit_price": 101 - side*exit_half,
         "gross_R": side*((101-side*exit_half)-(100+side*entry_half)), "net_R": 0.}
        for side in (-1, 1)])
    funding = pd.DataFrame({"ts": [ts[2]], "funding_rate": [.001]})
    result = apply_perp_costs(labels, bars, funding)
    expected_spread = entry_half + exit_half
    assert np.allclose(result.spread_R, expected_spread)  # one half at each side
    assert (result.cost_R != 0).all()
    assert result.fee_R.iloc[1] == pytest.approx(
        TAKER_FEE*(labels.fill_price.iloc[1]+labels.exit_price.iloc[1]))
    assert result.funding_R.iloc[1] > 0  # long pays positive funding
    assert result.funding_R.iloc[0] < 0  # short receives it
    assert np.allclose(result.net_R, result.gross_R-result.cost_R)
    assert bars.spread_modeled.all()


def test_spread_atr_never_infinite_and_invalid_atr_is_unlabelable():
    result = spread_in_atr([1., 1., 1., 1.], [2., 0., np.nan, -1.])
    assert result[0] == pytest.approx(.5)
    assert np.isnan(result[1:]).all()
    assert not np.isinf(result).any()
    ts = pd.date_range("2022-01-01", periods=10, freq="1min", tz="UTC")
    raw = pd.DataFrame({"ts": ts})
    for side in ("bid", "ask"):
        for field in "ohlc":
            raw[f"{side}_{field}"] = 100.
    bars = executable_perp_bars(raw, "BTCUSDT")
    assert label_grid(bars, pd.Series(np.zeros(len(bars))), every_minutes=1,
                      financing_per_night=0.).empty
