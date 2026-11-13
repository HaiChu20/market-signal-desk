"""Preregistered DEV-only E1/E2/E3 experiments; never reads 2023+ rows."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from msd.processing.wide_v1 import build_event_labels,load_config
from .gating import gate_open_signals
from .ledger import FIELDS,append_trial,read_trials
from .method_registry import load_registry
from .report_card import metrics
from .splits import cpcv_folds
from .wide_pure_rules import _best,_finite,_load_unit

DEV_END=pd.Timestamp("2023-01-01",tz="UTC")
PROTOCOL="dev_v2_experiments"
SYMBOLS=("BTCUSDT","ETHUSDT","USATECHIDXUSD","USA500IDXUSD","XAUUSD")
INDEXES=("USATECHIDXUSD","USA500IDXUSD")


def _assert_dev(frame: pd.DataFrame,*columns: str) -> None:
    for column in columns:
        if column in frame and pd.to_datetime(frame[column],utc=True,errors="coerce").ge(DEV_END).any():
            raise AssertionError(f"{column}: non-DEV row")


def build_e1(data_root: Path,event_root: Path,config_path: Path) -> None:
    config=load_config(config_path)
    if config["max_hold_trading_days"]!=3:raise ValueError("E1 requires three trading days")
    for symbol in SYMBOLS:build_event_labels(symbol,data_root,event_root,config)


def _evaluate(frame: pd.DataFrame) -> tuple[pd.DataFrame,dict,list[dict]]:
    if frame.empty:return frame,{"n":0},[]
    frame=frame.sort_values(["known_at","event_key","sl_atr","tp_r"],kind="stable").reset_index(drop=True)
    rep=frame.groupby("event_key",sort=False).agg(known_at=("known_at","first"),label_end_ts=("label_end_ts","max")).reset_index()
    votes=defaultdict(list);folds=[]
    for number,fold in enumerate(cpcv_folds(rep,5,2)):
        train_keys=set(rep.event_key.iloc[fold.train]);test_keys=rep.event_key.iloc[fold.test].tolist()
        train=frame[frame.event_key.isin(train_keys)];cell=_best(train)
        score=float(train.loc[train.sl_atr.eq(cell[0])&train.tp_r.eq(cell[1]),"net_R"].mean())
        folds.append({"fold":number,"cell":cell,"train_net_R":score})
        for key in test_keys:votes[key].append(cell)
    chosen=[]
    for key,choices in votes.items():
        cell=sorted(Counter(choices).items(),key=lambda item:(-item[1],item[0]))[0][0]
        chosen.append({"event_key":key,"sl_atr":cell[0],"tp_r":cell[1]})
    signals=pd.DataFrame(chosen).merge(frame,on=["event_key","sl_atr","tp_r"],validate="one_to_one") if chosen else frame.iloc[:0]
    signals=gate_open_signals(signals)
    item=metrics(signals,None)
    item["time_exit_share"]=float(signals.outcome.eq("time").mean()) if len(signals) else None
    item["events"]=int(rep.event_key.nunique());item["candidates"]=len(frame)
    return signals,item,folds


def e1_results(v1_root: Path,e1_root: Path) -> tuple[list[dict],list[dict],dict[str,pd.DataFrame]]:
    baseline=[];rows=[];signals={}
    for spec in [s for s in load_registry() if s.status=="in_scope"]:
        old=_load_unit(v1_root,spec);new=_load_unit(e1_root,spec)
        old_signals,old_item,old_folds=_evaluate(old);new_signals,item,folds=_evaluate(new)
        old_item.update({"unit":spec.key,"folds":old_folds})
        baseline.append(_finite(old_item))
        item.update({"unit":spec.key,"folds":folds,"old":{
            "net_avg_R":metrics(old_signals,None).get("net_avg_R"),
            "t_stat":metrics(old_signals,None).get("t_stat"),
            "profit_factor":metrics(old_signals,None).get("profit_factor"),
            "time_exit_share":float(old_signals.outcome.eq("time").mean()) if len(old_signals) else None}})
        for key in ("net_avg_R","t_stat","profit_factor","time_exit_share"):
            a=item.get(key);b=item["old"].get(key);item[f"delta_{key}"]=a-b if a is not None and b is not None else None
        rows.append(_finite(item));signals[spec.key]=new_signals
    rows.sort(key=lambda row:row.get("net_avg_R") if row.get("net_avg_R") is not None else -np.inf,reverse=True)
    baseline.sort(key=lambda row:row.get("net_avg_R") if row.get("net_avg_R") is not None else -np.inf,reverse=True)
    return baseline,rows,signals


def _vol_for_rows(frame: pd.DataFrame,volumes: dict[str,pd.Series]) -> np.ndarray:
    values=np.full(len(frame),np.nan)
    for symbol,index in frame.groupby("sym").groups.items():
        dates=pd.to_datetime(frame.loc[index,"known_at"],utc=True)
        keys=dates.dt.tz_convert("America/New_York").dt.date if symbol in INDEXES else dates.dt.date
        values[np.asarray(list(index),int)]=pd.Series(keys,index=index).map(volumes.get(symbol,pd.Series(dtype=float))).to_numpy(float)
    return values


def _nested_rule(v1: pd.DataFrame,e1: pd.DataFrame,unit: str,
                 volumes: dict[str,pd.Series]|None=None) -> pd.DataFrame:
    if v1.empty and e1.empty:return pd.DataFrame()
    reps=[]
    for horizon,frame in (("hold1",v1),("hold3",e1)):
        if len(frame):
            x=frame.groupby("event_key",sort=False).agg(known_at=("known_at","first"),label_end_ts=("label_end_ts","max")).reset_index()
            x["horizon"]=horizon;reps.append(x)
    rep=pd.concat(reps).groupby("event_key",sort=False).agg(known_at=("known_at","min"),label_end_ts=("label_end_ts","max")).reset_index()
    votes=defaultdict(list);volumes=volumes or {}
    frames={"hold1":v1,"hold3":e1}
    for fold in cpcv_folds(rep,5,2):
        train_keys=set(rep.event_key.iloc[fold.train]);test_keys=rep.event_key.iloc[fold.test].tolist()
        choices=[]
        for horizon,frame in frames.items():
            train=frame[frame.event_key.isin(train_keys)]
            if train.empty:continue
            cell=_best(train);selected=train[train.sl_atr.eq(cell[0])&train.tp_r.eq(cell[1])]
            choices.append((float(selected.net_R.mean()),horizon,cell))
        winner=max(choices,key=lambda x:(x[0],x[1],x[2])) if choices else None
        choice=None if winner is None or winner[0]<=0 else (winner[1],winner[2][0],winner[2][1])
        medians={}
        if choice is not None:
            selected_train=frames[choice[0]]
            selected_train=selected_train[selected_train.event_key.isin(train_keys)&selected_train.sl_atr.eq(choice[1])&selected_train.tp_r.eq(choice[2])]
            train_vol=_vol_for_rows(selected_train.reset_index(drop=True),volumes)
            for symbol,index in selected_train.reset_index(drop=True).groupby("sym").groups.items():
                finite=train_vol[np.asarray(list(index),int)];finite=finite[np.isfinite(finite)&(finite>0)]
                medians[symbol]=float(np.median(finite)) if len(finite) else np.nan
        lookup=rep.set_index("event_key")
        for key in test_keys:
            weight=1.
            if choice is not None:
                candidate=frames[choice[0]];row=candidate[candidate.event_key.eq(key)].iloc[0]
                symbol=str(row.sym);date=pd.Timestamp(row.known_at)
                date=date.tz_convert("America/New_York").date() if symbol in INDEXES else date.date()
                current=volumes.get(symbol,pd.Series(dtype=float)).get(date,np.nan);median=medians.get(symbol,np.nan)
                if np.isfinite(current) and current>0 and np.isfinite(median):weight=float(np.clip(median/current,.5,2.))
            votes[key].append((choice,weight))
    selected=[]
    for key,ballots in votes.items():
        choices=[x[0] for x in ballots];counts=Counter(choices);choice=sorted(counts.items(),key=lambda x:(-x[1],str(x[0])))[0][0]
        if choice is not None:
            weights=[weight for voted,weight in ballots if voted==choice]
            selected.append((key,*choice,float(np.median(weights))))
    parts=[]
    for key,horizon,sl,tp,weight in selected:
        row=frames[horizon]
        match=row[row.event_key.eq(key)&row.sl_atr.eq(sl)&row.tp_r.eq(tp)]
        if len(match):
            match=match.iloc[[0]].copy();match["selected_horizon"]=horizon;match["unit"]=unit
            match["inv_vol_weight"]=weight;parts.append(match)
    if not parts:return pd.DataFrame()
    raw=pd.concat(parts,ignore_index=True)
    return pd.concat([gate_open_signals(group) for _,group in raw.groupby(["unit","sym"],sort=False)],ignore_index=True)


def _daily_vol(data_root: Path,symbol: str) -> pd.Series:
    source="binance_um" if symbol in {"BTCUSDT","ETHUSDT"} else "dukascopy"
    parts=[]
    for path in sorted((data_root/"bars"/source/symbol).glob("*.parquet")):
        try:month=pd.Timestamp(path.stem+"-01",tz="UTC")
        except ValueError:continue
        if month>=DEV_END:continue
        part=pd.read_parquet(path,columns=["ts","bid_c","ask_c"]);_assert_dev(part,"ts");parts.append(part)
    if not parts:return pd.Series(dtype=float)
    frame=pd.concat(parts,ignore_index=True);ts=pd.to_datetime(frame.ts,utc=True)
    date=ts.dt.tz_convert("America/New_York").dt.date if symbol in INDEXES else ts.dt.date
    mid=(frame.bid_c.to_numpy(float)+frame.ask_c.to_numpy(float))/2
    close=pd.Series(mid,index=pd.Index(date)).groupby(level=0).last()
    return close.pct_change().rolling(20,min_periods=20).std().shift(1)


def _portfolio_metrics(trades: pd.DataFrame,weights: np.ndarray) -> dict:
    if trades.empty:return {"n":0}
    work=trades.copy();work["weighted_R"]=work.net_R.to_numpy(float)*weights
    day=pd.to_datetime(work.label_end_ts,utc=True).dt.floor("D");daily=work.assign(day=day).groupby("day").weighted_R.sum()
    days=pd.date_range(day.min(),day.max(),freq="D",tz="UTC");daily=daily.reindex(days,fill_value=0.)
    returns=daily*.005;equity=(1+returns).clip(lower=0).cumprod();draw=(equity/equity.cummax().clip(lower=1)-1).min()
    values=work.weighted_R.to_numpy(float);loss=-values[values<0].sum()
    contribution={symbol:float(work.loc[work.sym.eq(symbol),"weighted_R"].sum()) for symbol in SYMBOLS}
    return _finite({"n":len(work),"trades_per_day":len(work)/len(days),"net_R_per_day":float(daily.mean()),
        "daily_sharpe":float(np.sqrt(365)*daily.mean()/daily.std(ddof=1)) if daily.std(ddof=1)>0 else None,
        "max_drawdown":float(draw),"profit_factor":float(values[values>0].sum()/loss) if loss>0 else None,
        "per_market_contribution":contribution})


def e2_results(data_root: Path,v1_root: Path,e1_root: Path) -> tuple[dict,pd.DataFrame]:
    parts=[];volumes={symbol:_daily_vol(data_root,symbol) for symbol in SYMBOLS}
    for spec in [s for s in load_registry() if s.status=="in_scope"]:
        chosen=_nested_rule(_load_unit(v1_root,spec),_load_unit(e1_root,spec),spec.key,volumes)
        if len(chosen):parts.append(chosen)
    trades=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    equal=np.ones(len(trades));inv=trades.inv_vol_weight.to_numpy(float) if len(trades) else np.array([])
    return {"equal_risk":_portfolio_metrics(trades,equal),"inverse_volatility":_portfolio_metrics(trades,inv)},trades


def _intraday_rows(data_root: Path,symbol: str) -> pd.DataFrame:
    parts=[]
    for path in sorted((data_root/"bars"/"dukascopy"/symbol).glob("*.parquet")):
        try:month=pd.Timestamp(path.stem+"-01",tz="UTC")
        except ValueError:continue
        if month.year<2019 or month>=DEV_END:continue
        columns=["ts",*[f"{side}_{field}" for side in ("bid","ask") for field in ("o","c")]]
        part=pd.read_parquet(path,columns=columns);_assert_dev(part,"ts");parts.append(part)
    bars=pd.concat(parts,ignore_index=True).sort_values("ts").drop_duplicates("ts")
    local=pd.to_datetime(bars.ts,utc=True).dt.tz_convert("America/New_York")
    bars=bars.assign(date=local.dt.date,clock=local.dt.strftime("%H:%M"))
    feature_cache={};rows=[];prior_close=None
    for date,day in bars.groupby("date",sort=True):
        by=day.set_index("clock")
        if prior_close is not None and {"09:59","15:30","15:59"}<=set(by.index):
            ten=by.loc["09:59"];entry=by.loc["15:30"];close=by.loc["15:59"]
            signal=((ten.bid_c+ten.ask_c)/2)/prior_close-1;side=1 if signal>0 else -1 if signal<0 else 0
            if side:
                entry_price=float(entry.ask_o if side>0 else entry.bid_o);exit_price=float(close.bid_c if side>0 else close.ask_c)
                entry_mid=float((entry.bid_o+entry.ask_o)/2);exit_mid=float((close.bid_c+close.ask_c)/2)
                feature_path=data_root/"features"/symbol/f"{pd.Timestamp(entry.ts).strftime('%Y-%m')}.parquet"
                if feature_path not in feature_cache:
                    feature_cache[feature_path]=pd.read_parquet(feature_path,columns=["ts","known_at","1h_atr14"])
                feature=feature_cache[feature_path]
                known=pd.to_datetime(feature.known_at,utc=True);eligible=feature[known<=pd.Timestamp(entry.ts)]
                atr=float(eligible.iloc[-1]["1h_atr14"]) if len(eligible) else np.nan
                if np.isfinite(atr) and atr>0:
                    rows.append({"sym":symbol,"date":str(date),"known_at":pd.Timestamp(entry.ts),"entry_ts":pd.Timestamp(entry.ts),
                        "label_end_ts":pd.Timestamp(close.ts)+pd.Timedelta(minutes=1),"signal":float(signal),"side":side,
                        "entry_price":entry_price,"exit_price":exit_price,"entry_mid":entry_mid,"exit_mid":exit_mid,
                        "gross_R":side*(exit_mid-entry_mid)/atr,"net_R":side*(exit_price-entry_price)/atr,
                        "prior_close_mid":prior_close,"ten_am_mid":float((ten.bid_c+ten.ask_c)/2),
                        "event_key":f"{symbol}|{date}"})
        if "15:59" in by.index:
            last=by.loc["15:59"];prior_close=float((last.bid_c+last.ask_c)/2)
    out=pd.DataFrame(rows);_assert_dev(out,"known_at","label_end_ts");return out


def _intraday_variant(frame: pd.DataFrame,large: bool) -> pd.DataFrame:
    rep=frame[["event_key","known_at","label_end_ts"]].copy();votes=defaultdict(list)
    for fold in cpcv_folds(rep,5,2):
        threshold=float(frame.signal.abs().iloc[fold.train].median()) if large else 0.
        for ix in fold.test:votes[int(ix)].append(bool(abs(frame.signal.iloc[ix])>threshold))
    take=[ix for ix,choices in votes.items() if sum(choices)>len(choices)/2]
    return frame.iloc[sorted(take)].reset_index(drop=True)


def e3_results(data_root: Path) -> tuple[dict,list[dict]]:
    frame=pd.concat([_intraday_rows(data_root,s) for s in INDEXES],ignore_index=True)
    result={}
    for name,large in (("all_nonzero",False),("above_train_median",True)):
        signals=_intraday_variant(frame,large);item=metrics(signals,None);item["gross_avg_R"]=float(signals.gross_R.mean())
        item["per_market"]={s:{**metrics(signals[signals.sym.eq(s)],None),"gross_avg_R":float(signals.loc[signals.sym.eq(s),"gross_R"].mean())} for s in INDEXES}
        item["per_year"]={str(y):{**metrics(signals[pd.to_datetime(signals.entry_ts,utc=True).dt.year.eq(y)],None),
            "gross_avg_R":float(signals.loc[pd.to_datetime(signals.entry_ts,utc=True).dt.year.eq(y),"gross_R"].mean())}
            for y in sorted(pd.to_datetime(signals.entry_ts,utc=True).dt.year.unique())}
        result[name]=_finite(item)
    desired=("2019-03-08","2019-03-11","2019-11-04")
    checks=frame[frame.date.isin(desired)].sort_values(["date","sym"]).head(6).copy()
    checks["known_at"]=pd.to_datetime(checks.known_at,utc=True).astype(str)
    columns=["sym","date","prior_close_mid","ten_am_mid","signal","side","known_at","entry_price","exit_price","gross_R","net_R"]
    return result,_finite(checks[columns].to_dict("records"))


def _ledger_rows(baseline: list[dict],e1: list[dict],e2: dict,e3: dict,config_sha: str) -> list[dict]:
    day=str(pd.Timestamp.now(tz="UTC").date());rows=[]
    payloads=[*(('E0',x['unit'],x) for x in baseline),*(('E1',x['unit'],x) for x in e1),
              *(('E2',k,v) for k,v in e2.items()),*(('E3',k,v) for k,v in e3.items())]
    for experiment,name,value in payloads:
        method=name if experiment in {'E0','E1'} else 'rule_portfolio' if experiment=='E2' else 'intraday_momentum_jfe'
        digest=hashlib.sha256(f"{PROTOCOL}|{experiment}|{name}|{config_sha}".encode()).hexdigest()
        params=json.dumps({"protocol":PROTOCOL,"experiment":experiment,"config":name,"config_sha":config_sha},sort_keys=True)
        rows.append(dict(zip(FIELDS,[f"dev-v2-{experiment.lower()}-{name}",day,digest,method,params,
            "through 2022-12-31","dev",json.dumps(_finite(value),sort_keys=True,allow_nan=False),PROTOCOL])))
    return rows


def _preflight(ledger: Path,rows: list[dict]) -> None:
    existing=read_trials(ledger);shadow=list(existing)
    for row in rows:
        same=[x for x in shadow if x['method']==row['method'] and x['period'] in {'dev','development'}]
        if any(x['config_hash']==row['config_hash'] for x in same):raise ValueError(f"duplicate {row['run_id']}")
        if len({x['config_hash'] for x in same})>=20:raise ValueError(f"trial limit {row['method']}")
        shadow.append(row)


def run(data_root: Path=Path("data"),e1_root: Path=Path("data/events_wide_hold3_v2"),
        v1_root: Path=Path("data/events_wide_v2"),
        output: Path=Path("reports/research/dev_v2_experiments"),ledger: Path=Path("reports/trials.csv"),
        build: bool=True) -> Path:
    config_path=Path("hpc/roihu/sequence/configs/wide_hold3_v2.json")
    baseline_config=Path("hpc/roihu/sequence/configs/wide_v2.json")
    config_sha=hashlib.sha256(baseline_config.read_bytes()+b"\0"+config_path.read_bytes()).hexdigest()
    if build:build_e1(data_root,e1_root,config_path)
    baseline,e1,_=e1_results(v1_root,e1_root)
    e2,_=e2_results(data_root,v1_root,e1_root)
    e3,e3_checks=e3_results(data_root)
    rows=_ledger_rows(baseline,e1,e2,e3,config_sha);_preflight(ledger,rows)
    payload=_finite({"protocol":PROTOCOL,"dev_only":True,"wide_v2_baseline":baseline,
                     "e1":e1,"e2":e2,"e3":e3,"e3_hand_checks":e3_checks})
    output.mkdir(parents=True,exist_ok=True);(output/"summary.json").write_text(json.dumps(payload,indent=2,allow_nan=False)+"\n")
    (output/"wide_v2_pure_rules_summary.json").write_text(json.dumps({"protocol":PROTOCOL,"units":baseline},indent=2,allow_nan=False)+"\n")
    def f(v):return "NA" if v is None else f"{v:.4f}"
    positive=sum(1 for x in e1 if (x.get('net_avg_R') or 0)>0);best=e1[0]
    by_unit={x['unit']:x for x in e1}
    leaders=[]
    for unit in ('donchian_atr_breakout','funding_extreme_fade'):
        item=by_unit.get(unit,{})
        delta=item.get('delta_net_avg_R')
        leaders.append(f"{unit} {'improved' if delta is not None and delta>0 else 'weakened'} by {f(delta)}R")
    equal=e2.get('equal_risk',{});inverse=e2.get('inverse_volatility',{})
    all_signal=e3.get('all_nonzero',{});filtered=e3.get('above_train_median',{})
    lines=["# DEV v2 experiments","","**DEV only; Test and Final were not loaded.**","","## Conclusions","",
        f"E1: {'; '.join(leaders)}. {positive} of 34 units had positive OOF average R; the best was {best['unit']} at {f(best.get('net_avg_R'))}R.",
        f"E2 equal-risk Sharpe was {f(equal.get('daily_sharpe'))} with account MDD {f(equal.get('max_drawdown'))}; inverse-volatility Sharpe was {f(inverse.get('daily_sharpe'))} with account MDD {f(inverse.get('max_drawdown'))}. MDD is a fraction of account equity, not an R-unit drawdown. ETH contributes exactly zero because the frozen replay contains no ETH event parquet, not because rows were lost during portfolio loading.",
        f"E3 net average R was {f(all_signal.get('net_avg_R'))} for all signals and {f(filtered.get('net_avg_R'))} above the train-fold median. The direction and New York session timestamps were hand-checked across the March and November DST transitions. E3 does not use wide event labels and was unaffected by the deadline-unit bug.","",
        "## Wide-v2 corrected one-day baseline","","| Rule | OOF n | Net R | t | PF | Time exit |",
        "|---|---:|---:|---:|---:|---:|"]
    for x in baseline:lines.append(f"| {x['unit']} | {x.get('n',0)} | {f(x.get('net_avg_R'))} | {f(x.get('t_stat'))} | {f(x.get('profit_factor'))} | {f(x.get('time_exit_share'))} |")
    (output/"wide_v2_pure_rules_summary.md").write_text("\n".join(lines[lines.index("## Wide-v2 corrected one-day baseline"):])+"\n")
    lines += ["",
        "## E1 — three-day hold","","| Rule | OOF n | Net R | Δ Net R | t | Δ t | PF | Δ PF | Time exit | Δ Time exit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in e1:lines.append(f"| {x['unit']} | {x.get('n',0)} | {f(x.get('net_avg_R'))} | {f(x.get('delta_net_avg_R'))} | {f(x.get('t_stat'))} | {f(x.get('delta_t_stat'))} | {f(x.get('profit_factor'))} | {f(x.get('delta_profit_factor'))} | {f(x.get('time_exit_share'))} | {f(x.get('delta_time_exit_share'))} |")
    lines += ["","## E2 — nested rule portfolio","","MDD is the fraction of account equity at 0.5% base risk per accepted trade.","","| Sizing | Trades | Trades/day | Net R/day | Sharpe | Account MDD | PF | Contribution |","|---|---:|---:|---:|---:|---:|---:|---|"]
    for name,x in e2.items():lines.append(f"| {name} | {x.get('n',0)} | {f(x.get('trades_per_day'))} | {f(x.get('net_R_per_day'))} | {f(x.get('daily_sharpe'))} | {f(x.get('max_drawdown'))} | {f(x.get('profit_factor'))} | {json.dumps(x.get('per_market_contribution',{}),sort_keys=True)} |")
    lines += ["","## E3 — intraday momentum","","| Variant | n | Gross R/trade | Net R/trade | Hit | t | Sharpe | MDD | PF |","|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name,x in e3.items():lines.append(f"| {name} | {x.get('n',0)} | {f(x.get('gross_avg_R'))} | {f(x.get('net_avg_R'))} | {f(x.get('hit_rate'))} | {f(x.get('t_stat'))} | {f(x.get('daily_sharpe'))} | {f(x.get('max_drawdown'))} | {f(x.get('profit_factor'))} |")
    for name,x in e3.items():
        lines += ["",f"### E3 {name} by market/year","","| Scope | n | Gross R/trade | Net R/trade | Hit | t |","|---|---:|---:|---:|---:|---:|"]
        for scope,value in [*x['per_market'].items(),*[(f"year {k}",v) for k,v in x['per_year'].items()]]:
            lines.append(f"| {scope} | {value.get('n',0)} | {f(value.get('gross_avg_R'))} | {f(value.get('net_avg_R'))} | {f(value.get('hit_rate'))} | {f(value.get('t_stat'))} |")
    lines += ["","### E3 hand checks (ET session conversion)","","| Market | Session | Prior 16:00 mid | 10:00 mid | Signal | Side | Entry UTC | Entry | Exit | Gross R | Net R |","|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|"]
    for x in e3_checks:lines.append(f"| {x['sym']} | {x['date']} | {x['prior_close_mid']:.4f} | {x['ten_am_mid']:.4f} | {x['signal']:.6f} | {x['side']} | {x['known_at']} | {x['entry_price']:.4f} | {x['exit_price']:.4f} | {x['gross_R']:.4f} | {x['net_R']:.4f} |")
    report=output/"summary.md";report.write_text("\n".join(lines)+"\n")
    for row in rows:append_trial(ledger,row,max_configs=20)
    return report


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--skip-build",action="store_true")
    parser.add_argument("--data-root",type=Path,default=Path("data"));parser.add_argument("--e1-root",type=Path,default=Path("data/events_wide_hold3_v2"))
    parser.add_argument("--v1-root",type=Path,default=Path("data/events_wide_v2"))
    args=parser.parse_args();print(run(args.data_root,args.e1_root,args.v1_root,build=not args.skip_build))


if __name__=="__main__":main()
