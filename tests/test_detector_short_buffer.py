"""A five-bar lag must preserve the array length during online replay."""
import numpy as np
import pandas as pd

from msd.methods._detectors import detect_rule


def _inputs(n):
    ts = pd.date_range('2025-01-01', periods=n, freq='min', tz='UTC')
    prices = np.full(n, 100.)
    if n >= 6: prices[5] = 103.
    bars = pd.DataFrame({'ts': ts, 'bid_o': prices, 'bid_h': prices+.5,
                         'bid_l': prices-.5, 'bid_c': prices, 'sym': 'BTCUSDT'})
    since = np.full(n, np.nan)
    if n >= 6: since[4:6] = [4., 5.]
    features = pd.DataFrame({'ts': ts, 'known_at': ts+pd.Timedelta(minutes=1),
                             '1m_atr14': np.full(n, 2.),
                             'macro_minutes_since_event': since})
    return features, bars


def test_macro_five_bar_lag_handles_two_row_online_chunk_and_keeps_full_rule():
    short_features, short_bars = _inputs(2)
    assert detect_rule('post_macro_event_reaction', short_features, pd.DataFrame(), short_bars) == []
    full_features, full_bars = _inputs(6)
    events = detect_rule('post_macro_event_reaction', full_features, pd.DataFrame(), full_bars)
    assert events and events[0]['ts'] == full_bars.ts.iloc[5]
    assert events[0]['side'] == 1
