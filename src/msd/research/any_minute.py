"""Preliminary DEV model on the every-15-minute ATR barrier label grid."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd
from .dataset import DEV_END,FEATURES_BY_METHOD
from .splits import walk_forward
from .models import fit_time_ordered
from .decision import choose
from .report_card import report,metrics,trial_diagnostics
from .benchmark import random_direction

SYMBOLS=('BTCUSDT','USATECHIDXUSD','USA500IDXUSD')
GRID_FEATURES=('1m_return_bars_5','1m_return_bars_60','1m_realized_vol30','1m_rsi2','1m_atr14','1m_adx14','15m_return_bars_4','15m_rsi14','1h_return_bars_4','1h_adx14','4h_return_bars_6','1d_return_bars_5','time_sin','time_cos')

def gate_open_signals(candidates):
 """Keep a signal only when its prior exit was observable by this decision time."""
 keep=[];open_known_at=pd.Timestamp.min.tz_localize('UTC')
 ordered=candidates.sort_values('known_at')
 for ix,row in ordered.iterrows():
  if row.known_at>=open_known_at:
   keep.append(ix)
   # Grid exit_ts is the exit bar start; event becomes known at its close.
   open_known_at=pd.Timestamp(row.label_end_ts)+pd.Timedelta(minutes=1)
 return ordered.loc[keep]

def load_grid(root):
 import pyarrow.parquet as pq
 tables=[];manifest=[];audit={'anchors':0,'candidate_rows':0,'rows':0,'drops':0}
 for sym in SYMBOLS:
  ep=sorted(p for p in (root/'labels'/sym).glob('*.parquet') if p.stem[:4]<='2022')
  for p in ep:
   before=p.stat();y=pd.read_parquet(p,columns=['side','sl_atr','tp_atr','net_R','gross_R','exit_ts','entry_ts','deadline_ts','outcome','ts','planned_risk'])
   y=y[pd.to_datetime(y.ts,utc=True)<DEV_END]
   if p.stat().st_mtime_ns!=before.st_mtime_ns:raise RuntimeError(f'Changed while reading {p}')
   y['sym']=sym;y['known_at']=pd.to_datetime(y.ts,utc=True)+pd.Timedelta(minutes=1)
   audit['candidate_rows']+=len(y);audit['anchors']+=y.ts.nunique()
   feat=root/'features'/sym/f'{p.stem}.parquet'
   if not feat.exists():audit['drops']+=len(y);continue
   fb=feat.stat();f=pd.read_parquet(feat,columns=['known_at',*(c for c in GRID_FEATURES if c in pq.read_schema(feat).names)]);f=f[pd.to_datetime(f.known_at,utc=True)<DEV_END];manifest.extend([{'path':str(p),'mtime_ns':before.st_mtime_ns},{'path':str(feat),'mtime_ns':fb.st_mtime_ns}])
   y['label_end_ts']=pd.to_datetime(y.exit_ts,utc=True);y['tp_first']=y.outcome.eq(1).astype('int8')
   y['net_R']=y.net_R.astype(float);y['gross_R']=y.gross_R.astype(float)
   risk=pd.to_numeric(y.planned_risk,errors='coerce');y['TP_R']=y.tp_atr/y.sl_atr;y['p0']=1/(1+y.TP_R)
   # Geometry is represented in ATR units; label-grid outputs don't persist
   # actual anchor price or ATR, but the R distances are exact.
   y['price']=0.;y['sl']=-y.sl_atr;y['tp']=y.tp_atr;y['planned_risk']=y.sl_atr
   y['event_key']=sym+'|'+y.ts.astype(str)
   y['cost_R']=0.;y['financing_R']=0.
   z=pd.merge_asof(y.sort_values('known_at'),f.sort_values('known_at'),on='known_at',direction='backward',suffixes=('','_feature'))
   for c in z.select_dtypes(include=['float64']).columns:z[c]=z[c].astype('float32')
   cols=[c for c in f if c!='known_at']
   z=z[(z.label_end_ts<DEV_END)&(z.known_at<DEV_END)&z[cols].notna().any(axis=1)]
   audit['rows']+=len(z);audit['drops']+=len(y)-len(z);tables.append(z)
 data=pd.concat(tables,ignore_index=True) if tables else pd.DataFrame()
 return data,manifest,audit

def run(root=Path('/Users/bfhach/Projects/market-signal-desk/data')):
 data,manifest,audit=load_grid(root)
 data=data.sort_values('known_at').reset_index(drop=True)
 features=None;pred=np.full(len(data),np.nan);unc=np.full(len(data),np.nan)
 for tr,te in walk_forward(data,4):
  train=data.iloc[tr]
  if len(train)>100_000:
   # Deterministic candidate subsample for training only; evaluate every anchor.
   train=train.sample(n=100_000,random_state=20261110).sort_values('known_at')
  model=fit_time_ordered(train,features=features);pred[te]=model.predict(data.iloc[te]);unc[te]=model.uncertainty(data.iloc[te])
 d=data.loc[np.isfinite(pred)].copy();d['p']=pred[np.isfinite(pred)];d['uncertainty']=unc[np.isfinite(pred)];d['candidate_id']=np.arange(len(d))
 # one open trade at a time, in decision-time order; reject overlapping label windows
 chosen=choose(d,threshold=.05,uncertainty=d.uncertainty)
 signals=gate_open_signals(chosen)
 manifest0=manifest
 percentile,n,bars=random_direction(signals,root);manifest0+=bars
 ledger=pd.read_csv('reports/trials.csv');sh,pbo,ntr=trial_diagnostics(ledger.to_dict('records'),'any_minute_grid')
 card=report('any_minute_grid','dev',signals,d,manifest0,trial_count=ntr,trial_sharpes=sh,pbo=pbo,random_percentile=percentile,random_n=n,audit={'events':audit['anchors'],'candidate_rows':audit['candidate_rows'],'assembled_rows':audit['rows'],'drops':{'unavailable_or_outside_dev':audit['drops']}})
 card['pooled']['anchors']=audit['anchors'];card['pooled']['candidate_rows']=audit['candidate_rows'];card['pooled']['oof_rows']=len(d)
 Path('reports/research/any_minute_grid_dev.json').write_text(json.dumps(card,indent=2,allow_nan=False))
 print(json.dumps({k:card['pooled'].get(k) for k in ('n','brier_skill_vs_p0','net_avg_R','t_stat','random_direction_percentile','deflated_sharpe_ratio')}))
if __name__=='__main__':run()
