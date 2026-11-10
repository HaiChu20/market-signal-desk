"""Binance USD-M bookDepth snapshots; only published bands are measured."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from .archive_download import fetch_plan

RAW_ROOT = Path('data/raw/binance/bookDepth')
AUX_ROOT = Path('data/aux/binance_depth')
FIRST_VERIFIED = date(2023,1,1)
BANDS = (0.5,1,2)


def archive_url(symbol: str, day: date) -> str:
    if symbol not in {'BTCUSDT','ETHUSDT'} or day < FIRST_VERIFIED:
        raise ValueError('symbol or date outside verified Binance depth range')
    return f'https://data.binance.vision/data/futures/um/daily/bookDepth/{symbol}/{symbol}-bookDepth-{day:%Y-%m-%d}.zip'


def parse_depth(path: str | Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith('.csv')]
        if len(names) != 1: raise ValueError('expected one depth CSV')
        with archive.open(names[0]) as stream:
            frame = pd.read_csv(stream)
    required = {'timestamp','percentage','depth','notional'}
    if not required.issubset(frame):
        raise ValueError(f'Binance bookDepth schema mismatch: {sorted(required-set(frame))}')
    frame['ts'] = pd.to_datetime(frame.timestamp, utc=True, errors='coerce')
    frame['percentage'] = pd.to_numeric(frame.percentage,errors='raise')
    frame['notional'] = pd.to_numeric(frame.notional,errors='raise')
    if frame.ts.isna().any() or not np.isfinite(frame.notional).all() or (frame.notional < 0).any():
        raise ValueError('invalid depth snapshot')
    return frame[['ts','percentage','notional']].sort_values(['ts','percentage']).reset_index(drop=True)


def minute_imbalance(depth: pd.DataFrame) -> pd.DataFrame:
    """Latest observed snapshot per minute; known_at is its actual timestamp."""
    if depth.empty:
        return pd.DataFrame(columns=['ts','known_at',*(f'imbalance_{str(b).replace(".","p")}' for b in BANDS)])
    frame = depth.copy()
    wide = frame.pivot_table(index='ts',columns='percentage',values='notional',aggfunc='last')
    result = pd.DataFrame({'known_at':wide.index})
    for band in BANDS:
        name = f'imbalance_{str(band).replace(".","p")}'
        if -band in wide and band in wide:
            bid,ask = wide[-band].to_numpy(float),wide[band].to_numpy(float)
            result[name] = np.divide(bid-ask,bid+ask,out=np.full(len(wide),np.nan),where=(bid+ask)>0)
        else:
            result[name] = np.nan  # The archive has no ±0.5% band; never interpolate it.
    result['ts'] = pd.to_datetime(result.known_at,utc=True).dt.floor('min')
    return result.sort_values('known_at').drop_duplicates('ts',keep='last')[
        ['ts','known_at','imbalance_0p5','imbalance_1','imbalance_2']].reset_index(drop=True)


def download_days(symbol: str, start: date, end: date,
                  raw_root: Path=RAW_ROOT, aux_root: Path=AUX_ROOT) -> list[Path]:
    days = [start + timedelta(days=i) for i in range((end-start).days + 1)]
    items = [(archive_url(symbol,day), raw_root/symbol/f'{symbol}-bookDepth-{day:%Y-%m-%d}.zip',
              archive_url(symbol,day)+'.CHECKSUM') for day in days]
    raw_paths = fetch_plan(items)
    outputs = []
    for day,path in zip(days,raw_paths):
        data = minute_imbalance(parse_depth(path))
        output = aux_root/symbol/f'{day:%Y-%m-%d}.parquet'
        output.parent.mkdir(parents=True,exist_ok=True)
        data.to_parquet(output,index=False)
        outputs.append(output)
    return outputs


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--symbol',choices=('BTCUSDT','ETHUSDT'),required=True)
    parser.add_argument('--start',type=date.fromisoformat,required=True)
    parser.add_argument('--end',type=date.fromisoformat,required=True)
    args=parser.parse_args()
    if args.end<args.start:parser.error('end before start')
    print(download_days(args.symbol,args.start,args.end))


if __name__=='__main__': main()
