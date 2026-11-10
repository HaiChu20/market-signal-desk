import gzip
from io import BytesIO
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import pytest

from msd.data.bybit import minute_flow, parse_trades
from msd.data.binance_depth import minute_imbalance, parse_depth


def test_bybit_parser_and_causal_minute_flow(tmp_path):
    path=tmp_path/'trades.csv.gz'
    text=('timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional\n'
          '1654041661,BTCUSDT,Sell,2,100,MinusTick,b,0,2,200\n'
          '1654041601,BTCUSDT,Buy,3,100,PlusTick,a,0,3,300\n'
          '1654041602,BTCUSDT,Sell,1,100,MinusTick,c,0,1,100\n')
    with gzip.open(path,'wt') as output: output.write(text)
    trades=parse_trades(path,'BTCUSDT')
    assert trades.ts.is_monotonic_increasing
    full=minute_flow(trades)
    assert full.buy_volume.tolist()==[3.,0.]
    assert full.sell_volume.tolist()==[1.,2.]
    assert full.delta.tolist()==[2.,-2.]
    assert full.trades.tolist()==[2,1]
    assert (full.known_at-full.ts).eq(pd.Timedelta(minutes=1)).all()
    cut=minute_flow(trades[trades.ts<full.known_at.iloc[0]])
    pd.testing.assert_frame_equal(cut,full.iloc[:1].reset_index(drop=True))
    with pytest.raises(ValueError,match='schema mismatch'):
        with gzip.open(path,'wt') as output: output.write('timestamp,size\n1,2\n')
        parse_trades(path,'BTCUSDT')


def test_binance_depth_parser_asof_and_missing_half_percent(tmp_path):
    path=tmp_path/'depth.zip'
    text=('timestamp,percentage,depth,notional\n'
          '2023-01-01 00:00:05,-1,1,100\n2023-01-01 00:00:05,1,1,50\n'
          '2023-01-01 00:00:05,-2,1,200\n2023-01-01 00:00:05,2,1,100\n'
          '2023-01-01 00:00:32,-1,1,50\n2023-01-01 00:00:32,1,1,50\n'
          '2023-01-01 00:00:32,-2,1,100\n2023-01-01 00:00:32,2,1,100\n'
          '2023-01-01 00:01:10,-1,1,25\n2023-01-01 00:01:10,1,1,75\n')
    with zipfile.ZipFile(path,'w') as archive: archive.writestr('depth.csv',text)
    depth=parse_depth(path)
    full=minute_imbalance(depth)
    assert len(full)==2 and full.known_at.iloc[0]==pd.Timestamp('2023-01-01 00:00:32Z')
    assert np.isnan(full.imbalance_0p5.iloc[0])
    assert full.imbalance_1.iloc[0]==0.
    assert full.imbalance_2.iloc[0]==0.
    earlier=minute_imbalance(depth[depth.ts<pd.Timestamp('2023-01-01 00:00:32Z')])
    assert earlier.imbalance_1.iloc[0]==pytest.approx(1/3)
    # As-of queries must never see the later snapshot.
    at_t=full[full.known_at<=pd.Timestamp('2023-01-01 00:00:20Z')]
    assert at_t.empty
    with pytest.raises(ValueError,match='schema mismatch'):
        with zipfile.ZipFile(path,'w') as archive: archive.writestr('bad.csv','timestamp,depth\nx,1\n')
        parse_depth(path)
