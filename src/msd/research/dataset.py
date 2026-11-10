"""Causal candidate tables from method-event outcomes and as-of features."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

DEV_END = pd.Timestamp('2023-01-01', tz='UTC')
FEATURES_BY_METHOD: dict[str, tuple[str, ...] | None] = {
    'sr_touch': None, 'liquidity_sweep': None, 'rsi2_mean_reversion': None,
}
EVENT_COLUMNS = ('ts','sym','method','side','price','sl','tp','known_at','entry_ts','deadline_ts',
                 'entry_price','planned_risk','outcome','exit_ts','R','gross_R','exit_kind')
FORBIDDEN = {'outcome','exit_ts','entry_ts','entry_price','R','gross_R','net_R',
             'label_end_ts','tp_first','exit_price','financing_nights'}


def assemble(events: pd.DataFrame, features: pd.DataFrame, feature_cols=None, *, return_audit=False):
    """Join features available at decision time; event outcomes stay separate."""
    if feature_cols is None:
        feature_cols=[c for c in features if c not in {'ts','known_at'} and pd.api.types.is_numeric_dtype(features[c])]
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
    conditions={'invalid_geometry':~((risk>0)&(reward>0)),
        'missing_outcome':out.label_end_ts.isna()|out.net_R.isna(),
        'missing_asof_feature':out.feature_known_at.isna(),
        'event_after_dev':~out.known_at.lt(DEV_END),
        'label_extends_beyond_dev':~out.label_end_ts.lt(DEV_END)}
    valid=~pd.DataFrame(conditions).any(axis=1)
    audit={k:int(v.sum()) for k,v in conditions.items()}
    result=out.loc[valid].reset_index(drop=True)
    return (result,audit) if return_audit else result


def load_method(method: str, data_root: Path, symbols=('BTCUSDT','USATECHIDXUSD','USA500IDXUSD'), *, return_audit=False):
    """Read monthly source files defensively and return an auditable inventory."""
    import pyarrow.parquet as pq
    tables=[]; manifest=[];audit={'events':0,'candidate_rows':0,'assembled_rows':0,'drops':{}}
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
        audit['events']+=len(events[['sym','ts','side']].drop_duplicates())
        audit['candidate_rows']+=len(events)
        lo=pd.to_datetime(events.known_at,utc=True).min()-pd.Timedelta(days=2)
        hi=pd.to_datetime(events.known_at,utc=True).max()
        feature_paths=sorted(p for p in (data_root/'features'/sym).glob('*.parquet')
                             if p.name[:4]<='2022' and pd.Timestamp(p.stem+'-01',tz='UTC')<=hi
                             and pd.Timestamp(p.stem+'-01',tz='UTC')+pd.offsets.MonthEnd(1)>=lo)
        feature_parts=[]
        for p in feature_paths:
            available=set(pq.read_schema(p).names)
            import pyarrow as pa
            cols=['known_at',*(field.name for field in pq.read_schema(p)
                if field.name not in {'ts','known_at'} and
                (pa.types.is_integer(field.type) or pa.types.is_floating(field.type) or pa.types.is_boolean(field.type)))]
            before=p.stat()
            feature_parts.append(pd.read_parquet(p,columns=cols))
            if p.stat().st_mtime_ns!=before.st_mtime_ns: raise RuntimeError(f'Source changed during read: {p}')
            st=p.stat();manifest.append({'path':str(p),'mtime_ns':st.st_mtime_ns,'size':st.st_size})
        if feature_parts:
            result,drops=assemble(events,pd.concat(feature_parts,ignore_index=True),return_audit=True)
            tables.append(result)
            audit['assembled_rows']+=len(result)
            for key,value in drops.items():audit['drops'][key]=audit['drops'].get(key,0)+value
    table=pd.concat(tables,ignore_index=True) if tables else pd.DataFrame()
    return (table,manifest,audit) if return_audit else (table,manifest)
