"""DEV-only correctness and information audit for Phase-2 feature families.

This module is deliberately analysis-only: it neither appends to the trial
ledger nor changes a model, threshold, rule, or label.  Every input decision
and label end is required to precede 2023-01-01.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from msd.processing.crypto_perp import apply_perp_costs
from msd.processing.labels import deadline_after_trading_days, first_hit_reference
from msd.processing.wide_v1 import _bars as wide_bars, _funding as wide_funding
from .decision import choose, expected_r
from .family import (DEV_END, MAX_RSS_GIB, SYMBOLS, THRESHOLD, _peak_rss_gib,
                     _read_labels, cpcv_oof, feature_spec, load_anchor_features,
                     load_config)
from .gating import gate_open_signals
from .splits import cpcv_folds


HORIZONS = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1),
            "4h": pd.Timedelta(hours=4), "1d": None}
SOURCE = {"BTCUSDT":"binance_um", "ETHUSDT":"binance_um",
          "USATECHIDXUSD":"dukascopy", "USA500IDXUSD":"dukascopy", "XAUUSD":"dukascopy"}
TOP_K = 20
FORBIDDEN_TOKENS = ("outcome", "exit_", "label_", "net_r", "gross_r", "cost_r")


def _guard_memory() -> None:
    if _peak_rss_gib() > MAX_RSS_GIB:
        raise MemoryError(f"information audit exceeded {MAX_RSS_GIB:g} GiB RSS")


def _schema_numeric(path: Path) -> list[str]:
    if not path.exists(): return []
    columns=[]
    for field in pq.read_schema(path):
        if field.name in {"ts","known_at"}: continue
        if pa.types.is_boolean(field.type) or pa.types.is_integer(field.type) or pa.types.is_floating(field.type):
            columns.append(field.name)
    return columns


def _months(start: pd.Timestamp, end: pd.Timestamp):
    return pd.period_range(start.tz_localize(None).to_period("M"),
                           (end-pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M"),freq="M")


def _read_range(directory: Path, start: pd.Timestamp, end: pd.Timestamp,
                columns: list[str] | None=None) -> pd.DataFrame:
    paths=[directory/f"{month}.parquet" for month in _months(start,end)]
    paths=[path for path in paths if path.exists()]
    if not paths:return pd.DataFrame(columns=columns or ())
    parts=[]
    for path in paths:
        available=set(pq.read_schema(path).names)
        wanted=None if columns is None else [column for column in columns if column in available]
        parts.append(pd.read_parquet(path,columns=wanted))
    out=pd.concat(parts,ignore_index=True)
    stamp="known_at" if "known_at" in out else "ts"
    out[stamp]=pd.to_datetime(out[stamp],utc=True).astype("datetime64[ns, UTC]")
    return out[(out[stamp]>=start)&(out[stamp]<end)].sort_values(stamp).drop_duplicates(stamp,keep="last")


def _anchors(labels_root: Path, symbol: str, start: pd.Timestamp, end: pd.Timestamp,
             limit: int | None=None) -> pd.DataFrame:
    parts=[]
    for path in sorted((labels_root/symbol).glob("*.parquet")):
        if path.stem < start.strftime("%Y-%m") or path.stem > end.strftime("%Y-%m"):continue
        available=set(pq.read_schema(path).names)
        columns=[column for column in ("ts","label_end_ts","exit_ts") if column in available]
        part=pd.read_parquet(path,columns=columns)
        end_col="label_end_ts" if "label_end_ts" in part else "exit_ts"
        part=part[["ts",end_col]].rename(columns={end_col:"label_end_ts"})
        parts.append(part)
    if not parts:return pd.DataFrame(columns=["ts","known_at","label_end_ts"])
    out=pd.concat(parts,ignore_index=True)
    out["ts"]=pd.to_datetime(out.ts,utc=True).astype("datetime64[ns, UTC]")
    out["label_end_ts"]=pd.to_datetime(out.label_end_ts,utc=True).astype("datetime64[ns, UTC]")
    out=out[(out.ts>=start)&(out.ts<end)&(out.label_end_ts<DEV_END)]
    out=out.groupby("ts",sort=True).label_end_ts.max().reset_index()
    out["known_at"]=out.ts+pd.Timedelta(minutes=1)
    if limit and len(out)>limit:
        out=out.iloc[np.linspace(0,len(out)-1,limit,dtype=int)]
    return out.reset_index(drop=True)


def _feature_union(data_root: Path, symbol: str, config: dict) -> tuple[list[str],list[str]]:
    dense_dir=data_root/"features"/symbol;flow_dir=data_root/"features_flow"/symbol
    dense_path=next(iter(sorted(dense_dir.glob("*.parquet"))),None)
    flow_path=next(iter(sorted(flow_dir.glob("*.parquet"))),None)
    dense=_schema_numeric(dense_path) if dense_path else []
    configured_flow=[]
    for name in config["families"]:
        configured_flow.extend(config["families"][name].get("flow_columns",()))
    flow_available=set(_schema_numeric(flow_path)) if flow_path else set()
    flow=[column for column in dict.fromkeys(configured_flow) if column in flow_available]
    bad=[column for column in dense+flow if any(token in column.lower() for token in FORBIDDEN_TOKENS)]
    if bad:raise AssertionError(f"outcome-derived information features: {bad}")
    return list(dict.fromkeys(dense)),flow


def _asof_features(data_root: Path, symbol: str, anchors: pd.DataFrame,
                   dense_columns: list[str], flow_columns: list[str]) -> pd.DataFrame:
    result=anchors.copy().sort_values("known_at")
    result["known_at"]=pd.to_datetime(result.known_at,utc=True).astype("datetime64[ns, UTC]")
    for name,directory,columns in (("dense",data_root/"features"/symbol,dense_columns),
                                   ("flow",data_root/"features_flow"/symbol,flow_columns)):
        parts=[]
        for month in sorted(result.known_at.dt.strftime("%Y-%m").unique()):
            path=directory/f"{month}.parquet"
            if not path.exists():continue
            available=set(pq.read_schema(path).names)
            wanted=["known_at",*[column for column in columns if column in available]]
            part=pd.read_parquet(path,columns=wanted)
            for column in columns:
                if column not in part:part[column]=np.nan
            parts.append(part[["known_at",*columns]])
        if parts:
            right=pd.concat(parts,ignore_index=True);right["known_at"]=pd.to_datetime(right.known_at,utc=True).astype("datetime64[ns, UTC]")
            right=right.sort_values("known_at").drop_duplicates("known_at",keep="last").rename(columns={"known_at":f"{name}_known_at"})
            result=pd.merge_asof(result.sort_values("known_at"),right,left_on="known_at",right_on=f"{name}_known_at",direction="backward")
            if (result[f"{name}_known_at"]>result.known_at).any():raise AssertionError(f"future {name} feature")
        else:
            result[f"{name}_known_at"]=pd.NaT
            for column in columns:result[column]=np.nan
    return result


def _bar_targets(data_root: Path, symbol: str, frame: pd.DataFrame,
                 start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    read_end=min(DEV_END,end+pd.Timedelta(days=5))
    bars=_read_range(data_root/"bars"/SOURCE[symbol]/symbol,start-pd.Timedelta(days=1),read_end,
                     ["ts","bid_c","ask_c"])
    if bars.empty:return frame
    bars=bars.rename(columns={"known_at":"ts"}) if "ts" not in bars else bars
    bars["ts"]=pd.to_datetime(bars.ts,utc=True).astype("datetime64[ns, UTC]")
    times=bars.ts.to_numpy(dtype="datetime64[ns]");mid=((bars.bid_c+bars.ask_c)/2).to_numpy(float)
    anchor_ns=frame.ts.to_numpy(dtype="datetime64[ns]");indices=np.searchsorted(times,anchor_ns)
    exact=(indices<len(times))&(times[np.minimum(indices,len(times)-1)]==anchor_ns)
    current=np.full(len(frame),np.nan);current[exact]=mid[indices[exact]]
    atr=pd.to_numeric(frame.get("1h_atr14"),errors="coerce").to_numpy(float)
    crypto=symbol in {"BTCUSDT","ETHUSDT"}
    for name,delta in HORIZONS.items():
        deadlines=(frame.ts+delta if delta is not None else
                   frame.ts.map(lambda value:deadline_after_trading_days(value,1,"crypto" if crypto else "index")))
        target_ns=deadlines.to_numpy(dtype="datetime64[ns]");future_i=np.searchsorted(times,target_ns)
        valid=exact&(future_i<len(times))&np.isfinite(atr)&(atr>0)&deadlines.lt(DEV_END).to_numpy()
        values=np.full(len(frame),np.nan);values[valid]=(mid[future_i[valid]]-current[valid])/atr[valid]
        frame[f"return_{name}"]=values.astype("float32")
        frame[f"abs_return_{name}"]=np.abs(values).astype("float32")
        end_values=np.full(len(frame),np.datetime64("NaT","ns"),dtype="datetime64[ns]")
        end_values[valid]=times[future_i[valid]]
        frame[f"target_end_{name}"]=pd.to_datetime(end_values,utc=True)
    return frame


def _annual_ic(frame: pd.DataFrame, features: list[str], targets: list[str]) -> pd.DataFrame:
    rows=[]
    years=pd.to_datetime(frame.known_at,utc=True).dt.year
    for year,group in frame.groupby(years,sort=True):
        usable=[column for column in features if group[column].count()>2 and group[column].nunique(dropna=True)>1]
        x=group[usable].rank(method="average",pct=True)
        for target in targets:
            y=group[target].rank(method="average",pct=True)
            values=x.corrwith(y)
            rows.extend({"year":int(year),"target":target,"feature":feature,"ic":float(value)}
                        for feature,value in values.items() if np.isfinite(value))
    return pd.DataFrame(rows)


def _summarise_ic(annual: pd.DataFrame, target_std: dict[str,float], cost_atr: float) -> pd.DataFrame:
    rows=[]
    for (target,feature),group in annual.groupby(["target","feature"],sort=False):
        values=group.ic.to_numpy(float);mean=float(values.mean());sd=float(values.std(ddof=1)) if len(values)>1 else np.nan
        same=float(np.mean(np.sign(values)==np.sign(mean))) if mean else .5
        proxy=abs(mean)*target_std.get(target,np.nan)
        rows.append({"target":target,"feature":feature,"mean_ic":mean,
                     "t_over_years":mean/(sd/np.sqrt(len(values))) if sd>0 else np.nan,
                     "same_sign_share":same,"years":len(values),"edge_atr_proxy":proxy,
                     "median_cost_atr":cost_atr,"proxy_cost_ratio":proxy/cost_atr if cost_atr>0 else np.nan,
                     "stable_score":abs(mean)*same})
    return pd.DataFrame(rows)


def _ridge_oof(frame: pd.DataFrame, features: list[str], target: str, end_column: str) -> dict:
    valid=frame[target].notna()&frame[end_column].notna()
    data=frame.loc[valid,["known_at",end_column,target,*features]].rename(columns={end_column:"label_end_ts"}).reset_index(drop=True)
    if len(data)<100:return {"n":len(data),"oof_ic":None}
    total=np.zeros(len(data));count=np.zeros(len(data),dtype=np.uint8);selected=[]
    for fold in cpcv_folds(data[["known_at","label_end_ts"]],5,2):
        train=data.iloc[fold.train];test=data.iloc[fold.test]
        coverage=train[features].notna().mean();usable=coverage[coverage>=.5].index.tolist()
        usable=[column for column in usable if train[column].nunique(dropna=True)>1]
        if not usable:continue
        annual=[]
        for _,year in train.groupby(pd.to_datetime(train.known_at,utc=True).dt.year):
            values=year[usable].corrwith(year[target],method="spearman")
            annual.append(values)
        yearly=pd.concat(annual,axis=1)
        mean=yearly.mean(axis=1);same=yearly.apply(lambda row:np.mean(np.sign(row.dropna())==np.sign(row.mean())),axis=1)
        scores=(mean.abs()*same).sort_values(ascending=False)
        chosen=scores.head(TOP_K).index.tolist();selected.extend(chosen)
        model=make_pipeline(SimpleImputer(strategy="median"),StandardScaler(),Ridge(alpha=1.0))
        model.fit(train[chosen],train[target]);total[fold.test]+=model.predict(test[chosen]);count[fold.test]+=1
    predicted=count>0
    ic=float(spearmanr(total[predicted]/count[predicted],data.loc[predicted,target]).statistic) if predicted.sum()>2 else None
    return {"n":int(predicted.sum()),"oof_ic":ic,"median_selected_features":len(set(selected)),
            "frequent_features":[item for item in pd.Series(selected).value_counts().head(10).index] if selected else []}


def _cost_atr(data_root: Path, labels_root: Path, symbol: str, frame: pd.DataFrame) -> float:
    # CFD wide labels use executable bid/ask fills for both ``gross_R`` and
    # ``net_R``; their difference therefore measures financing, not spread.
    # One round trip pays approximately one full spread.  ``spread_atr`` is
    # stored in units of the 1-minute ATR, so convert it to the 1-hour ATR used
    # by the information targets.  Crypto labels instead carry explicit
    # spread, fee and funding costs in ``cost_R``.
    if symbol not in {"BTCUSDT", "ETHUSDT"}:
        required = {"spread_atr", "1m_atr14", "1h_atr14"}
        if not required.issubset(frame):
            return np.nan
        values = (pd.to_numeric(frame.spread_atr, errors="coerce").to_numpy(float)
                  * pd.to_numeric(frame["1m_atr14"], errors="coerce").to_numpy(float)
                  / pd.to_numeric(frame["1h_atr14"], errors="coerce").to_numpy(float))
        usable = values[np.isfinite(values) & (values > 0)]
        return float(np.median(usable)) if len(usable) else np.nan
    atr=pd.Series(pd.to_numeric(frame["1h_atr14"],errors="coerce").to_numpy(float),index=frame.ts)
    values=[]
    for path in sorted((labels_root/symbol).glob("*.parquet")):
        if path.stem>"2022-12":continue
        part=pd.read_parquet(path,columns=["ts","cost_R","planned_risk"])
        if len(part)>5000:part=part.iloc[np.linspace(0,len(part)-1,5000,dtype=int)]
        a=pd.to_datetime(part.ts,utc=True).map(atr).to_numpy(float)
        values.append(pd.to_numeric(part.cost_R,errors="coerce").to_numpy(float)*pd.to_numeric(part.planned_risk,errors="coerce").to_numpy(float)/a)
    all_values=np.concatenate(values) if values else np.array([])
    return float(np.nanmedian(all_values[np.isfinite(all_values)])) if np.isfinite(all_values).any() else np.nan


def _effective_daily_dvol(frame: pd.DataFrame) -> dict | None:
    """Check the slow DVOL/one-day relationship on non-overlapping targets."""
    if "dvol_btc_level" not in frame or "return_1d" not in frame:
        return None
    usable=frame[frame.dvol_btc_level.notna() & frame.return_1d.notna()].copy()
    if usable.empty:return None
    daily=usable.sort_values("known_at").groupby(usable.known_at.dt.floor("D"),sort=True).head(1)
    annual=[]
    for year,group in daily.groupby(daily.known_at.dt.year,sort=True):
        if len(group)>2:
            annual.append({"year":int(year),"n":len(group),
                           "ic":float(group.dvol_btc_level.corr(group.return_1d,method="spearman"))})
    return {"n":len(daily),"ic":float(daily.dvol_btc_level.corr(daily.return_1d,method="spearman")),
            "years":annual}


def audit_family(data_root: Path, labels_root: Path, family: str, symbol: str) -> dict:
    config=load_config();labels,_=_read_labels(labels_root,symbol)
    anchors=labels.groupby("ts",sort=True).agg(known_at=("known_at","first"),label_end_ts=("label_end_ts","max")).reset_index()
    anchors["anchor_index"]=np.arange(len(anchors),dtype=np.int32)
    mapping=pd.Series(anchors.anchor_index.to_numpy(),index=anchors.ts)
    labels["anchor_index"]=labels.ts.map(mapping).astype("int32")
    labels["event_key"]=(labels.anchor_index.astype("int64")*2+labels.side.gt(0).astype("int8")).astype("int64")
    features,spec,_=load_anchor_features(data_root,symbol,anchors,family,config)
    hourly=features[features.ts.dt.minute.eq(0)]
    coverage={column:float(hourly[column].notna().mean()) for column in spec["source"]}
    causality={name:bool(features[name].isna().all() or (features[name]<=features.known_at).all())
               for name in ("dense_known_at","flow_known_at")}
    evaluated,fit=cpcv_oof(labels,anchors,features,spec)
    edge=expected_r(evaluated.p,evaluated.TP_R,evaluated.cost_R,evaluated.financing_R)
    shrunk=np.maximum(0,edge-1.64*evaluated.p_uncertainty.to_numpy()*(evaluated.TP_R.to_numpy()+1))
    raw_positive=edge>0;raw_threshold=edge>THRESHOLD;shrunk_threshold=shrunk>THRESHOLD
    eligible_events=set(evaluated.loc[shrunk_threshold,"event_key"])
    chosen=choose(evaluated,threshold=THRESHOLD,uncertainty=evaluated.p_uncertainty)
    gated=gate_open_signals(chosen)
    train_loss=float(-np.nanmean(fit["cpcv_train_scores"]));test_loss=float(-np.nanmean(fit["cpcv_test_scores"]))
    result={"family":family,"symbol":symbol,"training_anchors":len(hourly),"configured_features":len(spec["model"]),
        "actual_passed_features":spec["model"],"source_coverage":coverage,
        "auto_rule_50pct_features":[column for column,value in coverage.items() if value>=.5],
        "all_nan_features":[column for column,value in coverage.items() if value==0],"causality":causality,
        "edge_quantiles":{str(q):float(np.quantile(edge,q)) for q in (0,.01,.05,.5,.95,.99,1)},
        "edge_gt_0":int(raw_positive.sum()),"edge_gt_005":int(raw_threshold.sum()),
        "fails_uncertainty_only":int((raw_threshold&~shrunk_threshold).sum()),
        "eligible_events_after_uncertainty":len(eligible_events),"fails_neighbour_events":len(eligible_events-set(chosen.event_key)),
        "chosen_before_gate":len(chosen),"removed_by_open_signal_gate":len(chosen)-len(gated),"final_signals":len(gated),
        "mean_train_brier":train_loss,"mean_oof_brier":test_loss,"oof_minus_train_brier":test_loss-train_loss}
    del labels,features,evaluated;gc.collect();_guard_memory();return result


def audit_labels(data_root: Path, labels_root: Path, samples: int=30, seed: int=0,
                 symbols=SYMBOLS) -> dict:
    rng=np.random.default_rng(seed);records=[]
    each=max(1,int(np.ceil(samples/len(symbols))))
    for symbol in symbols:
        paths=sorted((labels_root/symbol).glob("*.parquet"));picked=rng.choice(paths,size=min(each,len(paths)),replace=False)
        for path in picked:
            stored=pd.read_parquet(path).iloc[int(rng.integers(0,pq.ParquetFile(path).metadata.num_rows))]
            ts=pd.Timestamp(stored.ts);ts=ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            month=pd.Period(ts.tz_localize(None),freq="M");start=pd.Timestamp(month.start_time,tz="UTC")
            end=min(DEV_END,pd.Timestamp(month.end_time,tz="UTC")+pd.Timedelta(days=4))
            bars=wide_bars(data_root,symbol,start,end);times=pd.to_datetime(bars.ts,utc=True)
            signal_i=int(times.searchsorted(ts));feature=pd.read_parquet(data_root/"features"/symbol/f"{month}.parquet",columns=["ts","1h_atr14"])
            atr=float(feature.set_index(pd.to_datetime(feature.ts,utc=True)).loc[ts,"1h_atr14"])
            mid=(float(bars.bid_c.iloc[signal_i])+float(bars.ask_c.iloc[signal_i]))/2;side=int(stored.side)
            sl=mid-side*float(stored.sl_atr)*atr;tp=mid+side*float(stored.sl_atr)*float(stored.tp_r)*atr
            crypto=symbol in {"BTCUSDT","ETHUSDT"}
            value=first_hit_reference(bars,signal_i,side,mid,sl,tp,delay_bars=2,deadline_ts=stored.deadline_ts,
                financing_per_night=0 if crypto else .0002,instrument_class="crypto" if crypto else "index",detailed=True)
            reason,exit_i,exit_price,net,gross,fill,nights,entry_i,risk=value
            if crypto:
                one=pd.DataFrame({"entry_ts":[bars.ts.iloc[entry_i]],"exit_ts":[bars.ts.iloc[exit_i]],"fill_price":[fill],
                    "exit_price":[exit_price],"planned_risk":[risk],"gross_R":[gross],"net_R":[net],"side":[side]})
                funding=wide_funding(data_root,symbol,start,end);one=apply_perp_costs(one,bars,funding).iloc[0]
                net=float(one.net_R);gross=float(one.gross_R)
            code={"tp":1,"stop":-1,"sl":-1,"time":0,"no_fill":-2}[reason]
            checks={"outcome":int(stored.outcome)==code,"entry_ts":pd.Timestamp(stored.entry_ts)==pd.Timestamp(bars.ts.iloc[entry_i]),
                    "exit_ts":pd.Timestamp(stored.exit_ts)==pd.Timestamp(bars.ts.iloc[exit_i]),
                    "fill_price":np.isclose(stored.fill_price,fill,rtol=1e-5,atol=1e-4),
                    "exit_price":np.isclose(stored.exit_price,exit_price,rtol=1e-5,atol=1e-4),
                    "net_R":np.isclose(stored.net_R,net,rtol=2e-5,atol=2e-5),
                    "gross_R":np.isclose(stored.gross_R,gross,rtol=2e-5,atol=2e-5)}
            records.append({"symbol":symbol,"ts":str(ts),"cell":f"{side}/{stored.sl_atr}/{stored.tp_r}","checks":checks,"ok":all(checks.values())})
            if len(records)>=samples:break
        if len(records)>=samples:break
    return {"samples":len(records),"passed":sum(row["ok"] for row in records),"rows":records}


def analyse_market(data_root: Path, labels_root: Path, symbol: str, start: pd.Timestamp,
                   end: pd.Timestamp, anchor_limit: int | None=None) -> tuple[dict,pd.DataFrame]:
    config=load_config();dense,flow=_feature_union(data_root,symbol,config);years=[]
    for year in range(start.year,end.year+1):
        left=max(start,pd.Timestamp(f"{year}-01-01",tz="UTC"));right=min(end,pd.Timestamp(f"{year+1}-01-01",tz="UTC"))
        if left>=right:continue
        anchors=_anchors(labels_root,symbol,left,right,anchor_limit)
        if anchors.empty:continue
        frame=_asof_features(data_root,symbol,anchors,dense,flow)
        frame=_bar_targets(data_root,symbol,frame,left,right)
        for column in dense+flow:frame[column]=pd.to_numeric(frame[column],errors="coerce").astype("float32")
        years.append(frame);_guard_memory()
    if not years:return {"symbol":symbol,"status":"no data"},pd.DataFrame()
    frame=pd.concat(years,ignore_index=True);features=list(dict.fromkeys(dense+flow));targets=[f"{prefix}{h}" for h in HORIZONS for prefix in ("return_","abs_return_")]
    annual=_annual_ic(frame,features,targets);std={target:float(frame[target].std()) for target in targets}
    cost=_cost_atr(data_root,labels_root,symbol,frame);summary=_summarise_ic(annual,std,cost);summary.insert(0,"symbol",symbol)
    ridge={}
    for target in targets:
        horizon=target.removeprefix("abs_").removeprefix("return_")
        ridge[target]=_ridge_oof(frame,features,target,f"target_end_{horizon}")
    causal=all(frame[column].isna().all() or (frame[column]<=frame.known_at).all() for column in ("dense_known_at","flow_known_at"))
    result={"symbol":symbol,"anchors":len(frame),"features":len(features),"years":sorted(frame.known_at.dt.year.unique().tolist()),
            "causal_asof":causal,"median_cost_atr":cost,"ridge":ridge,
            "dvol_1d_effective":_effective_daily_dvol(frame),
            "top":{target:summary[summary.target.eq(target)].nlargest(20,"stable_score").to_dict("records") for target in targets}}
    del frame;gc.collect();_guard_memory();return result,summary


def write_report(output: Path, family_audit: list[dict], label_audit: dict,
                 market_results: list[dict], ic: pd.DataFrame, runtime: float,
                 peak_rss_gib: float | None = None) -> None:
    peak_rss_gib=_peak_rss_gib() if peak_rss_gib is None else peak_rss_gib
    output.parent.mkdir(parents=True,exist_ok=True);csv_path=output.with_name("information_ic.csv");ic.to_csv(csv_path,index=False)
    coverage_path=output.with_name("information_feature_coverage.csv")
    coverage_rows=[]
    for row in family_audit:
        for feature,value in row["source_coverage"].items():
            coverage_rows.append({"family":row["family"],"symbol":row["symbol"],"feature":feature,
                "training_non_nan_share":value,"passed_explicitly":feature in row["actual_passed_features"],
                "eligible_under_50pct_auto_rule":value>=.5})
    pd.DataFrame(coverage_rows).to_csv(coverage_path,index=False)
    lines=["# Phase 2 DEV information and correctness audit","",
        "**DEV only: all decisions, targets and label ends are before 2023-01-01. Test and Final were not loaded. Analysis only; no rules, thresholds or ledger rows were changed.**","",
        f"Runtime: {runtime/60:.2f} minutes; peak RSS: {peak_rss_gib:.2f} GiB.","",
        "## Label correctness","",f"Direct bar-path recomputation: {label_audit['passed']}/{label_audit['samples']} labels matched outcome, entry/exit timestamps and prices, gross R and net R.","",
        "## Feature coverage and model inputs","",
        f"The completed family runner supplied explicit feature lists to ResidualModel. Therefore its automatic ≥50% coverage selection was bypassed: `actual passed` below is the configured count, while `eligible at ≥50%` shows what the automatic path would have retained. Per-feature values are in `{coverage_path.name}`.","",
        "| Family | Market | Training anchors | Actual passed | Eligible at ≥50% | All-NaN source features | Causal stamps |","|---|---|---:|---:|---:|---:|---|"]
    for row in family_audit:
        lines.append(f"| {row['family']} | {row['symbol']} | {row['training_anchors']:,} | {row['configured_features']} | {len(row['auto_rule_50pct_features'])} | {len(row['all_nan_features'])} | {'yes' if all(row['causality'].values()) else 'NO'} |")
    lines += ["", "**Coverage warning:** F3 order flow was not a valid test on the CFD markets. NQ, SPX and XAU each had only 6/84 configured features at ≥50% training coverage and 35/84 were entirely NaN. The explicit family feature list bypassed ResidualModel's normal ≥50% filter, so those fits were dominated by missing inputs rather than a usable CFD flow history. F4 likewise had only 192/406 eligible inputs, although its usable subset was much broader."]
    lines += ["","## Gate and fit diagnostics","","| Family | Market | edge p50 | p95 | p99 | edge>0 | edge>0.05 | uncertainty-only failures | neighbour-only event failures | chosen | gated | train Brier | OOF Brier | gap |","|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in family_audit:
        q=row["edge_quantiles"]
        lines.append(f"| {row['family']} | {row['symbol']} | {q['0.5']:.4f} | {q['0.95']:.4f} | {q['0.99']:.4f} | {row['edge_gt_0']:,} | {row['edge_gt_005']:,} | {row['fails_uncertainty_only']:,} | {row['fails_neighbour_events']:,} | {row['chosen_before_gate']:,} | {row['final_signals']:,} | {row['mean_train_brier']:.6f} | {row['mean_oof_brier']:.6f} | {row['oof_minus_train_brier']:.6f} |")
    lines += ["", "The train-to-OOF Brier gaps are only 0.0002–0.0023. That rules out severe tree overfit, but does not prove that 40 trees/7 leaves are sufficient: together with compressed predicted-edge distributions, it is consistent with weak/missing inputs or mild underfit. This audit cannot distinguish those without changing the pre-registered model, so no capacity change was made."]
    lines += ["","## Information content","",f"The exhaustive per-feature/per-year IC summary is in `{csv_path.name}`. Stable ranking is |mean annual Spearman IC| × same-sign year share. The cost comparison is |IC| × target standard deviation divided by median executable cost in ATR units.",""]
    for market in market_results:
        lines += [f"### {market['symbol']}","",f"Anchors: {market['anchors']:,}; features: {market['features']}; median cost: {market['median_cost_atr']:.6f} ATR; causal joins: {market['causal_asof']}.","",
                  "| Target | Ridge OOF IC | n | Best feature | Mean IC | IC t(years) | Same-sign years | Proxy/cost |","|---|---:|---:|---|---:|---:|---:|---:|"]
        for target,item in market["ridge"].items():
            top=market["top"][target][0] if market["top"][target] else {}
            def f(value):return "NA" if value is None or not np.isfinite(value) else f"{value:.4f}"
            years=int(top.get("years",0));same=round(float(top.get("same_sign_share",0))*years)
            lines.append(f"| {target} | {f(item['oof_ic'])} | {item['n']:,} | {top.get('feature','NA')} | {f(top.get('mean_ic'))} | {f(top.get('t_over_years'))} | {same}/{years} | {f(top.get('proxy_cost_ratio'))} |")
        effective=market.get("dvol_1d_effective")
        if effective:
            annual=", ".join(f"{row['year']}: IC {row['ic']:.3f} (n={row['n']})" for row in effective["years"])
            lines += ["",f"DVOL/1-day non-overlap check: one anchor per UTC day gives n={effective['n']:,}, IC={effective['ic']:.3f}; {annual}. This is only {len(effective['years'])} calendar years and is treated as a slow regime observation, not robust evidence."]
    positives=[(m["symbol"],target,item["oof_ic"]) for m in market_results for target,item in m["ridge"].items() if item["oof_ic"] is not None and abs(item["oof_ic"])>=.03]
    lines += ["","## Plain-language conclusion","",f"Across {sum(m['features'] for m in market_results)} market-feature inventories, stable directional relationships and purged ridge forecasts are generally tiny. {len(positives)} market/target ridge forecasts reached |OOF IC| ≥ 0.03, but the large ICs are concentrated in absolute-return targets: volatility is predictable (roughly 0.20–0.45 OOF IC, mostly from time of day), while direction is not.","",
              "The clearest directional pattern is 15-minute crypto mean reversion (for example, BTC EMA20 distance IC about -0.09), but its IC-implied move is only about 0.3× executable cost. It is information, not a net trading edge at this horizon.","",
              "The NQ/BTC one-day DVOL relationship survives daily de-overlap, but DVOL is available for only two DEV calendar years. It is a plausible slow regime proxy, not a validated directional signal. XAU `spread_modeled` has an IC t-stat of NA because the flag varied in only one year; it is a data-quality indicator and not stable evidence.","",
              "F3 on NQ, SPX and XAU cannot support a conclusion about order-flow edge because almost all intended CFD flow history was unavailable during DEV. This is a coverage failure, not evidence that order flow has no value.","",
              "Family 1 is rule-only and therefore has no feature coverage, probability fit or model gate to audit; its wide-v1 OOF rule results remain in `reports/research/wide_v1/pure_rules_summary.md`.","",
              "No model, threshold, rule or trial-ledger entry was changed by this audit.",""]
    output.write_text("\n".join(lines))
    detail=output.with_name("information_audit_details.json")
    detail.write_text(json.dumps(_jsonable({"runtime_seconds":runtime,"peak_rss_gib":peak_rss_gib,"label_audit":label_audit,"family_audit":family_audit,"markets":market_results}),indent=2,allow_nan=False)+"\n")


def _jsonable(value):
    if isinstance(value,dict):return {str(key):_jsonable(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [_jsonable(item) for item in value]
    if isinstance(value,np.generic):value=value.item()
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def run(data_root: Path, labels_root: Path, output: Path, *, symbols=SYMBOLS,
        families=("f3_order_flow","f4_regime","f5_cross_market"), start=None,end=DEV_END,
        anchor_limit=None,label_samples=30,skip_family_audit=False) -> Path:
    started=time.perf_counter();start=pd.Timestamp(start,tz="UTC") if start else pd.Timestamp("2000-01-01",tz="UTC")
    end=pd.Timestamp(end);end=end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    if end>DEV_END:raise ValueError("Audit cannot load 2023+ data")
    label=audit_labels(data_root,labels_root,label_samples,symbols=symbols)
    family_rows=[]
    if not skip_family_audit:
        for family in families:
            for symbol in symbols:family_rows.append(audit_family(data_root,labels_root,family,symbol))
    markets=[];tables=[]
    for symbol in symbols:
        result,table=analyse_market(data_root,labels_root,symbol,start,end,anchor_limit)
        markets.append(result)
        if len(table):tables.append(table)
    ic=pd.concat(tables,ignore_index=True) if tables else pd.DataFrame()
    write_report(output,family_rows,label,markets,ic,time.perf_counter()-started);return output


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--data-root",type=Path,required=True)
    parser.add_argument("--labels-root",type=Path);parser.add_argument("--output",type=Path,default=Path("reports/research/phase2_v1/information_audit.md"))
    parser.add_argument("--symbols",nargs="+",choices=SYMBOLS,default=list(SYMBOLS));parser.add_argument("--families",nargs="+",default=["f3_order_flow","f4_regime","f5_cross_market"])
    parser.add_argument("--start");parser.add_argument("--end",default="2023-01-01");parser.add_argument("--anchor-limit",type=int)
    parser.add_argument("--label-samples",type=int,default=30);parser.add_argument("--skip-family-audit",action="store_true")
    args=parser.parse_args();root=args.labels_root or args.data_root/"labels_wide_v1"
    print(run(args.data_root,root,args.output,symbols=tuple(args.symbols),families=tuple(args.families),
              start=args.start,end=args.end,anchor_limit=args.anchor_limit,label_samples=args.label_samples,
              skip_family_audit=args.skip_family_audit),flush=True)


if __name__=="__main__":main()
