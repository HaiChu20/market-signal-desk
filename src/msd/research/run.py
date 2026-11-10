"""Run development-only pilot evaluations."""
from __future__ import annotations
import argparse,csv,hashlib,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss
from .dataset import load_method
from .splits import walk_forward
from .models import fit_time_ordered
from .decision import choose
from .report_card import report

METHODS=('sr_touch','liquidity_sweep','rsi2_mean_reversion')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--method',required=True,choices=METHODS)
    p.add_argument('--period',required=True,choices=('dev','test'))
    p.add_argument('--i-have-frozen-config')
    p.add_argument('--data-root',type=Path,default=Path('/Users/bfhach/Projects/market-signal-desk/data'))
    args=p.parse_args()
    if args.period!='dev':
        if not args.i_have_frozen_config: p.error('Test requires --period test --i-have-frozen-config <hash>')
        p.error('Test runner is deliberately unimplemented in this development task')
    started=time.perf_counter()
    data,manifest=load_method(args.method,args.data_root)
    if data.empty:
        card=report(args.method,'dev',data,data,manifest)
        print(json.dumps({'pooled':card['pooled'],'runtime_s':time.perf_counter()-started}));return
    data=data.sort_values('known_at').reset_index(drop=True)
    pred=np.full(len(data),np.nan)
    for train,test in walk_forward(data,n_folds=4):
        if len(train)<100:continue
        model=fit_time_ordered(data.iloc[train])
        pred[test]=model.predict(data.iloc[test])
    evaluated=data.loc[np.isfinite(pred)].copy()
    evaluated['p']=pred[np.isfinite(pred)]
        # Estimate uncertainty from the available OOF sample; thresholds are fixed in development.
    signals=choose(evaluated,threshold=.05,uncertainty=np.sqrt(evaluated.p*(1-evaluated.p)/max(len(evaluated),1)))
    config={'model':'lightgbm','n_estimators':40,'num_leaves':7,'threshold':.05,'folds':4,'cost_model':'known_spread_plus_one_night_v2','offset':'lightgbm_init_score','report_metrics':'v2'}
    cfg=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    ledger=Path('reports/trials.csv')
    with ledger.open(newline='') as f: existing=list(csv.DictReader(f))
    count=sum(r['method']==args.method and r['period'] in ('development','dev') and r['config_hash']==cfg for r in existing)
    if count: raise RuntimeError('This config was already evaluated; trial ledger is append-only')
    if sum(r['method']==args.method and r['period'] in ('development','dev') and 'model=' in r['parameters'] for r in existing)>=20:
        raise RuntimeError('Development configuration limit reached')
    card=report(args.method,'dev',signals,evaluated,manifest,trial_count=len(existing)+1)
    with ledger.open('a',newline='') as f:
        csv.writer(f).writerow([f'dev-model-{args.method}-{cfg[:10]}',pd.Timestamp.now(tz='UTC').date(),cfg,args.method,
            'model=lightgbm;'+json.dumps(config,sort_keys=True),
            f"{data.known_at.min()} / {data.known_at.max()}",'development',json.dumps(card['pooled'],sort_keys=True),
            'PRELIMINARY stage 9 inputs; development OOF only'])
    print(json.dumps({'method':args.method,'pooled':card['pooled'],'runtime_s':round(time.perf_counter()-started,2)}))
if __name__=='__main__':main()
