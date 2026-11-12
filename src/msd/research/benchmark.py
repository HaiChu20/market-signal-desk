"""Same-entry, same-barrier random-direction benchmark on development bars."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from msd.processing.labels import first_hit_reference

DEV_END=pd.Timestamp('2023-01-01',tz='UTC')
BAR_COLUMNS=['ts',*[f'{side}_{field}' for side in ('bid','ask') for field in 'ohlc']]
CRYPTO = {'BTCUSDT', 'ETHUSDT'}

def random_direction(signals:pd.DataFrame,data_root:Path,seeds=200):
    if signals.empty:return None,0,[]
    try:
        from msd._msd_kernels import first_hit_batch
    except ImportError:
        first_hit_batch=None
    normal=[];opposite=[];manifest=[]
    work=signals.assign(month=pd.to_datetime(signals.ts,utc=True).dt.tz_localize(None).dt.to_period('M'))
    for (symbol,month),group in work.groupby(['sym','month']):
        # Crypto must use the pipeline's annual Dukascopy spread model. Raw
        # Binance OHLC are mid prices and understate executable costs.
        if symbol in CRYPTO or (symbol in {'USATECHIDXUSD','USA500IDXUSD'} and data_root.name=='data'):
            from msd.research.sequence_data import load_executable_1m
            bars=load_executable_1m(symbol,pd.Timestamp(month.start_time,tz='UTC'),
                                    pd.Timestamp((month+1).end_time,tz='UTC'),data_root)
            if bars.empty:continue
            bars=bars[BAR_COLUMNS].sort_values('ts').drop_duplicates('ts').reset_index(drop=True)
        else:
            source='binance_spot' if symbol in CRYPTO else 'dukascopy'
            directory=data_root/'bars'/source/symbol
            parts=[]
            for period in (month,month+1):
                if period.year>=2023:continue
                path=directory/f'{period}.parquet'
                if not path.exists():continue
                before=path.stat();part=pd.read_parquet(path,columns=BAR_COLUMNS)
                if path.stat().st_mtime_ns!=before.st_mtime_ns:raise RuntimeError(f'Source changed during read: {path}')
                parts.append(part)
                manifest.append({'path':str(path),'mtime_ns':before.st_mtime_ns,'size':before.st_size})
            if not parts:continue
            bars=pd.concat(parts,ignore_index=True).sort_values('ts').drop_duplicates('ts').reset_index(drop=True)
        times=pd.to_datetime(bars.ts,utc=True)
        jobs=[];rows=[]
        for row in group.itertuples(index=False):
            ix=int(times.searchsorted(pd.Timestamp(row.ts)))
            if ix>=len(bars) or times.iloc[ix]!=pd.Timestamp(row.ts) or ix+2>=len(bars):continue
            side=-int(row.side)
            stop=float(row.price)-side*abs(float(row.price)-float(row.sl))
            tp=float(row.price)+side*abs(float(row.tp)-float(row.price))
            rate=.0006 if symbol in CRYPTO else .0002
            deadline=pd.Timestamp(row.deadline_ts)
            if deadline>=DEV_END:continue
            jobs.extend([ix,side,float(row.price),stop,tp,int(deadline.timestamp()),2,rate,
                         np.nan,np.nan,1 if symbol in CRYPTO else 0])
            rows.append(row)
        if not rows:continue
        if first_hit_batch is not None:
            packed=bars[[c for c in BAR_COLUMNS if c!='ts']].to_numpy(dtype='<f8')
            stamps=(times.astype('int64').to_numpy()//1_000_000_000).astype('<i8')
            results=np.asarray(first_hit_batch(packed.tobytes(),stamps.tobytes(),jobs,11),dtype=float).reshape(-1,9)
            opposite_r=results[:,4]
        else:
            opposite_r=[]
            for job in np.asarray(jobs,dtype=float).reshape(-1,11):
                result=first_hit_reference(bars,int(job[0]),int(job[1]),job[2],job[3],job[4],
                    delay_bars=2,financing_per_night=job[7],deadline_ts=pd.Timestamp(job[5],unit='s',tz='UTC'),
                    instrument_class='crypto' if symbol in CRYPTO else 'index',detailed=True)
                opposite_r.append(result[3])
        for row,r in zip(rows,opposite_r):
            if np.isfinite(r):normal.append(float(row.net_R));opposite.append(float(r))
    if not normal:return None,0,manifest
    normal=np.asarray(normal);opposite=np.asarray(opposite)
    observed=normal.mean()
    scores=[]
    for seed in range(seeds):
        swap=np.random.default_rng(seed).integers(0,2,size=len(normal),dtype=np.int8).astype(bool)
        scores.append(np.where(swap,opposite,normal).mean())
    return float(100*np.mean(np.asarray(scores)<observed)),len(normal),manifest
