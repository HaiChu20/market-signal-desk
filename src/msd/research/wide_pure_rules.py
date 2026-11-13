"""Family-1 pure-rule CPCV selection on versioned wide-v1 event labels."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from msd.stats import deflated_sharpe_ratio
from .gating import gate_open_signals
from .ledger import FIELDS, append_trial, read_trials
from .method_registry import load_registry
from .report_card import metrics
from .splits import cpcv_folds

PROTOCOL="wide_v1_pure_rules"
SYMBOLS=("BTCUSDT","ETHUSDT","USATECHIDXUSD","USA500IDXUSD","XAUUSD")


def _load_unit(root: Path, spec) -> pd.DataFrame:
    parts=[]
    for symbol in spec.symbols:
        if symbol not in SYMBOLS:continue
        for path in sorted((root/symbol).glob("*.parquet")):
            try:
                wanted=("method","variant","sym","event_key","ts","side","entry_type","limit_price",
                        "known_at","label_end_ts","entry_ts","sl_atr","tp_r","net_R","spread_R","outcome")
                available=set(pq.read_schema(path).names)
                frame=pd.read_parquet(path,columns=[column for column in wanted if column in available])
            except Exception:
                continue
            if frame.empty or "method" not in frame:continue
            frame=frame[frame.method.eq(spec.name)]
            if spec.variant is not None:
                frame=frame[frame.get("variant",pd.Series(index=frame.index,dtype=object)).eq(spec.variant)]
            if len(frame):parts.append(frame)
    if not parts:return pd.DataFrame()
    out=pd.concat(parts,ignore_index=True)
    broken=out.event_key.isna()|out.event_key.astype(str).eq("")
    if broken.any():
        variant=out.get("variant",pd.Series("",index=out.index)).fillna("").astype(str)
        entry_type=out.get("entry_type",pd.Series("market",index=out.index)).fillna("market").astype(str)
        limit=out.get("limit_price",pd.Series(np.nan,index=out.index)).astype(object).fillna("").astype(str)
        repaired=(out.sym.astype(str)+"|"+out.method.astype(str)+"|"+variant+"|"+
                  out.ts.astype(str)+"|"+out.side.astype(str)+"|"+entry_type+"|"+limit)
        out.loc[broken,"event_key"]=repaired.loc[broken]
    if pd.to_datetime(out.known_at,utc=True).ge("2023-01-01").any() or pd.to_datetime(out.label_end_ts,utc=True).ge("2023-01-01").any():
        raise ValueError(f"{spec.key}: non-DEV row")
    return out


def _best(frame: pd.DataFrame) -> tuple[float,float]:
    scores=frame.groupby(["sl_atr","tp_r"],observed=True).net_R.mean().sort_values(ascending=False)
    return tuple(map(float,scores.index[0]))


def _daily(signals: pd.DataFrame) -> np.ndarray:
    if signals.empty:return np.array([],dtype=float)
    end=pd.to_datetime(signals.label_end_ts,utc=True);entry=pd.to_datetime(signals.entry_ts,utc=True)
    values=signals.assign(day=end.dt.floor("D")).groupby("day").net_R.sum()*.005
    days=pd.date_range(entry.min().floor("D"),end.max().floor("D"),freq="D",tz="UTC")
    return values.reindex(days,fill_value=0).to_numpy(float)


def evaluate_unit(frame: pd.DataFrame) -> tuple[pd.DataFrame,dict,list[float],list[float],tuple[float,float]|None]:
    if frame.empty:return frame,{"n":0},[],[],None
    frame=frame.sort_values(["known_at","event_key","sl_atr","tp_r"],kind="stable").reset_index(drop=True)
    rep=frame.groupby("event_key",sort=False).agg(known_at=("known_at","first"),label_end_ts=("label_end_ts","max")).reset_index()
    votes=defaultdict(list);train_scores=[];test_scores=[]
    for fold in cpcv_folds(rep,5,2):
        train_keys=set(rep.event_key.iloc[fold.train]);test_keys=rep.event_key.iloc[fold.test].tolist()
        train=frame[frame.event_key.isin(train_keys)]
        cell=_best(train)
        test=frame[frame.event_key.isin(test_keys)&frame.sl_atr.eq(cell[0])&frame.tp_r.eq(cell[1])]
        train_cell=train[train.sl_atr.eq(cell[0])&train.tp_r.eq(cell[1])]
        train_scores.append(float(train_cell.net_R.mean()));test_scores.append(float(test.net_R.mean()))
        for key in test_keys:votes[key].append(cell)
    selected=[]
    for key,choices in votes.items():
        cell=sorted(Counter(choices).items(),key=lambda item:(-item[1],item[0]))[0][0]
        selected.append({"event_key":key,"sl_atr":cell[0],"tp_r":cell[1]})
    if selected:
        choices=pd.DataFrame(selected)
        chosen=choices.merge(frame,on=["event_key","sl_atr","tp_r"],how="left",validate="one_to_one")
    else:
        chosen=frame.iloc[:0].copy()
    gated=gate_open_signals(chosen)
    result=metrics(gated,None)
    years=max((pd.to_datetime(rep.known_at,utc=True).max()-pd.to_datetime(rep.known_at,utc=True).min()).total_seconds()/86400/365.25,1/365.25)
    result["signals_per_year"]=len(gated)/years
    return gated,result,train_scores,test_scores,_best(frame)


def _finite(value):
    if isinstance(value,dict):return {str(key):_finite(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [_finite(item) for item in value]
    if isinstance(value,np.generic):value=value.item()
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def _time_exit_table(event_root: Path) -> list[dict]:
    totals=defaultdict(lambda:[0,0])
    for symbol in SYMBOLS:
        for path in sorted((event_root/symbol).glob("*.parquet")):
            available=set(pq.read_schema(path).names)
            if not {"sl_atr","tp_r","outcome"}<=available:continue
            frame=pd.read_parquet(path,columns=["sl_atr","tp_r","outcome"])
            for cell,group in frame.groupby(["sl_atr","tp_r"],observed=True):
                totals[tuple(map(float,cell))][0]+=len(group)
                totals[tuple(map(float,cell))][1]+=int(group.outcome.eq("time").sum())
    return [{"sl_atr":cell[0],"tp_r":cell[1],"rows":values[0],"time_exits":values[1],
             "time_exit_share":values[1]/values[0] if values[0] else None}
            for cell,values in sorted(totals.items())]


def run(event_root: Path=Path("data/events_wide_v1"), output: Path=Path("reports/research/wide_v1"),
        ledger: Path=Path("reports/trials.csv"), config_path: Path=Path("hpc/roihu/sequence/configs/wide_v1.json")) -> Path:
    specs=[spec for spec in load_registry() if spec.status=="in_scope"]
    config_bytes=config_path.read_bytes();config_sha=hashlib.sha256(config_bytes).hexdigest()
    rows=[];daily={};signals_by_unit={};spec_by_key={spec.key:spec for spec in specs}
    for spec in specs:
        frame=_load_unit(event_root,spec)
        market_events=({symbol:int(frame.loc[frame.sym.eq(symbol),"event_key"].nunique())
                        for symbol in spec.symbols if symbol in SYMBOLS} if len(frame) else
                       {symbol:0 for symbol in spec.symbols if symbol in SYMBOLS})
        signals,item,train_scores,test_scores,in_sample=evaluate_unit(frame)
        item.update({"unit":spec.key,"candidates":len(frame),"events":frame.event_key.nunique() if len(frame) else 0,
                     "market_events":market_events,"in_sample_best":in_sample,
                     "cpcv_train_scores":train_scores,"cpcv_test_scores":test_scores})
        rows.append(item);daily[spec.key]=_daily(signals);signals_by_unit[spec.key]=signals
    sharpes=[]
    for values in daily.values():
        sharpes.append(float(np.mean(values)/np.std(values,ddof=1)) if len(values)>1 and np.std(values,ddof=1)>0 else np.nan)
    trial_sharpes=np.asarray(sharpes,float)
    for item in rows:
        values=daily[item["unit"]]
        dsr=deflated_sharpe_ratio(values,trial_sharpes,len(rows))[0] if len(values)>1 else np.nan
        item["dsr"]=float(dsr) if np.isfinite(dsr) else None
    rows=_finite(rows)
    rows.sort(key=lambda item:item.get("net_avg_R") if item.get("net_avg_R") is not None else -np.inf,reverse=True)
    time_exits=_time_exit_table(event_root)
    output.mkdir(parents=True,exist_ok=True);path=output/"pure_rules_summary.md"
    lines=["# Wide-v1 Family 1 pure-rules DEV retest","",
        "**Development only. Test and Final were not loaded. No ML was used.**","",
        "Each CPCV training split selects one fixed SL/TP cell by mean net R; the test events receive only that fold-trained cell, followed by the shared one-position-per-symbol gate.","",
        "| Rank | Unit | Events | OOF trades | Trades/yr | Hit | Net avg R | t | PF | Sharpe | MDD | DSR | In-sample best SL/TP-R | Result |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    def f(v):return "NA" if v is None or not np.isfinite(v) else f"{v:.4f}"
    for rank,item in enumerate(rows,1):
        passes=(item.get("net_avg_R") or 0)>0 and (item.get("t_stat") or 0)>2
        cell=item["in_sample_best"];cell_text="NA" if cell is None else f"{cell[0]:g}/{cell[1]:g}"
        lines.append(f"| {rank} | {item['unit']} | {item['events']:,} | {item.get('n',0):,} | {f(item.get('signals_per_year'))} | {f(item.get('hit_rate'))} | {f(item.get('net_avg_R'))} | {f(item.get('t_stat'))} | {f(item.get('profit_factor'))} | {f(item.get('daily_sharpe'))} | {f(item.get('max_drawdown'))} | {f(item.get('dsr'))} | {cell_text} | {'OOF > 0, t > 2' if passes else 'does not pass'} |")
    lines += ["","## Time exits by geometry", "", "| SL ATR | TP R | Rows | Time exits | Share |", "|---:|---:|---:|---:|---:|"]
    for cell in time_exits:
        lines.append(f"| {cell['sl_atr']:g} | {cell['tp_r']:g} | {cell['rows']:,} | {cell['time_exits']:,} | {f(cell['time_exit_share'])} |")
    lines += ["","## Per-market OOF metrics", "", "| Unit | Market | Events | OOF n | Net avg R | t | PF | Sharpe | MDD |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for item in rows:
        signals=signals_by_unit[item["unit"]]
        spec=spec_by_key[item["unit"]]
        for symbol in spec.symbols:
            if symbol not in SYMBOLS:continue
            subset=signals[signals.sym.eq(symbol)] if len(signals) else signals
            m=metrics(subset,None)
            lines.append(f"| {item['unit']} | {symbol} | {item['market_events'].get(symbol,0):,} | {m['n']:,} | {f(m['net_avg_R'])} | {f(m['t_stat'])} | {f(m['profit_factor'])} | {f(m['daily_sharpe'])} | {f(m['max_drawdown'])} |")
    path.write_text("\n".join(lines)+"\n")
    payload={"units":rows,"time_exits_by_cell":time_exits}
    (output/"pure_rules_summary.json").write_text(json.dumps(_finite(payload),indent=2,allow_nan=False)+"\n")
    existing=read_trials(ledger)
    pending=[]
    for item in rows:
        run_id=f"wide-v1-pure-{item['unit']}"
        if any(row["run_id"]==run_id for row in existing):continue
        digest=hashlib.sha256((config_sha+item["unit"]).encode()).hexdigest()
        metrics_payload={key:value for key,value in item.items() if key not in {"unit"}}
        row=dict(zip(FIELDS,[run_id,str(pd.Timestamp.now(tz="UTC").date()),digest,item["unit"],
            json.dumps({"protocol":PROTOCOL,"config_sha256":config_sha},sort_keys=True),
            "first available / 2022-12-31","dev",json.dumps(_finite(metrics_payload),sort_keys=True,allow_nan=False),PROTOCOL]))
        pending.append(row)
    # Preflight every ledger constraint before the first append.
    for row in pending:
        same=[item for item in existing if item["method"]==row["method"] and item["period"] in {"dev","development"}]
        if any(item["config_hash"]==row["config_hash"] for item in same):raise ValueError(f"duplicate trial: {row['method']}")
        if len({item["config_hash"] for item in same})>=20:raise ValueError(f"trial limit: {row['method']}")
    for row in pending:append_trial(ledger,row,max_configs=20);existing.append(row)
    return path


if __name__=="__main__":run()
