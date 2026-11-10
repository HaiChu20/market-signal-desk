"""Run development-only pilot evaluations."""
from __future__ import annotations
import argparse,csv,hashlib,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from .dataset import load_method, FEATURES_BY_METHOD
from .splits import walk_forward
from .models import fit_time_ordered
from .decision import choose
from .report_card import report,metrics,trial_diagnostics
from .benchmark import random_direction

METHODS=('sr_touch','liquidity_sweep','rsi2_mean_reversion')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--method',required=True,choices=METHODS)
    p.add_argument('--period',required=True,choices=('dev','test'))
    p.add_argument('--i-have-frozen-config')
    p.add_argument('--data-root',type=Path,default=Path('/Users/bfhach/Projects/market-signal-desk/data'))
    p.add_argument('--features',help='Comma-separated feature override; default selects dense columns on each training fold')
    args=p.parse_args()
    if args.period!='dev':
        if not args.i_have_frozen_config: p.error('Test requires --period test --i-have-frozen-config <hash>')
        p.error('Test runner is deliberately unimplemented in this development task')
    started=time.perf_counter()
    data,manifest,audit=load_method(args.method,args.data_root,return_audit=True)
    if data.empty:
        card=report(args.method,'dev',data,data,manifest,audit=audit)
        print(json.dumps({'pooled':card['pooled'],'runtime_s':time.perf_counter()-started}));return
    data=data.sort_values('known_at').reset_index(drop=True)
    pred=np.full(len(data),np.nan)
    uncertainty=np.full(len(data),np.nan)
    features=tuple(args.features.split(',')) if args.features else FEATURES_BY_METHOD[args.method]
    audit['model_features_by_fold']=[]
    for train,test in walk_forward(data,n_folds=4):
        if len(train)<100:continue
        model=fit_time_ordered(data.iloc[train],features=features)
        audit['model_features_by_fold'].append(list(model.features))
        pred[test]=model.predict(data.iloc[test])
        uncertainty[test]=model.uncertainty(data.iloc[test])
    evaluated=data.loc[np.isfinite(pred)].copy()
    evaluated['p']=pred[np.isfinite(pred)]
    evaluated['p_uncertainty']=uncertainty[np.isfinite(pred)]
    evaluated['candidate_id']=np.arange(len(evaluated))
    signals=choose(evaluated,threshold=.05,uncertainty=evaluated.p_uncertainty)
    config={'model':'lightgbm','n_estimators':40,'num_leaves':7,'min_data_in_leaf':100,
            'feature_fraction':.5,'features':list(features) if features else 'training_dense_gt_50pct',
            'threshold':.05,'folds':4,'cost_model':'known_spread_plus_one_night_v2',
            'offset':'lightgbm_init_score','uncertainty':'calibration_bin_distinct_events_v1',
            'report_metrics':'v4'}
    cfg=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    ledger=Path('reports/trials.csv')
    with ledger.open(newline='') as f: existing=list(csv.DictReader(f))
    count=sum(r['method']==args.method and r['period'] in ('development','dev') and r['config_hash']==cfg for r in existing)
    if count: raise RuntimeError('This config was already evaluated; trial ledger is append-only')
    if sum(r['method']==args.method and r['period'] in ('development','dev') and 'model=' in r['parameters'] for r in existing)>=20:
        raise RuntimeError('Development configuration limit reached')
    provisional=metrics(signals,evaluated)
    sharpes,pbo,trial_count=trial_diagnostics(existing+[{'method':args.method,'period':'development','metrics':json.dumps(provisional)}],args.method)
    random_percentile,random_n,bar_manifest=random_direction(signals,args.data_root)
    manifest.extend(bar_manifest)
    card=report(args.method,'dev',signals,evaluated,manifest,trial_count=trial_count,
        trial_sharpes=sharpes,pbo=pbo,random_percentile=random_percentile,random_n=random_n,audit=audit)
    ledger_metrics={k:card['pooled'].get(k) for k in ('n','net_avg_R','t_stat','brier_skill_vs_p0',
        'daily_sharpe','per_year','random_direction_percentile','pbo','deflated_sharpe_ratio')}
    with ledger.open('a',newline='') as f:
        csv.writer(f).writerow([f'dev-model-{args.method}-{cfg[:10]}',pd.Timestamp.now(tz='UTC').date(),cfg,args.method,
            'model=lightgbm;'+json.dumps(config,sort_keys=True),
            f"{data.known_at.min()} / {data.known_at.max()}",'development',json.dumps(ledger_metrics,sort_keys=True),
            'PRELIMINARY stage 9 inputs; development OOF only'])
    print(json.dumps({'method':args.method,'metrics':ledger_metrics,
        'events':audit['events'],'candidate_rows':audit['candidate_rows'],
        'oof_rows':len(evaluated),'runtime_s':round(time.perf_counter()-started,2)}))
if __name__=='__main__':main()
