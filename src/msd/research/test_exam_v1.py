"""One-shot preregistered 2023-2024 Test exam for two fixed pure rules."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from msd.processing.crypto_perp import apply_perp_costs
from msd.processing.pipeline import replay_events_only
from msd.processing.wide_v1 import _bars, _event_jobs, _funding
from .gating import gate_open_signals
from .ledger import FIELDS, append_test_trial_once, validate_test_trial
from .report_card import metrics

TEST_START=pd.Timestamp("2023-01-01",tz="UTC")
FINAL_START=pd.Timestamp("2025-01-01",tz="UTC")
FROZEN_CODE="a196fdd982e10aa4f3d4dffc08e59382615ce53a"
WIDE_CONFIG_SHA="1cab0902ea0845a1ab74ff15333ea412a1f16bd6b3b71031afeb4a2da02681dd"
PREREG=Path("docs/test_preregistration_v1.md")
RULES={
    "funding_extreme_fade":{"symbols":("BTCUSDT",),"sl_atr":1.5,"tp_r":2.0},
    "donchian_atr_breakout":{"symbols":("USATECHIDXUSD","USA500IDXUSD","XAUUSD","BTCUSDT"),
                              "sl_atr":3.0,"tp_r":3.0},
}


def _assert_test_boundary(frame: pd.DataFrame, *columns: str) -> None:
    for column in columns:
        if column in frame and pd.to_datetime(frame[column],utc=True,errors="coerce").ge(FINAL_START).any():
            raise AssertionError(f"{column} reaches locked Final period")


def _finite(value):
    if isinstance(value,dict):return {str(key):_finite(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [_finite(item) for item in value]
    if isinstance(value,np.generic):value=value.item()
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def _config_hash(rule: str) -> str:
    return hashlib.sha256(PREREG.read_bytes()+b"\0"+rule.encode()).hexdigest()


def _event_identity(frame: pd.DataFrame) -> pd.Series:
    variant=frame.get("variant",pd.Series("",index=frame.index)).fillna("").astype(str)
    entry=frame.get("entry_type",pd.Series("market",index=frame.index)).fillna("market").astype(str)
    limit=frame.get("limit_price",pd.Series(np.nan,index=frame.index)).astype(object).fillna("").astype(str)
    return (frame.sym.astype(str)+"|"+frame.method.astype(str)+"|"+variant+"|"+
            frame.ts.astype(str)+"|"+frame.side.astype(str)+"|"+entry+"|"+limit)


def _load_events(root: Path, symbol: str, method: str) -> pd.DataFrame:
    parts=[]
    for path in sorted((root/symbol).glob("2023-*.parquet"))+sorted((root/symbol).glob("2024-*.parquet")):
        frame=pd.read_parquet(path)
        if len(frame):parts.append(frame[frame.method.eq(method)])
    if not parts:return pd.DataFrame()
    frame=pd.concat(parts,ignore_index=True)
    frame["ts"]=pd.to_datetime(frame.ts,utc=True)
    frame["known_at"]=pd.to_datetime(frame.known_at,utc=True)
    frame=frame[(frame.ts>=TEST_START)&(frame.ts<FINAL_START)]
    _assert_test_boundary(frame,"ts","known_at")
    frame["event_key"]=_event_identity(frame)
    return frame.sort_values(["known_at","event_key"]).drop_duplicates("event_key").reset_index(drop=True)


def _label_events(events: pd.DataFrame, symbol: str, rule: dict, data_root: Path,
                  *, opposite: bool=False) -> tuple[pd.DataFrame,int]:
    if events.empty:return pd.DataFrame(),0
    source=events.copy()
    if opposite:source["side"]=-source.side.astype(int)
    config={"sl_atr":[rule["sl_atr"]],"tp_r":[rule["tp_r"]],"max_hold_trading_days":1}
    parts=[];crossing=0
    month_key=source.ts.dt.tz_localize(None).dt.to_period("M")
    for month,group in source.groupby(month_key,sort=True):
        left=pd.Timestamp(month.start_time,tz="UTC")
        month_end=pd.Timestamp(month.end_time,tz="UTC")+pd.Timedelta(nanoseconds=1)
        read_right=min(month_end+pd.Timedelta(days=8),FINAL_START)
        bars=_bars(data_root,symbol,left,read_right)
        _assert_test_boundary(bars,"ts")
        feature_path=data_root/"features"/symbol/f"{month}.parquet"
        features=pd.read_parquet(feature_path,columns=["ts","1h_atr14"])
        _assert_test_boundary(features,"ts")
        atr_map=pd.Series(features["1h_atr14"].to_numpy(float),index=pd.to_datetime(features.ts,utc=True))
        result=_event_jobs(group,bars,atr_map,config,symbol)
        if result.empty:continue
        if symbol=="BTCUSDT":
            result=apply_perp_costs(result,bars,_funding(data_root,symbol,left,read_right))
        else:
            result["cost_R"]=result.gross_R-result.net_R
            result["spread_R"]=result.cost_R
            result["venue"]="dukascopy_cfd"
        resolved=pd.to_datetime(result.exit_ts,utc=True,errors="coerce").lt(FINAL_START)
        crossing+=int((~resolved).sum())
        result=result.loc[resolved].copy()
        result["label_end_ts"]=pd.to_datetime(result.exit_ts,utc=True)
        _assert_test_boundary(result,"ts","known_at","entry_ts","exit_ts","label_end_ts")
        parts.append(result)
    if not parts:return pd.DataFrame(),crossing
    return pd.concat(parts,ignore_index=True),crossing


def _random_percentile(signals: pd.DataFrame, opposite: pd.DataFrame, seeds: int=200) -> tuple[float|None,int]:
    if signals.empty:return None,0
    other=opposite.set_index("event_key").net_R
    matched=signals[signals.event_key.isin(other.index)].copy()
    if matched.empty:return None,0
    normal=matched.net_R.to_numpy(float);reverse=matched.event_key.map(other).to_numpy(float)
    observed=float(normal.mean());scores=[]
    for seed in range(seeds):
        swap=np.random.default_rng(seed).integers(0,2,len(normal),dtype=np.int8).astype(bool)
        scores.append(float(np.where(swap,reverse,normal).mean()))
    return float(100*np.mean(np.asarray(scores)<observed)),len(normal)


def _rule_result(rule_name: str, rule: dict, event_root: Path, data_root: Path) -> tuple[dict,pd.DataFrame]:
    normal_parts=[];opposite_parts=[];dropped=0;events_n=0
    for symbol in rule["symbols"]:
        events=_load_events(event_root,symbol,rule_name);events_n+=len(events)
        normal,crossing=_label_events(events,symbol,rule,data_root)
        reverse,_=_label_events(events,symbol,rule,data_root,opposite=True)
        dropped+=crossing;normal_parts.append(normal);opposite_parts.append(reverse)
    candidates=pd.concat(normal_parts,ignore_index=True) if normal_parts else pd.DataFrame()
    reverse=pd.concat(opposite_parts,ignore_index=True) if opposite_parts else pd.DataFrame()
    signals=gate_open_signals(candidates)
    percentile,matched=_random_percentile(signals,reverse,200)
    pooled=metrics(signals,None);pooled["random_direction_percentile"]=percentile
    pooled["random_direction_matched_signals"]=matched
    pooled["events"]=events_n;pooled["boundary_dropped"]=dropped
    pooled["pass"]=(pooled.get("net_avg_R") is not None and pooled["net_avg_R"]>0 and
                    pooled.get("profit_factor") is not None and pooled["profit_factor"]>1 and
                    percentile is not None and percentile>=75)
    pooled["per_market"]={symbol:metrics(signals[signals.sym.eq(symbol)],None)
                          for symbol in rule["symbols"]}
    pooled["per_year"]={str(year):metrics(signals[pd.to_datetime(signals.entry_ts,utc=True).dt.year.eq(year)],None)
                        for year in (2023,2024)}
    return _finite(pooled),signals


def run(data_root: Path=Path("data"), event_root: Path=Path("data/test_v1_events"),
        output: Path=Path("reports/research/test_v1"),
        ledger: Path=Path("reports/trials.csv")) -> Path:
    wide=Path("hpc/roihu/sequence/configs/wide_v1.json")
    if hashlib.sha256(wide.read_bytes()).hexdigest()!=WIDE_CONFIG_SHA:raise RuntimeError("wide config changed")
    rows=[]
    for rule in RULES:
        row=dict(zip(FIELDS,[f"test-v1-{rule}",str(pd.Timestamp.now(tz="UTC").date()),_config_hash(rule),rule,
            json.dumps({"protocol":"test_v1","frozen_code":FROZEN_CODE,**RULES[rule]},sort_keys=True),
            "2023-01-01 / 2024-12-31","test","{}","one-time preregistered Test exam v1"]))
        validate_test_trial(ledger,row);rows.append(row)
    for symbol in sorted({symbol for rule in RULES.values() for symbol in rule["symbols"]}):
        names={name for name,rule in RULES.items() if symbol in rule["symbols"]}
        replay_events_only(symbol,2023,2024,event_root,data_root,method_names=names,
                           hard_end_exclusive=FINAL_START)
    results={};signals={}
    for name,rule in RULES.items():results[name],signals[name]=_rule_result(name,rule,event_root,data_root)
    payload={"protocol":"test_v1","period":"test","test_start":str(TEST_START),
             "final_boundary_exclusive":str(FINAL_START),"frozen_code":FROZEN_CODE,
             "wide_config_sha256":WIDE_CONFIG_SHA,"rules":results,
             "statement":"The 2025+ Final period was not loaded for decisions or labels."}
    output.mkdir(parents=True,exist_ok=True)
    (output/"test_exam_report.json").write_text(json.dumps(_finite(payload),indent=2,allow_nan=False)+"\n")
    def f(value):return "NA" if value is None else f"{value:.4f}"
    lines=["# One-time protocol Test exam v1","",
        "**Test was graded once using the preregistered fixed rules. The 2025+ Final period was not loaded for decisions or labels.**","",
        "| Rule | Events | Trades | Hit | Net avg R | t | PF | Daily Sharpe | MDD | Random pct | Result |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for name,item in results.items():
        lines.append(f"| {name} | {item['events']} | {item['n']} | {f(item.get('hit_rate'))} | {f(item.get('net_avg_R'))} | {f(item.get('t_stat'))} | {f(item.get('profit_factor'))} | {f(item.get('daily_sharpe'))} | {f(item.get('max_drawdown'))} | {f(item.get('random_direction_percentile'))} | {'PASS' if item['pass'] else 'FAIL'} |")
    for name,item in results.items():
        lines += ["",f"## {name}","",f"Boundary-crossing trades dropped: {item['boundary_dropped']}.","",
                  "| Scope | n | Hit | Net avg R | t | PF | Sharpe | MDD |","|---|---:|---:|---:|---:|---:|---:|---:|"]
        for scope,value in [*item["per_market"].items(),*[(f"year {k}",v) for k,v in item["per_year"].items()]]:
            lines.append(f"| {scope} | {value['n']} | {f(value.get('hit_rate'))} | {f(value.get('net_avg_R'))} | {f(value.get('t_stat'))} | {f(value.get('profit_factor'))} | {f(value.get('daily_sharpe'))} | {f(value.get('max_drawdown'))} |")
    report=output/"test_exam_report.md";report.write_text("\n".join(lines)+"\n")
    for row in rows:
        row["metrics"]=json.dumps(results[row["method"]],sort_keys=True,allow_nan=False)
        append_test_trial_once(ledger,row)
    return report


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--data-root",type=Path,default=Path("data"))
    parser.add_argument("--event-root",type=Path,default=Path("data/test_v1_events"))
    parser.add_argument("--output",type=Path,default=Path("reports/research/test_v1"))
    args=parser.parse_args();print(run(args.data_root,args.event_root,args.output))


if __name__=="__main__":main()
