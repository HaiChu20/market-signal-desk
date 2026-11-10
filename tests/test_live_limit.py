"""Limit lifecycle parity with the production Rust label kernel."""
import sys
import types

import numpy as np
import pandas as pd
import pytest

from msd.live.engine import SignalEngine
from msd.live.store import SignalStore


def _module(order):
    module = types.ModuleType('test_limit_strategy')
    module.NAME = 'test_limit_strategy'
    module.SYMBOLS = ('BTCUSDT',)
    module.RESOLUTION = 'MINUTE'
    module.orders = lambda bars: [order]
    sys.modules[module.__name__] = module
    return module


def _bars(kind='tp'):
    ts = pd.date_range('2021-06-01', periods=4, freq='min', tz='UTC')
    # The fill bar crosses the target, which must not trigger TP yet.
    quotes = [(100, 101, 99, 100), (100, 104, 99, 101),
              (101, 104, 99, 103), (103, 104, 101, 102)]
    if kind == 'stop':
        quotes[1] = (100, 104, 95, 99)
    if kind == 'gap':
        quotes[1] = (99, 104, 98.5, 101)
    rows = []
    for stamp, (op, hi, lo, close) in zip(ts, quotes):
        rows.append({'ts': stamp, 'bid_o': op, 'bid_h': hi, 'bid_l': lo, 'bid_c': close,
                     'ask_o': op + .2, 'ask_h': hi + .2, 'ask_l': lo + .2, 'ask_c': close + .2,
                     'volume': 1.})
    return pd.DataFrame(rows)


def _run(bars, tmp_path, *, side=1, limit=100.2, stop=98., tp=103., expiry=None,
         restart=False, cancel=False, deadline=None):
    expiry = expiry or bars.ts.iloc[-1] + pd.Timedelta(minutes=1)
    order = {'decision_ts': bars.ts.iloc[0], 'side': side, 'entry_type': 'limit',
             'entry_price': limit, 'stop': stop, 'tp': tp, 'expiry_ts': expiry,
             'exit_ts': deadline, 'confidence': .8}
    module = _module(order)
    path = tmp_path / 'signals.db'
    messages = []
    store = SignalStore(path)
    config = {'module': module.__name__, 'enabled': True}
    engine = SignalEngine(store, messages.append, instruments=[{'symbol': 'BTCUSDT'}], strategies=[config])
    engine.process_completed('BTCUSDT', 'MINUTE', bars.iloc[0].to_dict())
    engine.process_forming('BTCUSDT', 'MINUTE', bars.iloc[1].to_dict())
    key = f"BTCUSDT:{module.NAME}:{bars.ts.iloc[0].isoformat()}"
    assert store.get(key)['status'] == 'pending'
    engine.process_forming('BTCUSDT', 'MINUTE', bars.iloc[1].to_dict())
    assert sum('LIMIT' in message and 'valid until' in message for message in messages) == 1
    action = 'BUY LIMIT' if side > 0 else 'SELL LIMIT'
    assert any(action in message and 'SL ' in message and 'TP ' in message
               and 'Confidence' in message for message in messages)
    if cancel:
        assert engine.cancel_pending(key) and not engine.cancel_pending(key)
    if restart:
        store.close()
        store = SignalStore(path)
        engine = SignalEngine(store, messages.append, instruments=[{'symbol': 'BTCUSDT'}], strategies=[config])
        engine.process_completed('BTCUSDT', 'MINUTE', bars.iloc[0].to_dict())
        engine.process_forming('BTCUSDT', 'MINUTE', bars.iloc[1].to_dict())
        assert sum('LIMIT' in message and 'valid until' in message for message in messages) == 1
    for bar in bars.iloc[1:].to_dict('records'):
        engine.process_completed('BTCUSDT', 'MINUTE', bar)
    saved = store.get(key)
    store.close()
    return saved, messages


def _kernel(bars, side, limit, stop, tp, expiry, deadline=None):
    from msd._msd_kernels import first_hit
    cols = ['bid_o', 'bid_h', 'bid_l', 'bid_c', 'ask_o', 'ask_h', 'ask_l', 'ask_c']
    stamps = (bars.ts.astype('int64') // 1_000_000_000).tolist()
    return first_hit(bars[cols].to_numpy(float).tolist(), stamps, 0, side,
                     float((bars.bid_c.iloc[0] + bars.ask_c.iloc[0]) / 2), stop, tp,
                     delay_bars=1, limit_price=limit, expiry_ts=int(expiry.timestamp()),
                     deadline_ts=None if deadline is None else int(deadline.timestamp()),
                     instrument_class='crypto')


@pytest.mark.parametrize('kind,expected_status', [('tp', 'tp'), ('stop', 'stop'), ('gap', 'tp')])
def test_limit_fill_exit_matches_rust_kernel(tmp_path, kind, expected_status):
    bars = _bars(kind)
    expiry = bars.ts.iloc[-1] + pd.Timedelta(minutes=1)
    saved, messages = _run(bars, tmp_path, expiry=expiry, restart=(kind == 'tp'))
    expected = _kernel(bars, 1, 100.2, 98., 103., expiry)
    outcome, exit_i, fill, exit_price, net_r, gross_r, _, entry_i, risk = expected
    assert saved['status'] == expected_status == {1: 'tp', -1: 'stop', 0: 'time'}[outcome]
    assert saved['entry_ts'] == bars.ts.iloc[entry_i].isoformat()
    assert saved['entry_price'] == pytest.approx(fill)
    assert saved['planned_risk'] == pytest.approx(risk)
    assert saved['exit_ts'] == bars.ts.iloc[exit_i].isoformat()
    assert saved['exit_price'] == pytest.approx(exit_price)
    assert saved['realized_r'] == pytest.approx(net_r)
    assert sum('LIMIT FILLED' in message for message in messages) == 1


def test_limit_expiry_and_cancel(tmp_path):
    bars = _bars()
    expiry = bars.ts.iloc[2]
    saved, messages = _run(bars, tmp_path / 'expiry', limit=90., stop=88., expiry=expiry, restart=True)
    assert _kernel(bars, 1, 90., 88., 103., expiry)[0] == -2
    assert saved['status'] == 'expired' and saved['entry_ts'] is None
    assert sum('LIMIT EXPIRED' in message for message in messages) == 1
    saved, messages = _run(bars, tmp_path / 'cancel', limit=90., stop=88., expiry=expiry, cancel=True)
    assert saved['status'] == 'cancelled' and saved['entry_ts'] is None
    assert sum('LIMIT CANCELLED' in message for message in messages) == 1


def test_real_btc_limit_matches_rust_kernel(tmp_path):
    path = '/Users/bfhach/Projects/market-signal-desk/data/bars/binance_spot/BTCUSDT/2021-06.parquet'
    from pathlib import Path
    if not Path(path).exists():
        pytest.skip('read-only BTC bars unavailable')
    bars = pd.read_parquet(path).iloc[:25].reset_index(drop=True)
    limit = float(bars.ask_o.iloc[1])
    stop = limit - 10000.
    tp = limit + 10000.
    expiry = bars.ts.iloc[10]
    deadline = bars.ts.iloc[20]
    saved, _ = _run(bars, tmp_path, limit=limit, stop=stop, tp=tp,
                    expiry=expiry, deadline=deadline)
    outcome, exit_i, fill, exit_price, net_r, _, _, entry_i, risk = _kernel(
        bars, 1, limit, stop, tp, expiry, deadline)
    assert saved['status'] == {1: 'tp', -1: 'stop', 0: 'time'}[outcome]
    assert saved['entry_ts'] == bars.ts.iloc[entry_i].isoformat()
    assert saved['entry_price'] == pytest.approx(fill)
    assert saved['planned_risk'] == pytest.approx(risk)
    assert saved['exit_ts'] == bars.ts.iloc[exit_i].isoformat()
    assert saved['exit_price'] == pytest.approx(exit_price)
    assert saved['realized_r'] == pytest.approx(net_r)


def test_short_limit_matches_rust_kernel(tmp_path):
    bars = _bars()
    expiry = bars.ts.iloc[-1] + pd.Timedelta(minutes=1)
    saved, _ = _run(bars, tmp_path, side=-1, limit=101., stop=105., tp=100., expiry=expiry)
    outcome, exit_i, fill, exit_price, net_r, _, _, entry_i, risk = _kernel(
        bars, -1, 101., 105., 100., expiry)
    assert saved['status'] == {1: 'tp', -1: 'stop', 0: 'time'}[outcome]
    assert saved['entry_ts'] == bars.ts.iloc[entry_i].isoformat()
    assert saved['entry_price'] == pytest.approx(fill)
    assert saved['planned_risk'] == pytest.approx(risk)
    assert saved['exit_ts'] == bars.ts.iloc[exit_i].isoformat()
    assert saved['exit_price'] == pytest.approx(exit_price)
    assert saved['realized_r'] == pytest.approx(net_r)
