"""Protocol-v2 DEV tournament orchestrator. Test and Final are inaccessible here."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import resource
import time

import numpy as np
import pandas as pd

from .benchmark import random_direction
from .dataset import FORBIDDEN, load_method
from .decision import choose
from .gating import gate_open_signals
from .ledger import FIELDS, append_trial, read_trials
from .method_registry import MethodSpec, load_registry, reconciliation
from .models import fit_time_ordered
from .report_card import metrics, report, trial_diagnostics
from .splits import cpcv_folds


CONFIG = {'model':'lightgbm','n_estimators':40,'num_leaves':7,'min_data_in_leaf':100,
          'feature_fraction':.5,'threshold':.05,'cpcv_groups':5,'cpcv_test_groups':2,
          'embargo':'1 trading day','cost_model':'executable_bid_ask_plus_financing_v2'}
REQUIRED = {'sym','method','known_at','label_end_ts','event_key','side','price','sl','tp',
            'planned_risk','tp_first','net_R','gross_R','p0','TP_R','cost_R','financing_R'}
FROZEN_MANIFEST = Path('reports/research/events_replay_dev_manifest.json')
FROZEN_FILE_COUNT = 336


def verify_frozen_events(events_root: Path, expected_sha: str, *,
                         manifest_path: Path=FROZEN_MANIFEST,
                         expected_count: int=FROZEN_FILE_COUNT) -> str:
    """Recompute the committed manifest's exact combined hash over event parquets."""
    manifest=json.loads(manifest_path.read_text())
    rows=manifest.get('files',[])
    actual=sorted(Path(events_root).rglob('*.parquet'))
    if len(rows)!=expected_count or len(actual)!=expected_count:
        raise ValueError(f'Frozen events require {expected_count} files; manifest={len(rows)}, actual={len(actual)}')
    root=Path(manifest['root'])
    expected={Path(item['path']).relative_to(root).as_posix():item for item in rows}
    found={path.relative_to(events_root).as_posix():path for path in actual}
    if set(found)!=set(expected):
        raise ValueError('Frozen event file set differs from the committed manifest')
    combined=hashlib.sha256()
    for relative,item in sorted(expected.items(),key=lambda pair:pair[1]['path']):
        digest=hashlib.sha256()
        with found[relative].open('rb') as handle:
            for chunk in iter(lambda:handle.read(8*1024*1024),b''):digest.update(chunk)
        value=digest.hexdigest()
        if value!=item['sha256'] or found[relative].stat().st_size!=item['size']:
            raise ValueError(f'Frozen event file mismatch: {relative}')
        combined.update(f"{item['path']}\0{value}\n".encode())
    value=combined.hexdigest()
    if value!=manifest.get('combined_sha256') or value!=expected_sha:
        raise ValueError(f'Frozen events SHA mismatch: actual={value}, requested={expected_sha}')
    return value


def validate_schema(frame: pd.DataFrame, spec: MethodSpec) -> None:
    missing=REQUIRED-set(frame)
    if missing:raise ValueError(f'{spec.key}: missing required columns {sorted(missing)}')
    if frame.empty:raise ValueError(f'{spec.key}: no DEV candidates')
    if pd.to_datetime(frame.label_end_ts,utc=True).ge(pd.Timestamp('2023-01-01',tz='UTC')).any():
        raise ValueError(f'{spec.key}: DEV label_end_ts crosses 2022-12-31')
    if spec.variant is not None:
        if 'variant' not in frame or not frame.variant.eq(spec.variant).all():
            raise ValueError(f'{spec.key}: replayed events lack the frozen variant attribute')
    if set(FORBIDDEN)&set(CONFIG.get('features',())):
        raise AssertionError('Outcome-derived column configured as a feature')
    usable=[column for column in frame if column not in FORBIDDEN and
            pd.api.types.is_numeric_dtype(frame[column]) and frame[column].notna().any()]
    if not usable:raise ValueError(f'{spec.key}: no usable causal model features')


def _selected_score(frame: pd.DataFrame, probabilities, uncertainties) -> float:
    work=frame.copy();work['p']=probabilities;work['p_uncertainty']=uncertainties
    work['candidate_id']=work.index.to_numpy()
    selected=gate_open_signals(choose(work,threshold=CONFIG['threshold'],uncertainty=uncertainties))
    return float(selected.net_R.mean()) if len(selected) else np.nan


def cpcv_predictions(frame: pd.DataFrame) -> tuple[pd.DataFrame,list[float],list[float],list[list[int]]]:
    """Aggregate repeated CPCV test predictions; every fold is purged/embargoed."""
    total=np.zeros(len(frame));uncertainty2=np.zeros(len(frame));count=np.zeros(len(frame),dtype=int)
    train_scores=[];test_scores=[];groups=[]
    for fold in cpcv_folds(frame,CONFIG['cpcv_groups'],CONFIG['cpcv_test_groups']):
        model=fit_time_ordered(frame.iloc[fold.train])
        p=model.predict(frame.iloc[fold.test]);u=model.uncertainty(frame.iloc[fold.test])
        total[fold.test]+=p;uncertainty2[fold.test]+=np.square(u);count[fold.test]+=1
        train_p=model.predict(frame.iloc[fold.train]);train_u=model.uncertainty(frame.iloc[fold.train])
        train_scores.append(_selected_score(frame.iloc[fold.train],train_p,train_u))
        test_scores.append(_selected_score(frame.iloc[fold.test],p,u))
        groups.append(list(fold.test_groups))
    if (count==0).any():raise RuntimeError('CPCV did not produce an out-of-fold prediction for every row')
    result=frame.copy();result['p']=total/count
    result['p_uncertainty']=np.sqrt(uncertainty2/count)
    result['candidate_id']=np.arange(len(result))
    return result,train_scores,test_scores,groups


def _config_hash(spec: MethodSpec) -> str:
    payload={**CONFIG,'method':spec.key,'symbols':spec.symbols}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def run_one(spec: MethodSpec, data_root: Path, output: Path, *, dry_run: bool,
            frozen_events_sha: str | None=None) -> tuple[dict,dict]:
    if spec.status!='in_scope':raise ValueError(f'{spec.key} is {spec.status}')
    started=time.perf_counter()
    data,manifest,audit=load_method(spec.key,data_root,symbols=spec.symbols,return_audit=True)
    if data.empty:
        reason=('macro_minutes_since_event is absent from the frozen DEV features'
                if spec.name=='post_macro_event_reaction' else
                'the frozen replay contains no candidates for this unit')
        pooled={key:None for key in ('signals_per_year','hit_rate','net_avg_R','t_stat',
            'profit_factor','daily_sharpe','max_drawdown','brier_skill_vs_p0',
            'deflated_sharpe_ratio','pbo','random_direction_percentile')}
        pooled['n']=0
        card={'method':spec.key,'period':'dev','preliminary':True,'protocol':'v2',
              'status':f'no DEV events: {reason}','grade_in_dev':'silent: no DEV events',
              'pooled':pooled,'per_instrument':{},'input_manifest':manifest,
              'config_hash':_config_hash(spec),'registry_id':spec.id,'variant':spec.variant,
              'dry_run':dry_run,'cpcv':None}
        runtime=time.perf_counter()-started
        stats={'method':spec.key,'candidates':0,'signals':0,'runtime_s':runtime,
               'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,
               'status':card['status'],'pooled':pooled}
        card['run_stats']=stats
        output.mkdir(parents=True,exist_ok=True)
        stem=output/f'{spec.key}_dev'
        stem.with_suffix('.json').write_text(json.dumps(card,indent=2,allow_nan=False))
        stem.with_suffix('.md').write_text(
            f'# {spec.key} — development report card\n\n**{card["status"]}.**\n\n'
            'Development only. Test and Final were not loaded or evaluated.\n')
        return card,stats
    validate_schema(data,spec)
    evaluated,train_scores,test_scores,groups=cpcv_predictions(data.sort_values('known_at').reset_index(drop=True))
    signals=gate_open_signals(choose(evaluated,threshold=CONFIG['threshold'],
                                    uncertainty=evaluated.p_uncertainty))
    train_scores=[None if not np.isfinite(value) else float(value) for value in train_scores]
    test_scores=[None if not np.isfinite(value) else float(value) for value in test_scores]
    ledger=Path('reports/trials.csv');existing=read_trials(ledger)
    provisional=metrics(signals,evaluated)
    diagnostic_row={'method':spec.key,'period':'dev','metrics':json.dumps({
        **provisional,'cpcv_train_scores':train_scores,'cpcv_test_scores':test_scores})}
    sharpes,pbo,trial_count=trial_diagnostics(existing+[diagnostic_row],spec.key)
    percentile,random_n,bar_manifest=random_direction(signals,data_root,seeds=200)
    manifest.extend(bar_manifest)
    fold_audit={'cpcv_test_groups':groups,'cpcv_train_scores':train_scores,
                'cpcv_test_scores':test_scores}
    audit.update(fold_audit)
    card=report(spec.key,'dev',signals,evaluated,manifest,trial_count=trial_count,
                trial_sharpes=sharpes,pbo=pbo,random_percentile=percentile,
                random_n=random_n,audit=audit,output=output)
    card['config_hash']=_config_hash(spec);card['registry_id']=spec.id
    card['variant']=spec.variant;card['dry_run']=dry_run
    card['cpcv'] = fold_audit
    report_path=output/f'{spec.key}_dev.json'
    report_path.write_text(json.dumps(card,indent=2,allow_nan=False))
    ledger_metrics={**card['pooled'],'cpcv_train_scores':train_scores,'cpcv_test_scores':test_scores}
    if not dry_run:
        if not frozen_events_sha:raise ValueError('A frozen replayed-events SHA is required')
        row=dict(zip(FIELDS,[f"dev-{spec.key}-{card['config_hash'][:12]}",
            str(pd.Timestamp.now(tz='UTC').date()),card['config_hash'],spec.key,
            json.dumps({**CONFIG,'events_sha':frozen_events_sha},sort_keys=True),
            f"{evaluated.known_at.min()} / {evaluated.known_at.max()}",'dev',
            json.dumps(ledger_metrics,sort_keys=True),'protocol-v2 DEV CPCV']))
        append_trial(ledger,row,max_configs=20)
    pooled=card['pooled']
    dev_pass=all(((pooled.get('net_avg_R') or 0)>0,
                 (pooled.get('t_stat') or 0)>=3,
                 (pooled.get('brier_skill_vs_p0') or 0)>0,
                 (pooled.get('positive_dev_year_share') or 0)>=.6,
                 (pooled.get('spread_1_5x_net_avg_R') or 0)>0))
    status='silent: 0 selected signals' if not len(signals) else ('passes DEV diagnostics' if dev_pass else 'fails DEV diagnostics')
    stats={'method':spec.key,'candidates':len(evaluated),'signals':len(signals),
           'runtime_s':time.perf_counter()-started,
           'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,
           'report':str(report_path),'status':status,'pooled':pooled}
    card['status']=status;card['run_stats']=stats
    report_path.write_text(json.dumps(card,indent=2,allow_nan=False))
    return card,stats


def write_summary(stats: list[dict], registry: tuple[MethodSpec,...], output: Path, *, dry_run: bool) -> Path:
    rec=reconciliation(registry);path=output/('dev_tournament_dry_run.md' if dry_run else 'dev_tournament_summary.md')
    title='Protocol-v2 DEV tournament dry run' if dry_run else 'Protocol-v2 DEV tournament'
    lines=[f'# {title}','',
        '**Development only. Test and Final were neither loaded nor evaluated.**','',
        '## Registry reconciliation','',
        f"The method index contains {rec['documented_table_rows']} table rows plus "
        f"{rec['pilot_modules']} pilots = {rec['detector_modules']} detector modules. "
        f"Bollinger and post-macro each add one extra frozen variant, producing "
        f"{rec['tournament_units']} tournament units. #34 is inputs-pending and excluded.",'',
        '| Unit | Candidates | Signals | Signals/yr | Hit | Net avg R | t | PF | Sharpe | MDD | Brier skill | DSR | PBO | Random pct | DEV status | Runtime s | Peak MiB |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|']
    def fmt(value):return 'NA' if value is None else f'{value:.4f}'
    for row in stats:
        item=row.get('pooled',{})
        lines.append(f"| {row['method']} | {row['candidates']:,} | {row['signals']:,} | "
            f"{fmt(item.get('signals_per_year'))} | {fmt(item.get('hit_rate'))} | "
            f"{fmt(item.get('net_avg_R'))} | {fmt(item.get('t_stat'))} | "
            f"{fmt(item.get('profit_factor'))} | {fmt(item.get('daily_sharpe'))} | "
            f"{fmt(item.get('max_drawdown'))} | {fmt(item.get('brier_skill_vs_p0'))} | "
            f"{fmt(item.get('deflated_sharpe_ratio'))} | {fmt(item.get('pbo'))} | "
            f"{fmt(item.get('random_direction_percentile'))} | {row['status']} | "
            f"{row['runtime_s']:.2f} | {row['peak_rss_mib']:.1f} |")
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text('\n'.join(lines)+'\n')
    return path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--method',action='append',required=True)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--frozen-events-sha')
    parser.add_argument('--data-root',type=Path,default=Path('data'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.dry_run and not args.frozen_events_sha:
        parser.error('Full DEV is locked until replayed events are frozen; use --dry-run')
    output=args.output or Path('reports/research/dry_run' if args.dry_run else 'reports/research/dev_v2')
    if not args.dry_run:
        verify_frozen_events(args.data_root/'events',args.frozen_events_sha)
    if args.dry_run and len(args.method)>2:parser.error('Dry-run acceptance is limited to 1–2 methods')
    registry=load_registry();by_key={spec.key:spec for spec in registry}
    unknown=set(args.method)-set(by_key)
    if unknown:parser.error(f'Unknown tournament units: {sorted(unknown)}')
    stats=[]
    for key in args.method:
        _,item=run_one(by_key[key],args.data_root,output,dry_run=args.dry_run,
                       frozen_events_sha=args.frozen_events_sha)
        stats.append(item);print(json.dumps(item),flush=True)
    # Each serial process refreshes the summary from all completed unit cards.
    completed=[]
    for spec in registry:
        path=output/f'{spec.key}_dev.json'
        if path.exists():
            card=json.loads(path.read_text())
            if card.get('run_stats'):completed.append(card['run_stats'])
    print(write_summary(completed or stats,registry,output,dry_run=args.dry_run))


if __name__=='__main__':main()
