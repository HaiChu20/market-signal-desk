"""Bybit public taker-side trade archives and causal minute flow."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .archive_download import fetch_plan

RAW_ROOT = Path('data/raw/bybit')
BAR_ROOT = Path('data/bars/bybit_flow')
FIRST_DATE = {'BTCUSDT': date(2020,3,25), 'ETHUSDT': date(2020,10,21)}
REQUIRED = {'timestamp','symbol','side','size','price','trdMatchID'}


def archive_url(symbol: str, day: date) -> str:
    if symbol not in FIRST_DATE or day < FIRST_DATE[symbol]:
        raise ValueError('symbol or date outside verified Bybit archive range')
    return f'https://public.bybit.com/trading/{symbol}/{symbol}{day:%Y-%m-%d}.csv.gz'


def parse_trades(path: str | Path, symbol: str) -> pd.DataFrame:
    frame = pd.read_csv(path, compression='gzip')
    if not REQUIRED.issubset(frame.columns):
        raise ValueError(f'Bybit schema mismatch: {sorted(REQUIRED - set(frame.columns))}')
    frame = frame.loc[frame.symbol.eq(symbol), ['timestamp','side','size','trdMatchID']].copy()
    if not frame.side.isin(['Buy','Sell']).all():
        raise ValueError('unexpected Bybit taker side')
    frame['ts'] = pd.to_datetime(pd.to_numeric(frame.timestamp), unit='s', utc=True)
    frame['size'] = pd.to_numeric(frame['size'], errors='raise')
    if (frame['size'] < 0).any() or frame.ts.isna().any():
        raise ValueError('invalid Bybit trade value')
    return frame[['ts','side','size','trdMatchID']].sort_values('ts').reset_index(drop=True)


def minute_flow(trades: pd.DataFrame) -> pd.DataFrame:
    """Taker Buy/Sell base-volume aggregates known only after minute close."""
    if trades.empty:
        return pd.DataFrame(columns=['ts','known_at','buy_volume','sell_volume','delta','trades'])
    data = trades.copy()
    data['minute'] = pd.to_datetime(data.ts,utc=True).dt.floor('min')
    data['buy_volume'] = data['size'].where(data.side.eq('Buy'),0.)
    data['sell_volume'] = data['size'].where(data.side.eq('Sell'),0.)
    result = data.groupby('minute',sort=True).agg(buy_volume=('buy_volume','sum'),
        sell_volume=('sell_volume','sum'),trades=('trdMatchID','count')).reset_index(names='ts')
    result['known_at'] = result.ts + pd.Timedelta(minutes=1)
    result['delta'] = result.buy_volume - result.sell_volume
    return result[['ts','known_at','buy_volume','sell_volume','delta','trades']]


def download_days(symbol: str, start: date, end: date,
                  raw_root: Path = RAW_ROOT, bar_root: Path = BAR_ROOT) -> list[Path]:
    days = [start + timedelta(days=i) for i in range((end-start).days + 1)]
    items = [(archive_url(symbol, day), raw_root / symbol / f'{symbol}{day:%Y-%m-%d}.csv.gz', None)
             for day in days]
    raw_paths = fetch_plan(items)
    outputs = []
    for day, path in zip(days, raw_paths):
        flow = minute_flow(parse_trades(path,symbol))
        output = bar_root / symbol / f'{day:%Y-%m-%d}.parquet'
        output.parent.mkdir(parents=True,exist_ok=True)
        flow.to_parquet(output,index=False)
        outputs.append(output)
    return outputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', choices=tuple(FIRST_DATE), required=True)
    parser.add_argument('--start', type=date.fromisoformat, required=True)
    parser.add_argument('--end', type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if args.end < args.start: parser.error('end before start')
    print(download_days(args.symbol,args.start,args.end))


if __name__ == '__main__': main()
