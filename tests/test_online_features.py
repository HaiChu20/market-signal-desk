"""Real read-only BTC replay; run with: uv run pytest -m slow tests/test_online_features.py."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from msd.live.online_features import OnlineFeatures
from msd.processing.features import build_features
from msd.processing.levels import build_levels, levels_asof
from msd.processing.pipeline import methods_for_symbol
from msd.processing.timeframes import build_all_timeframes

SOURCE = Path('/Users/bfhach/Projects/market-signal-desk/data/bars/binance_spot/BTCUSDT/2021-06.parquet')


@pytest.mark.slow
def test_real_btc_online_equals_offline_event_stretch():
    if not SOURCE.exists():
        pytest.skip('read-only real BTC archive unavailable')
    bars = pd.read_parquet(SOURCE)
    bars = bars[(bars.ts >= '2021-06-01') & (bars.ts < '2021-06-04')].reset_index(drop=True)
    tfs = build_all_timeframes(bars, 'BTCUSDT')
    levels = build_levels(bars, 'BTCUSDT', tfs)
    features = build_features(bars, 'BTCUSDT', tfs, levels)
    offline_events = [event for method in methods_for_symbol('BTCUSDT')
                      for event in method.detect(features, levels, bars)]
    assert offline_events, 'replay must exercise a pilot method event'
    target = min(int(bars.ts.searchsorted(event['ts'])) for event in offline_events
                 if event['ts'] >= pd.Timestamp('2021-06-02 01:00', tz='UTC'))
    start, end = max(1, target - 30), min(len(bars), target + 31)
    engine = OnlineFeatures('BTCUSDT', bars.iloc[:start])
    seen = []
    for i in range(start, end):
        online = engine.update(bars.iloc[i].to_dict())
        expected = features.iloc[i]
        assert online.features.index.tolist() == expected.index.tolist()
        for column in expected.index:
            if column in {'ts', 'known_at'} or column.endswith('_bar_known_at'):
                assert online.features[column] == expected[column]
            else:
                a, b = online.features[column], expected[column]
                if pd.isna(a) and pd.isna(b):
                    continue
                # Pandas can round a rolling value one float32 ULP apart.
                np.testing.assert_array_max_ulp(np.float32(a), np.float32(b), maxulp=1)
        expected_levels = levels_asof(levels, bars.ts.iloc[i] + pd.Timedelta(minutes=1))
        pd.testing.assert_frame_equal(online.levels.sort_values('level_id').reset_index(drop=True),
                                      expected_levels.sort_values('level_id').reset_index(drop=True), check_like=True)
        expected_events = [event for event in offline_events if event['ts'] == bars.ts.iloc[i]]
        def normalize(event):
            return {k: (v.isoformat() if isinstance(v, pd.Timestamp) else v)
                    for k, v in event.items() if k != 'sym'}
        assert [normalize(event) for event in online.events] == [normalize(event) for event in expected_events]
        seen.extend(online.events)
    assert seen
