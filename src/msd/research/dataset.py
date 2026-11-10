"""Causal candidate tables from method-event outcomes and as-of features."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

DEV_END = pd.Timestamp('2023-01-01', tz='UTC')
FEATURES = ('1m_return_bars_5','1m_return_bars_60','1m_realized_vol30',
            '1m_rsi2','1m_atr14','1m_adx14','1m_ema20_distance_atr','1m_volume_z20',
            '15m_return_bars_4','15m_rsi14','1h_return_bars_4','1h_adx14',
            '4h_return_bars_6','1d_return_bars_5','time_sin','time_cos',
            'spread_atr','vix_level','funding_z20')
EVENT_COLUMNS = ('ts','sym','method','side','price','sl','tp','known_at','entry_ts',
                 'entry_price','planned_risk','outcome','exit_ts','R','gross_R','exit_kind')
FORBIDDEN = {'outcome','exit_ts','entry_ts','entry_price','R','gross_R','net_R',
             'label_end_ts','tp_first','exit_price','financing_nights'}


def assemble(events: pd.DataFrame, features: pd.DataFrame, feature_cols=FEATURES) -> pd.DataFrame:
    """Join features available at decision time; event outcomes stay separate."""
    if set(feature_cols) & FORBIDDEN:
        raise AssertionError('Outcome field used as a feature')
    if 'known_at' not in events or 'known_at' not in features:
        raise ValueError('Both events and features require known_at')
    e=events.copy(); f=features.copy()
    for frame in (e,f): frame['known_at']=pd.to_datetime(frame.known_at,utc=True)
    for col in feature_cols:
        if col not in f: f[col]=np.nan
    f=f[['known_at',*feature_cols]].sort_values('known_at').drop_duplicates('known_at',keep='last')
    f=f.rename(columns={'known_at':'feature_known_at'})
    e=e.sort_values('known_at').reset_index(drop=True)
    out=pd.merge_asof(e,f,left_on='known_at',right_on='feature_known_at',direction='backward')
    if (out.feature_known_at>out.known_at).any(): raise AssertionError('Future feature joined')
    out['label_end_ts']=pd.to_datetime(out.exit_ts,utc=True)
    out['tp_first']=out.outcome.eq('tp').astype('int8')
    out['net_R']=pd.to_numeric(out.R,errors='coerce')
    out['gross_R']=pd.to_numeric(out.gross_R,errors='coerce')
    risk=(out.price-out.sl).abs()
    reward=(out.tp-out.price).abs()
    out['SL_R']=1.0
    out['TP_R']=reward/risk
    out['p0']=risk/(risk+reward)
    out['spread_R']=(pd.to_numeric(out.get('spread_atr',pd.Series(0,index=out.index)),errors='coerce')*pd.to_numeric(out.get('1m_atr14',pd.Series(0,index=out.index)),errors='coerce')/pd.to_numeric(out.planned_risk,errors='coerce')).clip(lower=0).fillna(0)
    out['cost_R']=out.spread_R
    rate=np.where(out.sym.eq('BTCUSDT'),.0006,.0002)
    out['financing_R']=rate*pd.to_numeric(out.price,errors='coerce')/pd.to_numeric(out.planned_risk,errors='coerce')
    out['event_key']=out.sym.astype(str)+'|'+out.method.astype(str)+'|'+out.ts.astype(str)+'|'+out.side.astype(str)
    valid=(risk>0)&(reward>0)&out.label_end_ts.notna()&out.net_R.notna()&out.feature_known_at.notna()&out.known_at.lt(DEV_END)
    return out.loc[valid].reset_index(drop=True)


def load_method(method: str, data_root: Path, symbols=('BTCUSDT','USATECHIDXUSD','USA500IDXUSD')):
    """Read monthly source files defensively and return an auditable inventory."""
    import pyarrow.parquet as pq
    tables=[]; manifest=[]
    for sym in symbols:
        event_paths=sorted(p for p in (data_root/'events'/sym).glob('*.parquet') if p.name[:4]<='2022')
        if not event_paths: continue
        event_parts=[]
        for p in event_paths:
            available=set(pq.read_schema(p).names)
            cols=[c for c in EVENT_COLUMNS if c in available]
            if not {'ts','method','known_at','sl','tp','R','exit_ts','outcome'}<=set(cols): continue
            before=p.stat()
            part=pd.read_parquet(p,columns=cols)
            if p.stat().st_mtime_ns!=before.st_mtime_ns: raise RuntimeError(f'Source changed during read: {p}')
            part=part[part.method.eq(method)]
            if len(part):
                event_parts.append(part)
                st=p.stat();manifest.append({'path':str(p),'mtime_ns':st.st_mtime_ns,'size':st.st_size})
        if not event_parts: continue
        events=pd.concat(event_parts,ignore_index=True)
        lo=pd.to_datetime(events.known_at,utc=True).min()-pd.Timedelta(days=2)
        hi=pd.to_datetime(events.known_at,utc=True).max()
        feature_paths=sorted(p for p in (data_root/'features'/sym).glob('*.parquet')
                             if p.name[:4]<='2022' and pd.Timestamp(p.stem+'-01',tz='UTC')<=hi
                             and pd.Timestamp(p.stem+'-01',tz='UTC')+pd.offsets.MonthEnd(1)>=lo)
        feature_parts=[]
        for p in feature_paths:
            available=set(pq.read_schema(p).names)
            cols=['known_at',*(c for c in FEATURES if c in available)]
            before=p.stat()
            feature_parts.append(pd.read_parquet(p,columns=cols))
            if p.stat().st_mtime_ns!=before.st_mtime_ns: raise RuntimeError(f'Source changed during read: {p}')
            st=p.stat();manifest.append({'path':str(p),'mtime_ns':st.st_mtime_ns,'size':st.st_size})
        if feature_parts:
            tables.append(assemble(events,pd.concat(feature_parts,ignore_index=True)))
    return (pd.concat(tables,ignore_index=True) if tables else pd.DataFrame(),manifest)
