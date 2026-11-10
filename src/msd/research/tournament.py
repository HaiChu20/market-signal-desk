"""Generate preliminary DEV tournament summary from registered event detectors."""
from __future__ import annotations
import importlib,csv,json
from pathlib import Path
import pandas as pd
from .report_card import metrics
from .dataset import DEV_END
from . import any_minute

def registry_names():
 import msd.methods as package
 names=[]
 for path in Path(package.__file__).parent.glob('*.py'):
  if path.name.startswith('_') or path.stem in {'__init__','common','filters'}:continue
  module=importlib.import_module(f'msd.methods.{path.stem}')
  name=getattr(module,'NAME',None)
  if name and name not in names:names.append(name)
 return sorted(names)

def main(root=Path('/Users/bfhach/Projects/market-signal-desk/data')):
 names=registry_names();rows=[]
 for method in names:
  events=[]
  for sym in any_minute.SYMBOLS:
   for p in sorted((root/'events'/sym).glob('*.parquet')):
    if p.stem[:4]>'2022':continue
    try:d=pd.read_parquet(p,columns=['method','sym','known_at','outcome','R','exit_ts','entry_ts','gross_R'])
    except Exception:continue
    d=d[d.method.eq(method)];d=d[(pd.to_datetime(d.known_at,utc=True)<DEV_END)&(pd.to_datetime(d.exit_ts,utc=True)<DEV_END)]
    events.append(d)
  if events:
   d=pd.concat(events,ignore_index=True)
   n=len(d);r=pd.to_numeric(d.R,errors='coerce').dropna();rows.append({'method':method,'events':n,'candidate rows':n,'net avg R':r.mean() if n else None,'grade':'ungraded: DEV'})
  else:rows.append({'method':method,'events':0,'candidate rows':0,'net avg R':None,'grade':'ungraded: DEV'})
 rows.append({'method':'any_minute_grid','events':None,'candidate rows':'15m anchors × SL/TP grid','net avg R':None,'grade':'see report'})
 out=Path('reports/research/tournament_dev.md');out.parent.mkdir(parents=True,exist_ok=True)
 lines=['# Preliminary development tournament','', 'DEV only (through 2022-12-31). Inputs are being regenerated; these counts and event outcomes are preliminary. Every method name is read from `src/msd/methods` NAME declarations. No test or final period evaluated.','', '| Method | Events | Candidate rows | Net avg R | Grade |','|---|---:|---:|---:|---|']
 for r in rows:lines.append(f"| {r['method']} | {r['events'] if r['events'] is not None else '—'} | {r['candidate rows']} | {r['net avg R'] if r['net avg R'] is not None else '—'} | {r['grade']} |")
 lines+=['','Any-minute model report: `reports/research/any_minute_grid_dev.json` (when generated).']
 out.write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main()
