"""Protocol metrics; development cards are explicitly ungraded."""
from __future__ import annotations
import json
from pathlib import Path
from math import erf,sqrt
from itertools import combinations
import numpy as np
import pandas as pd
from msd.stats import deflated_sharpe_ratio

def trial_diagnostics(rows,method):
    """DSR trial dispersion and CSCV PBO from logged yearly dev scores."""
    trials=[]
    for row in rows:
        if row.get('method')!=method or row.get('period') not in {'development','dev'}:continue
        try:metric=json.loads(row['metrics'])
        except (ValueError,KeyError):continue
        if isinstance(metric,dict) and metric.get('daily_sharpe') is not None:
            trials.append(metric)
    sharpes=[float(m['daily_sharpe'])/np.sqrt(252) for m in trials if np.isfinite(m['daily_sharpe'])]
    yearly=[m.get('per_year',{}) for m in trials if isinstance(m.get('per_year'),dict)]
    pbo=None
    if len(yearly)>=2:
        common=set.intersection(*(set(y) for y in yearly))
        years=sorted(common)
        if len(years)>=4:
            scores=np.asarray([[y[k] for k in years] for y in yearly],dtype=float)
            scores=scores[np.isfinite(scores).all(axis=1)]
            if len(scores)>=2:
                failures=[]
                for train_years in combinations(range(len(years)),len(years)//2):
                    test_years=[i for i in range(len(years)) if i not in train_years]
                    winner=np.argmax(scores[:,train_years].mean(axis=1))
                    out=scores[:,test_years].mean(axis=1)
                    failures.append(float(out[winner]<np.median(out)))
                pbo=float(np.mean(failures))
    return sharpes,pbo,len(trials)


def _f(v):
    return None if not np.isfinite(v) else float(v)

def metrics(signals:pd.DataFrame,candidates:pd.DataFrame|None=None,trial_count=1,trial_sharpes=None):
    if signals.empty:
        empty={'n':0,'signals_per_year':0,'hit_rate':None,'net_avg_R':None,'t_stat':None,
                'profit_factor':None,'daily_sharpe':None,'max_drawdown':None,'brier':None,
                'brier_skill_vs_p0':None,'positive_dev_year_share':None,'deflated_sharpe_ratio':None,
                'random_direction_percentile':None,'pbo':None,'grade':'ungraded: development'}
        if candidates is not None and len(candidates):
            y=candidates.tp_first.to_numpy(float);p=candidates.p.to_numpy(float);p0=candidates.p0.to_numpy(float)
            baseline=np.mean((p0-y)**2)
            empty['brier']=_f(np.mean((p-y)**2))
            empty['brier_skill_vs_p0']=_f(1-empty['brier']/baseline) if baseline>0 else None
        return empty
    r=signals.net_R.to_numpy(float);n=len(r);sd=np.std(r,ddof=1) if n>1 else np.nan
    wins=r[r>0].sum();loss=-r[r<0].sum()
    entry=pd.to_datetime(signals.entry_ts,utc=True);exit_ts=pd.to_datetime(signals.label_end_ts,utc=True)
    period_time=pd.to_datetime(candidates.known_at,utc=True) if candidates is not None and len(candidates) else entry
    years=max((period_time.max()-period_time.min()).total_seconds()/86400/365.25,1/365.25)
    daily=signals.assign(day=exit_ts.dt.floor('D')).groupby('day').net_R.sum()*.005
    days=pd.date_range(entry.min().floor('D'),exit_ts.max().floor('D'),freq='D' if signals.sym.eq('BTCUSDT').all() else 'B',tz='UTC')
    daily=daily.reindex(days,fill_value=0)
    equity=(1+daily).clip(lower=0).cumprod()
    peak=equity.cummax().clip(lower=1)
    grouped=signals.groupby(entry.dt.year).net_R.mean()
    out={'n':n,'signals_per_year':_f(n/years),'hit_rate':_f((r>0).mean()),
         'net_avg_R':_f(np.mean(r)),'t_stat':_f(np.mean(r)/(sd/np.sqrt(n))) if sd>0 else None,
         'profit_factor':_f(wins/loss) if loss>0 else None,
         'daily_sharpe':_f(np.sqrt(365 if signals.sym.eq('BTCUSDT').all() else 252)*daily.mean()/daily.std(ddof=1)) if daily.std(ddof=1)>0 else None,
         'max_drawdown':_f((equity/peak-1).min()),
         'positive_dev_year_share':_f((grouped>0).mean()),
         'per_year':{str(k):_f(v) for k,v in grouped.items()},
         'spread_1_5x_net_avg_R':_f((signals.net_R-.5*signals.get('spread_R',0)).mean()),
         'random_direction_percentile':None,'pbo':None,'grade':'ungraded: development'}
    if candidates is not None and len(candidates):
        y=candidates.tp_first.to_numpy(float);p=candidates.p.to_numpy(float);p0=candidates.p0.to_numpy(float)
        brier=np.mean((p-y)**2);base=np.mean((p0-y)**2)
        out['brier']=_f(brier);out['brier_skill_vs_p0']=_f(1-brier/base) if base>0 else None
        c=candidates.copy();c['year']=pd.to_datetime(c.known_at,utc=True).dt.year
        c['vol_tercile']=pd.qcut(c['1m_realized_vol30'].rank(method='first'),3,labels=['low','middle','high']).astype(str) if '1m_realized_vol30' in c else 'unknown'
        out['reliability_by_year']={str(k):{'n':len(g),'predicted':_f(g.p.mean()),'observed':_f(g.tp_first.mean())} for k,g in c.groupby('year')}
        out['reliability_by_vol_tercile']={str(k):{'n':len(g),'predicted':_f(g.p.mean()),'observed':_f(g.tp_first.mean())} for k,g in c.groupby('vol_tercile')}
    else:out['brier']=out['brier_skill_vs_p0']=None
    if trial_sharpes is not None and len(trial_sharpes)>1:
        dsr,_,_=deflated_sharpe_ratio(daily.to_numpy(),np.asarray(trial_sharpes),trial_count)
        out['deflated_sharpe_ratio']=_f(dsr)
    else:out['deflated_sharpe_ratio']=None
    return out

def report(method,period,signals,candidates,manifest,trial_count=1,trial_sharpes=None,
           pbo=None,random_percentile=None,random_n=0,audit=None,output=Path('reports/research')):
    if period!='dev':raise ValueError('Only development reports can be generated by this runner')
    pooled=metrics(signals,candidates,trial_count,trial_sharpes)
    pooled['pbo']=pbo
    pooled['random_direction_percentile']=random_percentile
    pooled['random_direction_matched_signals']=random_n
    if audit is not None:
        pooled['row_accounting']=audit
        pooled['row_accounting']['oof_predicted_rows']=len(candidates)
        pooled['row_accounting']['selected_signals']=len(signals)
        pooled['row_accounting']['no_oof_prediction']=max(0,audit.get('assembled_rows',0)-len(candidates))
    if len(candidates):
        # A candidate-level comparison, with correlated alternatives counted separately.
        keys=set(signals.candidate_id) if 'candidate_id' in signals else set()
        chosen=candidates.candidate_id.isin(keys).to_numpy() if 'candidate_id' in candidates else np.zeros(len(candidates),dtype=bool)
        same_event=candidates.event_key.isin(set(signals.event_key)).to_numpy()
        pooled['selection_comparison']={'selected_n':int(np.sum(chosen)),
            'selected_avg_R':_f(candidates.loc[chosen,'net_R'].mean()),
            'unselected_n':int(np.sum(~chosen)),
            'unselected_avg_R':_f(candidates.loc[~chosen,'net_R'].mean()),
            'same_event_unselected_n':int(np.sum(same_event&~chosen)),
            'same_event_unselected_avg_R':_f(candidates.loc[same_event&~chosen,'net_R'].mean())}
    per_instrument={s:metrics(g,candidates[candidates.sym.eq(s)] if len(candidates) else candidates,trial_count,trial_sharpes)
                    for s,g in signals.groupby('sym')}
    for s in candidates.sym.unique() if len(candidates) else []:
        per_instrument.setdefault(s,metrics(signals.iloc[:0],candidates[candidates.sym.eq(s)]))
    card={'method':method,'period':'dev','preliminary':True,'protocol':'v2',
          'grade_in_dev':'not applicable; protocol section 5 grades test only',
          'pooled':pooled,'per_instrument':per_instrument,'input_manifest':manifest,
          'limitations':['Stage 9 inputs may be rebuilt; inspect manifest before reuse.',
                         'PBO uses CSCV over common development years of logged configurations; null here because fewer than four common years have comparable trial scores.',
                         'Random-direction benchmark uses the executable opposite-side label kernel on raw bars; coverage is reported.',
                         'For BTC, the raw mid-price bars use a monthly median of the modeled decision-time spread in the opposite-direction simulation.',
                         'DSR uses trial-ledger daily Sharpe dispersion; null if too few trials.']}
    output.mkdir(parents=True,exist_ok=True)
    stem=output/f'{method}_{period}'
    stem.with_suffix('.json').write_text(json.dumps(card,indent=2,allow_nan=False))
    lines=[f'# {method} — development report card','',
           '**PRELIMINARY — stage 9 inputs may change. Development period only; no protocol grade.**','',
           f'Input files: {len(manifest)} (paths and mtimes in JSON).','',
           '| Scope | n | Brier skill vs p0 | Net avg R | t | Grade |','|---|---:|---:|---:|---:|---|']
    for scope,item in [('pooled',pooled),*per_instrument.items()]:
        fmt=lambda v:'NA' if v is None else f'{v:.4f}'
        lines.append(f"| {scope} | {item['n']} | {fmt(item['brier_skill_vs_p0'])} | {fmt(item['net_avg_R'])} | {fmt(item['t_stat'])} | ungraded |")
    if audit is not None:
        lines+=['','## Row accounting','',
            f"Events: {audit['events']}; candidate rows: {audit['candidate_rows']}; assembled: {audit['assembled_rows']}; OOF predicted: {len(candidates)}; selected: {len(signals)}; signals/year: {fmt(pooled['signals_per_year'])}.",
            '',f"Drops: {json.dumps(audit['drops'],sort_keys=True)}; no OOF prediction: {pooled['row_accounting']['no_oof_prediction']} (initial walk-forward training block)."]
    comparison=pooled.get('selection_comparison')
    if comparison:
        lines+=['','## Candidate ranking','',
            f"Selected candidate realized R: {fmt(comparison['selected_avg_R'])} (n={comparison['selected_n']}); unselected candidate realized R: {fmt(comparison['unselected_avg_R'])} (n={comparison['unselected_n']}); unselected at selected events: {fmt(comparison['same_event_unselected_avg_R'])} (n={comparison['same_event_unselected_n']}). Alternatives at the same event are correlated."]
    lines+=['','## Selection-bias diagnostics','',
        f"Random-direction percentile: {fmt(random_percentile)} (matched signals {random_n}, 200 seeds). PBO: {fmt(pbo)}. DSR: {fmt(pooled['deflated_sharpe_ratio'])}."]
    lines+=['','## Limitations','']+[f'- {x}' for x in card['limitations']]
    stem.with_suffix('.md').write_text('\n'.join(lines)+'\n')
    return card
