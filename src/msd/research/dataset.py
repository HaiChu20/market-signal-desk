"""Causal DEV candidate tables from event outcomes and as-of feature layers."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from msd.data.flow_features import DEPTH_COLUMNS

DEV_END = pd.Timestamp('2023-01-01', tz='UTC')
FEATURES_BY_METHOD: dict[str, tuple[str, ...] | None] = {
    'sr_touch': None, 'liquidity_sweep': None, 'rsi2_mean_reversion': None,
}
EVENT_ATTRIBUTES = ('variant','pattern','cluster_id','cluster_price','cluster_strength',
                    'cluster_types','cluster_age_minutes','approach_direction','level_type',
                    'level_price','zone_edge','line_slope_per_minute','return_20d','return_60d',
                    'entry_type','limit_price','expiry_at','natural_sl','natural_tp')
EVENT_COLUMNS = ('ts','sym','method','side','price','sl','tp','known_at','entry_ts','deadline_ts',
                 'entry_price','planned_risk','outcome','exit_ts','exit_price','R','gross_R',
                 'financing_nights','exit_kind','side_candidates',*EVENT_ATTRIBUTES)
FORBIDDEN = {'outcome','exit_ts','entry_ts','entry_price','R','gross_R','net_R',
             'label_end_ts','tp_first','exit_price','financing_nights','deadline_ts'}
SYMBOLS = ('USATECHIDXUSD','USA500IDXUSD','XAUUSD','BTCUSDT','ETHUSDT')


def _utc(frame: pd.DataFrame, column='known_at') -> pd.DataFrame:
    result=frame.copy()
    result[column]=pd.to_datetime(result[column],utc=True).astype('datetime64[ns, UTC]')
    return result


def assert_dev_period(events: pd.DataFrame) -> None:
    """Hard-fail instead of silently admitting labels from Test or Final."""
    known=pd.to_datetime(events.known_at,utc=True)
    ended=pd.to_datetime(events.exit_ts,utc=True)
    if known.ge(DEV_END).any():
        raise ValueError('DEV data contains a decision at or after 2023-01-01')
    if ended.ge(DEV_END).any():
        raise ValueError('DEV data contains a label_end_ts at or after 2023-01-01')


def _numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame if column not in {'ts','known_at'} and
            (pd.api.types.is_numeric_dtype(frame[column]) or
             pd.api.types.is_bool_dtype(frame[column]))]


def _asof(events: pd.DataFrame, features: pd.DataFrame, columns: list[str], stamp: str) -> pd.DataFrame:
    """Left as-of join that never drops an event and exposes the causal clock."""
    left=_utc(events).sort_values('known_at',kind='stable')
    if features.empty:
        out=left.copy();out[stamp]=pd.NaT
        for column in columns: out[column]=np.nan
        return out
    right=_utc(features)
    missing=[column for column in columns if column not in right]
    for column in missing:right[column]=np.nan
    right=right[['known_at',*columns]].sort_values('known_at',kind='stable')
    right=right.drop_duplicates('known_at',keep='last').rename(columns={'known_at':stamp})
    overlap=set(columns)&set(left.columns)
    if overlap:
        raise ValueError(f'Feature columns collide with event columns: {sorted(overlap)}')
    out=pd.merge_asof(left,right,left_on='known_at',right_on=stamp,direction='backward')
    if (out[stamp]>out.known_at).any():raise AssertionError(f'Future {stamp} joined')
    return out


def assemble(events: pd.DataFrame, features: pd.DataFrame, feature_cols=None, *,
             supplemental: dict[str,pd.DataFrame] | None=None, return_audit=False,
             dev_mode=True):
    """Join features available at decision time; event outcomes stay separate."""
    if dev_mode: assert_dev_period(events)
    if feature_cols is None: feature_cols=_numeric_columns(features)
    if set(feature_cols) & FORBIDDEN:
        raise AssertionError('Outcome field used as a feature')
    if 'known_at' not in events or 'known_at' not in features:
        raise ValueError('Both events and features require known_at')
    out=_asof(events,features,list(feature_cols),'feature_known_at')
    for name,frame in (supplemental or {}).items():
        # Layer readers expose only approved numeric/boolean columns.  Keep
        # their schema even when the requested period has no source files so
        # unavailable coverage is represented by NaN rather than disappearing.
        columns=[column for column in frame if column not in {'ts','known_at'}]
        out=_asof(out,frame,columns,f'{name}_feature_known_at')
    out['label_end_ts']=pd.to_datetime(out.exit_ts,utc=True)
    out['tp_first']=out.outcome.eq('tp').astype('int8')
    out['net_R']=pd.to_numeric(out.R,errors='coerce')
    out['gross_R']=pd.to_numeric(out.gross_R,errors='coerce')
    risk=(out.price-out.sl).abs()
    reward=(out.tp-out.price).abs()
    out['SL_R']=1.0
    out['TP_R']=reward/risk
    out['p0']=risk/(risk+reward)
    spread_atr=pd.to_numeric(out.get('spread_atr',pd.Series(np.nan,index=out.index)),errors='coerce')
    out['spread_R']=(spread_atr*pd.to_numeric(out.get('1m_atr14',pd.Series(np.nan,index=out.index)),errors='coerce')/pd.to_numeric(out.planned_risk,errors='coerce')).clip(lower=0)
    crypto=out.sym.isin(['BTCUSDT','ETHUSDT'])
    if out.loc[crypto,'spread_R'].isna().any():
        raise ValueError('Crypto candidate has no executable spread cost')
    out['spread_R']=out.spread_R.fillna(0)
    out['cost_R']=out.spread_R
    rate=np.where(out.sym.isin(['BTCUSDT','ETHUSDT']),.0006,
                  np.where(out.sym.eq('XAUUSD'),.00015,.0002))
    out['financing_R']=rate*pd.to_numeric(out.price,errors='coerce')/pd.to_numeric(out.planned_risk,errors='coerce')
    out['event_key']=out.sym.astype(str)+'|'+out.method.astype(str)+'|'+out.ts.astype(str)+'|'+out.side.astype(str)
    conditions={'invalid_geometry':~((risk>0)&(reward>0)),
        'missing_outcome':out.label_end_ts.isna()|out.net_R.isna()}
    valid=~pd.DataFrame(conditions).any(axis=1)
    audit={k:int(v.sum()) for k,v in conditions.items()}
    result=out.loc[valid].reset_index(drop=True)
    return (result,audit) if return_audit else result


def _schema_columns(paths: list[Path], *, depth=False) -> list[str]:
    if not paths:return []
    names=[]
    for field in pq.read_schema(paths[0]):
        if field.name in {'ts','known_at'}:continue
        if depth:
            mapped='depth_coverage' if field.name=='coverage' else field.name
            if mapped in DEPTH_COLUMNS:names.append(mapped)
        elif pa.types.is_integer(field.type) or pa.types.is_floating(field.type) or pa.types.is_boolean(field.type):
            names.append(field.name)
    return list(dict.fromkeys(names))


def _read_layer(root: Path, events: pd.DataFrame, *, depth=False) -> tuple[pd.DataFrame,list[dict]]:
    """Read only event months; missing layer months remain explicit NaN."""
    paths=sorted(root.glob('*.parquet'))
    columns=list(DEPTH_COLUMNS) if depth else _schema_columns(paths,depth=False)
    if not paths:return pd.DataFrame(columns=['known_at',*columns]),[]
    by_stem={path.stem:path for path in paths};parts=[];manifest=[]
    months=pd.to_datetime(events.known_at,utc=True).dt.strftime('%Y-%m').unique()
    event_known=pd.to_datetime(events.known_at,utc=True)
    for month in sorted(months):
        path=by_stem.get(month)
        if path is None:continue
        available=set(pq.read_schema(path).names)
        raw_columns=['known_at']
        for column in columns:
            source='coverage' if depth and column=='depth_coverage' else column
            if source in available:raw_columns.append(source)
        before=path.stat();part=pd.read_parquet(path,columns=raw_columns)
        if path.stat().st_mtime_ns!=before.st_mtime_ns:raise RuntimeError(f'Source changed during read: {path}')
        if depth and 'coverage' in part:part=part.rename(columns={'coverage':'depth_coverage'})
        for column in columns:
            if column not in part:part[column]=np.nan
        # Keep only rows that can win an as-of join for this method's event
        # timestamps. Reading remains defensive, while concatenated memory is
        # proportional to candidates rather than every minute in every month.
        part=part[['known_at',*columns]].sort_values('known_at').reset_index(drop=True)
        known=pd.to_datetime(part.known_at,utc=True).astype('datetime64[ns, UTC]').astype('int64').to_numpy()
        wanted=(event_known[event_known.dt.strftime('%Y-%m').eq(month)]
                .astype('datetime64[ns, UTC]').astype('int64').to_numpy())
        positions=np.searchsorted(known,wanted,side='right')-1
        positions=np.unique(positions[positions>=0])
        part=part.iloc[positions].copy()
        for column in columns:
            if pd.api.types.is_float_dtype(part[column]):part[column]=part[column].astype('float32')
        parts.append(part)
        manifest.append({'path':str(path),'mtime_ns':before.st_mtime_ns,'size':before.st_size})
    frame=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame(columns=['known_at',*columns])
    return frame,manifest


def load_method(method: str, data_root: Path, symbols=SYMBOLS, *, return_audit=False):
    """Read monthly source files defensively and return an auditable inventory."""
    tables=[]; manifest=[];audit={'events':0,'candidate_rows':0,'assembled_rows':0,'drops':{}}
    base_method,_,variant=method.partition(':')
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
            part=part[part.method.eq(base_method)]
            if variant:
                part=part[part.get('variant',pd.Series(index=part.index,dtype=object)).eq(variant)]
            if len(part):
                event_parts.append(part)
                st=p.stat();manifest.append({'path':str(p),'mtime_ns':st.st_mtime_ns,'size':st.st_size})
        if not event_parts: continue
        events=pd.concat(event_parts,ignore_index=True)
        audit['events']+=len(events[['sym','ts','side']].drop_duplicates())
        audit['candidate_rows']+=len(events)
        assert_dev_period(events)
        dense,dense_manifest=_read_layer(data_root/'features'/sym,events)
        if dense.empty:raise ValueError(f'Missing dense features for {sym}/{method}')
        flow,flow_manifest=_read_layer(data_root/'features_flow'/sym,events)
        depth,depth_manifest=_read_layer(data_root/'features_depth'/sym,events,depth=True)
        result,drops=assemble(events,dense,supplemental={'flow':flow,'depth':depth},return_audit=True)
        tables.append(result);manifest.extend(dense_manifest+flow_manifest+depth_manifest)
        audit['assembled_rows']+=len(result)
        for key,value in drops.items():audit['drops'][key]=audit['drops'].get(key,0)+value
    table=pd.concat(tables,ignore_index=True) if tables else pd.DataFrame()
    return (table,manifest,audit) if return_audit else (table,manifest)
