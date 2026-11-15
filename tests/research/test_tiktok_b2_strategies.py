from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from msd.research.tiktok_b2.prep import prepare
from msd.research.tiktok_b2 import strategy_b, strategy_b_alt


def _signal_day(b2=False):
    day = date(2022, 6, 1)
    start = pd.Timestamp(datetime.combine(day, time(9, 30)), tz=ZoneInfo("America/New_York")).tz_convert("UTC")
    warmup = pd.date_range(start - pd.Timedelta(minutes=20), periods=20, freq="min")
    ts = warmup.append(pd.date_range(start, periods=391, freq="min"))
    offset = len(warmup)
    o = [100.] * len(ts)
    h = [101.] * len(ts)
    l = [99.] * len(ts)
    c = [100.] * len(ts)
    if not b2:
        # OR is 99..101.  Breakout j=9:35, FVG completes 9:36,
        # retrace/engulf confirms at 9:38, and the market entry is 9:39.
        o[offset+5], h[offset+5], l[offset+5], c[offset+5] = 101.2, 102., 101.2, 101.9
        o[offset+6], h[offset+6], l[offset+6], c[offset+6] = 102., 102.4, 102.1, 102.2
        o[offset+7], h[offset+7], l[offset+7], c[offset+7] = 102.2, 102.4, 96., 101.9
        o[offset+8], h[offset+8], l[offset+8], c[offset+8] = 101.9, 103., 96., 102.5
        o[offset+9], h[offset+9], l[offset+9], c[offset+9] = 102.5, 102.8, 102.2, 102.6
    else:
        # 30-minute OR is 99..101; first post-range five-minute close > 101.
        for i in range(30, 35):
            o[offset+i], h[offset+i], l[offset+i], c[offset+i] = 104.5, 105., 104., 105.
        o[offset+35], h[offset+35], l[offset+35], c[offset+35] = 104.5, 105., 104., 104.7
    rows = []
    for i, stamp in enumerate(ts):
        for side, offset in (("bid", -.05), ("ask", .05)):
            rows.append((stamp, side, o[i] + offset, h[i] + offset,
                         l[i] + offset, c[i] + offset))
    # 16:00 is the first force-flat market open after RTH.
    wide = []
    for i, stamp in enumerate(ts):
        item = {"ts": stamp}
        for side, offset in (("bid", -.05), ("ask", .05)):
            for field, vals in zip("ohlc", (o, h, l, c)):
                item[f"{side}_{field}"] = vals[i] + offset
        wide.append(item)
    return prepare(pd.DataFrame(wide), "USATECHIDXUSD")


def test_strategy_b_grid_and_first_causal_setup_simulate():
    assert len(strategy_b.GRID) == 36
    data = _signal_day()
    trades, diagnostics = strategy_b.simulate(data, strategy_b.DEFAULT)
    assert diagnostics["signals"] == 1
    assert diagnostics["minimum_stop_skips"] == 0
    assert len(trades) == 1
    assert pd.Timestamp(trades[0]["entry_ts"]).tz_convert("America/New_York").strftime("%H:%M") == "09:39"
    assert trades[0]["exit_reason"] == "time"


def test_b_selects_earliest_engulf_signal_across_gap_sides():
    early = {"signal_i": 19, "side": -1}
    late = {"signal_i": 24, "side": 1}
    assert strategy_b._earliest_signal([late, early]) is early


def test_grouped_b_cells_equal_individual_cell_simulations():
    data = _signal_day()
    cells = [dict(body_ratio=.6, deadline="10:00", target_r=target, stop_mode=stop)
             for stop in ("engulf", "fvg") for target in (2., 3.)]
    grouped = strategy_b.simulate_group(data, cells)
    by_cell = {tuple(sorted(params.items())): (trades, diag)
               for params, trades, diag in grouped}
    for params in cells:
        trades, diagnostics = strategy_b.simulate(data, params)
        grouped_trades, grouped_diag = by_cell[tuple(sorted(params.items()))]
        assert [(row["entry_ts"], row["exit_ts"], row["net_R"]) for row in grouped_trades] == [
            (row["entry_ts"], row["exit_ts"], row["net_R"]) for row in trades]
        assert grouped_diag == diagnostics


def test_strategy_b_alt_first_30m_or_breakout_is_next_bar_entry():
    assert len(strategy_b_alt.GRID) == 6
    data = _signal_day(b2=True)
    row = data.rth_days.loc[data.rth_days.day == date(2022, 6, 1)].iloc[0]
    diagnostics = {"bad_opening_range": 0, "minimum_stop_skips": 0}
    import types
    order = strategy_b_alt._signal(data, types.SimpleNamespace(**row.to_dict()),
                                   strategy_b_alt.DEFAULT, diagnostics,
                                   (pd.DatetimeIndex(data.five.ts),
                                    (pd.DatetimeIndex(data.five.ts).tz_convert("America/New_York").hour * 60 +
                                     pd.DatetimeIndex(data.five.ts).tz_convert("America/New_York").minute),
                                    (data.five.bid_c.to_numpy() + data.five.ask_c.to_numpy()) / 2,
                                    (data.five.bid_h.to_numpy() + data.five.ask_h.to_numpy()) / 2,
                                    (data.five.bid_l.to_numpy() + data.five.ask_l.to_numpy()) / 2))
    assert order is not None
    assert data.ny[order["entry_i"]].strftime("%H:%M") == "10:05"
    trades, diagnostics = strategy_b_alt.simulate(data, strategy_b_alt.DEFAULT)
    assert len(trades) == 1
    assert diagnostics["signals"] == 1
