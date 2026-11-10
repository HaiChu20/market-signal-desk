"""Real development-period checkpoint equivalence across June/July 2021."""
import importlib
import json
from pathlib import Path

import pandas as pd
import pytest

from test_tournament_methods import NAMES


def _source_data():
    worktree=Path(__file__).resolve().parents[1]
    local=worktree/'data'
    if (local/'features/BTCUSDT/2021-06.parquet').exists(): return local
    for parent in worktree.parents:
        if parent.name=='.cao':
            main=parent.parent/'data'
            if (main/'features/BTCUSDT/2021-06.parquet').exists(): return main
    pytest.skip('BTCUSDT 2021 read-only source data unavailable')


@pytest.mark.slow
def test_all_methods_june_july_2021_checkpoint_equivalence():
    data=_source_data()
    features=[];bars=[]
    for month in (6,7):
        features.append(pd.read_parquet(data/f'features/BTCUSDT/2021-{month:02d}.parquet'))
        b=pd.read_parquet(data/f'bars/binance_um/BTCUSDT/2021-{month:02d}.parquet')
        b['sym']='BTCUSDT';bars.append(b)
    levels=pd.read_parquet(data/'levels/BTCUSDT.parquet')
    whole_features=pd.concat(features,ignore_index=True)
    whole_bars=pd.concat(bars,ignore_index=True)
    no_both={'dow_trend_confirmation','post_macro_event_reaction',
             'post_earnings_index_reaction','intraday_momentum','vix_spike_dip_buy'}
    for name in NAMES:
        mod=importlib.import_module(f'msd.methods.{name}')
        whole=mod.detect(whole_features,levels,whole_bars)
        first,state,_=mod.detect(features[0],levels,bars[0],return_state=True)
        state=json.loads(json.dumps(state,allow_nan=False))
        second,_,_=mod.detect(features[1],levels,bars[1],state=state,return_state=True)
        assert first+second==whole, name
        if name not in no_both:
            assert first and second, name
