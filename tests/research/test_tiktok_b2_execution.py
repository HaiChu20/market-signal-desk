from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from msd.research.tiktok_b2.execution import (
    ExecutionBars, PositionState, admit_stop, commission_points, execution_bars,
    minimum_stop, replay_fixed_entry, simulate_trade,
)
from msd.research.tiktok_b2.reporting import random_direction, require_holdout


def _bars(mid, *, spread=.25, atr15=20., market="USATECHIDXUSD", model="futures",
          multiplier=1.):
    mid = np.asarray(mid, float)
    ts = pd.date_range("2022-01-03 14:30", periods=len(mid), freq="min", tz="UTC")
    high, low = mid + 1, mid - 1
    return ExecutionBars(ts, mid, high, low, mid,
                         mid - spread / 2, high - spread / 2, low - spread / 2, mid - spread / 2,
                         mid + spread / 2, high + spread / 2, low + spread / 2, mid + spread / 2,
                         np.full(len(mid), atr15), model, market, multiplier, .25,
                         .25 * multiplier, commission_points(market) * multiplier)


def _flat_trade(bars, **overrides):
    values = dict(bars=bars, market="USATECHIDXUSD", strategy="test", params={},
                  side=1, entry_i=0, stop=95., target_r=100., risk_points=5., deadline_i=len(bars.ts)-1)
    values.update(overrides)
    return simulate_trade(**values)


def test_market_fill_pays_half_tick_spread_slippage_and_round_trip_commission():
    trade = _flat_trade(_bars([100., 100.]))
    assert trade["entry_price"] == pytest.approx(100.375)
    assert trade["exit_reason"] == "time"
    assert trade["net_R"] == pytest.approx(-1.25 / 5.)
    assert trade["cost_R"] == pytest.approx(1.25 / 5.)


def test_stop_entry_gaps_adversely_and_market_stop_fill_slippage_is_one_tick():
    bars = _bars([100., 102.], spread=.25)
    bars.ask_h[0] = 100.5
    opened = _flat_trade(bars, entry_type="stop", trigger=101., stop=95., deadline_i=1)
    assert opened["entry_price"] == pytest.approx(102.375)


def test_limit_trade_through_vs_touch_fill():
    bars = _bars([100., 100., 100.], spread=.25)
    # Ask low is 99.90: it touches 100 but does not trade through 99.75.
    bars.ask_l[:] = 99.90
    through = _flat_trade(bars, entry_type="limit", limit_price=100., stop=90., deadline_i=2)
    touch = _flat_trade(bars, entry_type="limit", limit_price=100., stop=90., deadline_i=2,
                        fill_model="touch")
    assert through is None
    assert touch is not None and touch["entry_price"] == 100.


def test_same_bar_stop_and_target_is_a_loss():
    bars = _bars([100.], spread=.25)
    bars.bid_l[0], bars.bid_h[0] = 97., 104.
    trade = _flat_trade(bars, stop=98., target_r=.5, deadline_i=0)
    assert trade["exit_reason"] == "stop"
    assert trade["net_R"] < 0


def test_limit_fill_bar_checks_stop_but_ignores_target():
    bars = _bars([100., 100.], spread=.25)
    bars.ask_l[0] = 99.
    bars.bid_h[0] = 110.
    trade = _flat_trade(bars, entry_type="limit", limit_price=100., stop=90.,
                        target_r=1., risk_points=2., deadline_i=1)
    assert trade["exit_reason"] == "time"


def test_gap_through_stop_fills_at_open_then_slippage():
    bars = _bars([100., 96.], spread=.25)
    bars.bid_o[1] = 95.875
    trade = _flat_trade(bars, stop=98., deadline_i=1)
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == pytest.approx(95.625)


def test_cost_models_and_multipliers_scale_spread_slippage_and_commission():
    class Prepared:
        market = "USATECHIDXUSD"
        ts = pd.date_range("2022-01-03", periods=1, freq="min", tz="UTC")
        mid_o = mid_h = mid_l = mid_c = np.array([100.])
        atr15_at = np.array([20.])
        bars = pd.DataFrame({"bid_o": [99.9], "bid_h": [100.], "bid_l": [99.], "bid_c": [100.],
                             "ask_o": [100.1], "ask_h": [101.], "ask_l": [100.], "ask_c": [100.]})
    fut = execution_bars(Prepared(), Prepared.market, "futures", 1.5)
    duka = execution_bars(Prepared(), Prepared.market, "dukascopy", 2.)
    capital = execution_bars(Prepared(), Prepared.market, "capital", 1.)
    assert fut.ask_o[0] - fut.bid_o[0] == pytest.approx(.375)
    assert fut.slippage == pytest.approx(.375)
    assert fut.commission == pytest.approx(.75)
    assert duka.ask_o[0] - duka.bid_o[0] == pytest.approx(.4)
    assert duka.slippage == pytest.approx(.5)
    assert duka.commission == pytest.approx(1.)
    assert capital.ask_o[0] - capital.bid_o[0] == pytest.approx(1.8)


def test_minimum_stop_floor_and_atr_quarter_filter():
    assert minimum_stop("USATECHIDXUSD", 8.) == 4.
    assert minimum_stop("USATECHIDXUSD", 24.) == 6.
    assert admit_stop("USATECHIDXUSD", 6., 24.)
    assert not admit_stop("USATECHIDXUSD", 5.99, 24.)
    assert minimum_stop("USA500IDXUSD", 8.) == 2.


def test_one_position_state_and_same_side_random_replay_exactness():
    state = PositionState()
    assert state.open("a")
    assert not state.open("b")
    state.close("a")
    assert state.open("b")
    bars = _bars([100., 99., 98.])
    trade = _flat_trade(bars, stop=99., target_r=10., risk_points=1., deadline_i=2)
    replay = replay_fixed_entry(bars, trade, 1)
    assert replay["exit_ts"] == trade["exit_ts"]
    assert replay["net_R"] == pytest.approx(trade["net_R"])
    assert random_direction([trade], bars, seeds=20)["seeds"] == 20


@pytest.mark.parametrize("entry_type", ["market", "limit"])
def test_fixed_entry_replay_preserves_entry_type_fill_cost_and_fill_bar_rule(entry_type):
    bars = _bars([100., 100., 100.], spread=.25)
    if entry_type == "limit":
        bars.ask_l[0] = 99.5  # fills at the limit; its high also crosses target
        bars.bid_h[0] = 105.
        trade = _flat_trade(bars, entry_type="limit", limit_price=100., stop=95.,
                            target_r=.5, risk_points=2., deadline_i=2)
        assert trade["exit_reason"] == "time"  # limit-fill bar may check stop only
        assert trade["_entry_cost"] == 0.
    else:
        trade = _flat_trade(bars, entry_type="market", stop=95.,
                            target_r=.5, risk_points=5., deadline_i=2)
        assert trade["_entry_cost"] == pytest.approx(.375)
    same = replay_fixed_entry(bars, trade, trade["side"])
    opposite = replay_fixed_entry(bars, trade, -trade["side"])
    assert same["exit_ts"] == trade["exit_ts"]
    assert same["exit_reason"] == trade["exit_reason"]
    assert same["net_R"] == pytest.approx(trade["net_R"])
    assert same["entry_cost"] == pytest.approx(trade["_entry_cost"])
    assert opposite["entry_cost"] == pytest.approx(trade["_entry_cost"])


def test_market_entry_beyond_stop_is_skipped_and_counted():
    bars = _bars([94., 94.])
    diagnostics = {"entry_beyond_stop": 0}
    trade = _flat_trade(bars, stop=95., diagnostics=diagnostics)
    assert trade is None
    assert diagnostics["entry_beyond_stop"] == 1


def test_holdout_guard_requires_an_existing_frozen_dev_selection(tmp_path):
    with pytest.raises(FileNotFoundError, match="selection"):
        require_holdout(True, tmp_path / "missing.json")
    selection = tmp_path / "selection.json"
    selection.write_text("{}")
    require_holdout(True, selection)


def test_dsr_configuration_count_uses_batch2_strategy_grids_only():
    from msd.research.tiktok_b2.reporting import project_configuration_count
    count = project_configuration_count()
    assert count["tried"] == sum(count["by_dev_grid"].values())
    assert set(count["by_dev_grid"]) <= {
        "strategy_a", "strategy_b", "strategy_b_alt", "strategy_c", "strategy_d", "E2"}
    assert {"strategy_b", "strategy_b_alt", "E2"} <= set(count["by_dev_grid"])
    assert count["by_dev_grid"]["E2"] == 36
