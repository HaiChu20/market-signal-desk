"""Streaming, development-only 15-minute barrier model."""
from __future__ import annotations
import argparse, csv, gc, hashlib, json, time
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from .dataset import DEV_END
from .models import fit_time_ordered
from .decision import choose
from .benchmark import random_direction
from .report_card import trial_diagnostics

SYMBOLS = ('BTCUSDT', 'USATECHIDXUSD', 'USA500IDXUSD')
FEATURES = ('1m_return_bars_5','1m_return_bars_60','1m_realized_vol30','1m_rsi2',
    '1m_atr14','1m_adx14','15m_return_bars_4','15m_rsi14','1h_return_bars_4',
    '1h_adx14','4h_return_bars_6','1d_return_bars_5','time_sin','time_cos','spread_atr')
LABELS = ('ts','side','sl_atr','tp_atr','outcome','net_R','gross_R','exit_ts',
    'entry_ts','deadline_ts','planned_risk','fill_price')

def _gate_open_signals_streaming(candidates, open_known_at=None, *, return_state=False):
    """Exit bar starts at label_end_ts; it becomes known one minute later."""
    floor=pd.Timestamp.min.tz_localize('UTC')
    states=dict(open_known_at) if isinstance(open_known_at,dict) else {}
    default=floor if open_known_at is None or isinstance(open_known_at,dict) else open_known_at
    rows = []
    for row in candidates.sort_values(['known_at','event_key']).itertuples():
        key=str(getattr(row,'sym',''))
        opened=states.get(key,default)
        if row.known_at >= opened:
            rows.append(row.Index)
            states[key]=pd.Timestamp(row.label_end_ts) + pd.Timedelta(minutes=1)
    selected=candidates.loc[rows].reset_index(drop=True)
    state=next(iter(states.values()),default) if len(states)<=1 else states
    return (selected, state) if return_state else selected

def paths_for(root, symbol):
    return sorted(p for p in (root/'labels'/symbol).glob('*.parquet') if p.stem[:4] <= '2022')

def anchors_and_bounds(paths):
    # This first pass reads only the timestamp column.
    anchors=[]
    for path in paths:
        ts=pd.to_datetime(pd.read_parquet(path,columns=['ts']).ts,utc=True)
        anchors.extend(ts[ts<DEV_END].drop_duplicates().tolist())
    unique=pd.DatetimeIndex(sorted(set(anchors)))
    if len(unique)<5: raise ValueError('Too few development anchors')
    return unique, [(part.min(),part.max()) for part in np.array_split(unique,5)][1:]

def load_grid(root, symbol, path, manifest=None):
    """Read one month. Keep actual planned risk in price units for spread cost."""
    before=path.stat();y=pd.read_parquet(path,columns=list(LABELS))
    if path.stat().st_mtime_ns!=before.st_mtime_ns: raise RuntimeError(f'Changed during read: {path}')
    y=y[pd.to_datetime(y.ts,utc=True)<DEV_END].copy()
    if y.empty:return y
    feature_path=root/'features'/symbol/path.name
    if not feature_path.exists():raise FileNotFoundError(feature_path)
    schema=set(pq.read_schema(feature_path).names)
    cols=['known_at',*(c for c in FEATURES if c in schema)]
    start=feature_path.stat();f=pd.read_parquet(feature_path,columns=cols)
    if feature_path.stat().st_mtime_ns!=start.st_mtime_ns:raise RuntimeError(f'Changed during read: {feature_path}')
    if manifest is not None:
        manifest.extend(({'path':str(path),'mtime_ns':before.st_mtime_ns},
                         {'path':str(feature_path),'mtime_ns':start.st_mtime_ns}))
    y['ts']=pd.to_datetime(y.ts,utc=True)
    y['known_at']=y.ts+pd.Timedelta(minutes=1)
    y['label_end_ts']=pd.to_datetime(y.exit_ts,utc=True)
    f['known_at']=pd.to_datetime(f.known_at,utc=True)
    f=f[f.known_at<DEV_END].sort_values('known_at').drop_duplicates('known_at',keep='last')
    f=f.rename(columns={'known_at':'feature_known_at'})
    z=pd.merge_asof(y.sort_values('known_at'),f,left_on='known_at',right_on='feature_known_at',direction='backward')
    if (z.feature_known_at>z.known_at).any():raise AssertionError('Future feature')
    z=z[(z.label_end_ts+pd.Timedelta(minutes=1)<DEV_END)&z.feature_known_at.notna()&z.net_R.notna()].copy()
    z['sym']=symbol;z['tp_first']=z.outcome.eq(1).astype('int8')
    z['TP_R']=z.tp_atr/z.sl_atr
    z['p0']=z.sl_atr/(z.sl_atr+z.tp_atr)
    # Kernel uses ask entry/bid exit (opposite for shorts): half a spread at
    # each end. A full known spread is the ex-ante round-trip cost.
    spread=z.get('spread_atr',pd.Series(np.nan,index=z.index))*z.get('1m_atr14',pd.Series(np.nan,index=z.index))
    if symbol=='BTCUSDT':
        from msd.data.binance import BTC_SPREAD
        spread=spread.fillna(z.ts.dt.year.map(BTC_SPREAD))
    elif spread.isna().any():
        quote_path=root/'bars'/'dukascopy'/symbol/path.name
        if quote_path.exists():
            quote=pd.read_parquet(quote_path,columns=['ts','bid_c','ask_c'])
            quote['ts']=pd.to_datetime(quote.ts,utc=True)
            values=(quote.ask_c-quote.bid_c).to_numpy(float)
            by_ts=pd.Series(values,index=quote.ts).groupby(level=0).last()
            spread=spread.fillna(z.ts.map(by_ts))
    z['spread_R']=(spread/z.planned_risk).clip(lower=0)
    z=z[z.spread_R.notna()&np.isfinite(z.spread_R)&z.planned_risk.gt(0)].copy()
    z['cost_R']=z.spread_R
    z['financing_R']=0.0 # Realized financing remains in the net_R evaluation.
    z['price']=z.fill_price
    z['sl']=z.price-z.side*z.planned_risk
    z['tp']=z.price+z.side*z.TP_R*z.planned_risk
    z['event_key']=symbol+'|'+z.ts.astype(str)
    for c in FEATURES:
        if c not in z:z[c]=np.nan
        z[c]=pd.to_numeric(z[c],errors='coerce').astype('float32')
    for c in ('p0','TP_R','spread_R','cost_R','planned_risk','net_R'):
        z[c]=z[c].astype('float32')
    return z

def sampled(frame, cap=100_000):
    """Stable hash sample of candidate identity, independent of read order."""
    if frame.empty:return frame
    keys=frame.sym.astype(str)+'|'+frame.ts.astype(str)+'|'+frame.side.astype(str)+'|'+frame.sl_atr.astype(str)+'|'+frame.tp_atr.astype(str)
    h=pd.util.hash_pandas_object(keys,index=False).to_numpy(np.uint64)
    selected=np.flatnonzero(h%64==0)
    if len(selected)>cap:selected=selected[np.argsort(h[selected],kind='stable')[:cap]]
    return frame.iloc[selected]

def record_trial(result):
    config={'method':'any_minute_grid','symbol':result['symbol'],'folds':4,
            'sample_modulus':64,'sample_cap':100_000,'features':FEATURES,
            'cost':'known_full_spread','threshold':.05}
    digest=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    path=Path('reports/trials.csv')
    with path.open(newline='') as handle:rows=list(csv.DictReader(handle))
    if any(row.get('config_hash')==digest and row.get('period')=='development' for row in rows):return
    if sum(row.get('method')=='any_minute_grid' and row.get('period')=='development' for row in rows)>=20:
        raise RuntimeError('Development trial cap reached')
    metric={key:result.get(key) for key in ('signals','net_avg_R','t_stat','brier_skill_vs_p0','random_direction_percentile','dsr')}
    with path.open('a',newline='') as handle:
        csv.writer(handle,lineterminator='\n').writerow([
            f'dev-any-minute-{result["symbol"]}-{digest[:10]}',pd.Timestamp.now(tz='UTC').date(),
            digest,'any_minute_grid',json.dumps(config,sort_keys=True),
            f'{result["symbol"]}:DEV-through-2022-12-31','development',json.dumps(metric,sort_keys=True),
            'PRELIMINARY; stage 9 inputs may be regenerated'])

def run(root, symbol='BTCUSDT'):
    started=time.perf_counter();root=Path(root)
    if symbol not in SYMBOLS:raise ValueError(symbol)
    paths=paths_for(root,symbol)
    if not paths:raise FileNotFoundError(f'No DEV labels for {symbol}')
    anchors,bounds=anchors_and_bounds(paths)
    manifest=[];total=0;brier=brier0=0.;cal=np.zeros((10,3),float);signals=[]
    gate=None;fold_notes=[]
    for fold_id,(test_start,test_end) in enumerate(bounds):
        train_end=test_start-pd.Timedelta(days=1)
        pieces=[];seen=0
        for path in paths:
            if pd.Timestamp(path.stem+'-01',tz='UTC')>=train_end:break
            part=load_grid(root,symbol,path,manifest)
            part=part[(part.known_at<train_end)&(part.label_end_ts+pd.Timedelta(minutes=1)<train_end)]
            seen+=len(part)
            sample=sampled(part)
            if len(sample):pieces.append(sample)
            del part,sample;gc.collect()
        if not pieces:continue
        train=pd.concat(pieces,ignore_index=True)
        if len(train)>100_000:
            keys=pd.util.hash_pandas_object(train[['sym','ts','side','sl_atr','tp_atr']],index=False).to_numpy(np.uint64)
            train=train.iloc[np.argsort(keys,kind='stable')[:100_000]].copy()
        model=fit_time_ordered(train,features=FEATURES)
        fold_notes.append({'fold':fold_id,'train_sample':len(train),'train_eligible':seen})
        del train,pieces;gc.collect()
        for path in paths:
            month=pd.Timestamp(path.stem+'-01',tz='UTC')
            if month>test_end or month+pd.offsets.MonthEnd(1)<test_start:continue
            part=load_grid(root,symbol,path,manifest)
            part=part[(part.ts>=test_start)&(part.ts<=test_end)]
            if part.empty:del part;continue
            p=model.predict(part);y=part.tp_first.to_numpy(float);p0=part.p0.to_numpy(float)
            brier+=float(np.square(p-y).sum());brier0+=float(np.square(p0-y).sum());total+=len(part)
            bin_ids=np.minimum((p*10).astype(int),9)
            for i in range(10):
                mask=bin_ids==i;cal[i]+=mask.sum(),float(p[mask].sum()),float(y[mask].sum())
            part['p']=p;unc=model.uncertainty(part)
            selected=choose(part,threshold=.05,uncertainty=unc)
            selected,gate=_gate_open_signals_streaming(selected,gate,return_state=True)
            if len(selected):signals.append(selected)
            del part,selected;gc.collect()
        del model;gc.collect()
    chosen=pd.concat(signals,ignore_index=True) if signals else pd.DataFrame()
    if len(chosen):
        random_pct,matched,bars=random_direction(chosen,root)
        r=chosen.net_R.to_numpy(float);avg=float(r.mean())
        t=float(avg/(r.std(ddof=1)/np.sqrt(len(r)))) if len(r)>1 and r.std(ddof=1)>0 else None
    else:random_pct=matched=avg=t=None;bars=[]
    with Path('reports/trials.csv').open(newline='') as handle:
        ledger=list(csv.DictReader(handle))
    sharpes,pbo,n_trials=trial_diagnostics(ledger,'any_minute_grid')
    # DSR is unavailable until at least two DEV configurations have daily Sharpe scores.
    result={'method':'any_minute_grid','period':'dev','preliminary':True,'symbol':symbol,
        'anchors':len(anchors),'oof_candidate_rows':total,'signals':len(chosen),'brier':brier/total if total else None,
        'brier_p0':brier0/total if total else None,'brier_skill_vs_p0':1-brier/brier0 if brier0 else None,
        'net_avg_R':avg,'t_stat':t,'random_direction_percentile':random_pct,
        'random_direction_matched':matched,'dsr':None,'pbo':pbo,
        'calibration_bins':cal.tolist(),'folds':fold_notes,'manifest':manifest,
        'runtime_s':time.perf_counter()-started}
    out=Path(f'reports/research/any_minute_grid_{symbol}_dev.json');out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,allow_nan=False))
    out.with_suffix('.md').write_text(f"# Any-minute {symbol} DEV (PRELIMINARY)\n\n"
        f"OOF candidates: {total}; signals: {len(chosen)}; Brier skill vs p0: {result['brier_skill_vs_p0']}; "
        f"net average R: {avg}; t: {t}; random-direction percentile: {random_pct}.\n\n"
        "DSR and PBO require comparable logged model configurations. Inputs may be regenerated.\n")
    record_trial(result)
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--symbol',choices=SYMBOLS,default='BTCUSDT')
    parser.add_argument('--data-root',type=Path,default=Path('data'))
    parser.add_argument('--period',choices=['dev'],default='dev');args=parser.parse_args()
    print(json.dumps(run(args.data_root,args.symbol)))
if __name__=='__main__':main()
