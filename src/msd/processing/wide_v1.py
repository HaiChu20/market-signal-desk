"""Versioned wide-geometry DEV labels for grids and frozen replay events."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .crypto_perp import apply_perp_costs, executable_perp_bars
from .labels import deadline_after_trading_days, label_grid

DEV_END = pd.Timestamp("2023-01-01", tz="UTC")
CRYPTO = {"BTCUSDT", "ETHUSDT"}
SOURCE = {"BTCUSDT": "binance_um", "ETHUSDT": "binance_um",
          "USATECHIDXUSD": "dukascopy", "USA500IDXUSD": "dukascopy", "XAUUSD": "dukascopy"}


def load_config(path: Path) -> dict:
    config=json.loads(path.read_text())
    if config.get("period")!="dev" or pd.Timestamp(config["end_exclusive"])>pd.Timestamp("2023-01-01"):
        raise ValueError("wide_v1 is DEV only")
    if len(config["sl_atr"])*len(config["tp_r"])*2 != 50:
        raise ValueError("wide_v1 must contain 50 both-side options")
    return config


def _read_months(root: Path, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    months=pd.period_range(start.tz_localize(None).to_period("M"),
                           (end-pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M"),freq="M")
    paths=[root/symbol/f"{month}.parquet" for month in months if (root/symbol/f"{month}.parquet").exists()]
    if not paths:raise FileNotFoundError(f"{root}/{symbol} {start} {end}")
    frame=pd.concat([pd.read_parquet(path) for path in paths],ignore_index=True)
    frame["ts"]=pd.to_datetime(frame.ts,utc=True)
    return frame[(frame.ts>=start)&(frame.ts<end)].sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def _bars(data_root: Path, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    frame=_read_months(data_root/"bars"/SOURCE[symbol],symbol,start,end)
    return executable_perp_bars(frame,symbol) if symbol in CRYPTO else frame


def _funding(data_root: Path, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if symbol not in CRYPTO:return pd.DataFrame(columns=["ts","funding_rate"])
    months=pd.period_range(start.tz_localize(None).to_period("M"),
                           (end-pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M"),freq="M")
    paths=[data_root/"aux"/"funding"/symbol/f"{month}.parquet" for month in months]
    paths=[path for path in paths if path.exists()]
    if not paths:raise FileNotFoundError(f"funding/{symbol}")
    return pd.concat([pd.read_parquet(path,columns=["ts","funding_rate"]) for path in paths],ignore_index=True)


def _manifest(root: Path, symbol: str, kind: str, config: dict) -> Path:
    files=[]
    for path in sorted((root/symbol).glob("*.parquet")):
        files.append({"path":path.relative_to(root.parent).as_posix(),"size":path.stat().st_size,
                      "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    payload={"version":"wide_v1","kind":kind,"symbol":symbol,"config":config,"files":files}
    prefix="" if root.name in {"events_wide_v1","labels_wide_v1"} else f"{root.name}_"
    path=root.parent/f"manifest_{prefix}{kind}_{symbol}.json";path.write_text(json.dumps(payload,indent=2)+"\n")
    return path


def build_grid_labels(symbol: str, data_root: Path, output_root: Path, config: dict) -> None:
    start=pd.Timestamp(config["starts"][symbol],tz="UTC"); end=DEV_END
    target=output_root/symbol;target.mkdir(parents=True,exist_ok=True)
    for month in pd.period_range(start.tz_localize(None).to_period("M"),"2022-12",freq="M"):
        left=pd.Timestamp(month.start_time,tz="UTC");right=min(pd.Timestamp(month.end_time,tz="UTC")+pd.Timedelta(nanoseconds=1),end)
        read_right=min(right+pd.Timedelta(days=8),end)
        bars=_bars(data_root,symbol,left,read_right)
        features=pd.read_parquet(data_root/"features"/symbol/f"{month}.parquet",
                                 columns=["ts","1h_atr14"])
        atr_map=pd.Series(features["1h_atr14"].to_numpy(float),index=pd.to_datetime(features.ts,utc=True))
        atr=pd.Series(pd.to_datetime(bars.ts,utc=True).map(atr_map).to_numpy(),index=bars.index)
        labels=label_grid(bars,atr,max_trading_days=int(config["max_hold_trading_days"]),
            instrument_class="crypto" if symbol in CRYPTO else "index",signal_start=left,signal_end=right,
            financing_per_night=0. if symbol in CRYPTO else None,
            sl_grid=tuple(config["sl_atr"]),tp_grid=tuple(config["tp_r"]),tp_is_r_multiple=True)
        labels["ts"]=bars.ts.iloc[labels.signal_index.to_numpy()].to_numpy()
        if symbol in CRYPTO:
            labels=apply_perp_costs(labels,bars,_funding(data_root,symbol,left,read_right))
        else:
            labels["cost_R"]=labels.gross_R-labels.net_R
            labels["venue"]="dukascopy_cfd"
        labels=labels[pd.to_datetime(labels.exit_ts,utc=True)<DEV_END].reset_index(drop=True)
        labels["label_end_ts"]=labels.exit_ts
        labels.to_parquet(target/f"{month}.parquet",index=False,compression="zstd")
    _manifest(output_root,symbol,"grid",config)


def _event_jobs(events: pd.DataFrame, bars: pd.DataFrame, atr_map: pd.Series, config: dict, symbol: str):
    from msd._msd_kernels import first_hit_batch
    bars=bars.sort_values("ts").reset_index(drop=True)
    positions=pd.Series(np.arange(len(bars)),index=bars.ts)
    matrix=bars[["bid_o","bid_h","bid_l","bid_c","ask_o","ask_h","ask_l","ask_c"]].to_numpy(dtype="<f8")
    # Pandas may preserve microsecond resolution. Force nanoseconds before
    # converting to epoch seconds so the Rust deadline comparison is sound.
    stamp=(pd.to_datetime(bars.ts,utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
           //1_000_000_000).astype("<i8")
    jobs=[];meta=[]
    for row in events.itertuples(index=False):
        i=positions.get(row.ts);side=int(row.side)
        atr=float(atr_map.get(row.ts,np.nan))
        if i is None or side not in (-1,1) or not np.isfinite(atr) or atr<=0 or int(i)+2>=len(bars):continue
        limit=float(row.limit_price) if getattr(row,"entry_type","market")=="limit" and pd.notna(row.limit_price) else None
        mid=(float(bars.bid_c.iloc[int(i)])+float(bars.ask_c.iloc[int(i)]))/2
        entry=limit if limit is not None else mid
        deadline=deadline_after_trading_days(bars.ts.iloc[int(i)+2],int(config["max_hold_trading_days"]),"crypto" if symbol in CRYPTO else "index")
        expiry=getattr(row,"expiry_at",pd.NaT)
        expiry_seconds=float(pd.Timestamp(expiry).timestamp()) if limit is not None and pd.notna(expiry) else np.nan
        for sl_atr in config["sl_atr"]:
            for tp_r in config["tp_r"]:
                sl=entry-side*float(sl_atr)*atr;tp=entry+side*float(sl_atr)*float(tp_r)*atr
                jobs.extend([int(i),side,entry,sl,tp,int(deadline.timestamp()),2,
                             0. if symbol in CRYPTO else (.0002 if symbol!="XAUUSD" else .00015),
                             limit if limit is not None else np.nan,expiry_seconds,1 if symbol in CRYPTO else 0])
                meta.append((row,sl_atr,tp_r,sl,tp,deadline))
    if not jobs:return pd.DataFrame()
    values=np.asarray(first_hit_batch(matrix.tobytes(),stamp.tobytes(),jobs,11),dtype=float).reshape(-1,9)
    records=[];outcome={1:"tp",-1:"sl",0:"time",-2:"no_fill"}
    for (event,sl_atr,tp_r,sl,tp,deadline),value in zip(meta,values):
        code,exit_i,fill,exit_price,net,gross,nights,entry_i,risk=value;exit_i=int(exit_i);entry_i=int(entry_i)
        base=event._asdict();
        records.append({**base,"sl_atr":float(sl_atr),"tp_r":float(tp_r),"tp_atr":float(sl_atr)*float(tp_r),
            "sl":sl,"tp":tp,"deadline_ts":deadline,"entry_ts":bars.ts.iloc[entry_i] if entry_i>=0 else pd.NaT,
            "fill_price":fill,"entry_price":fill,"planned_risk":risk,"outcome":outcome[int(code)],
            "exit_ts":bars.ts.iloc[exit_i] if exit_i>=0 else pd.NaT,"exit_price":exit_price,
            "net_R":net,"R":net,"gross_R":gross,"financing_nights":int(nights)})
    return pd.DataFrame(records)


def build_event_labels(symbol: str, data_root: Path, output_root: Path, config: dict) -> None:
    target=output_root/symbol;target.mkdir(parents=True,exist_ok=True)
    start_year=pd.Timestamp(config["starts"][symbol]).year
    identity=["method","variant","ts","side","entry_type","limit_price","expiry_at"]
    for path in sorted((data_root/"events"/symbol).glob("*.parquet")):
        if not start_year<=int(path.stem[:4])<=2022:continue
        events=pd.read_parquet(path)
        events["ts"]=pd.to_datetime(events.ts,utc=True)
        present=[c for c in identity if c in events]
        events=events.sort_values("ts").drop_duplicates(present,keep="first")
        left=pd.Timestamp(path.stem+"-01",tz="UTC");right=left+pd.offsets.MonthBegin(1);read_right=min(right+pd.Timedelta(days=8),DEV_END)
        bars=_bars(data_root,symbol,left,read_right)
        features=pd.read_parquet(data_root/"features"/symbol/path.name,columns=["ts","1h_atr14"])
        atr_map=pd.Series(features["1h_atr14"].to_numpy(float),index=pd.to_datetime(features.ts,utc=True))
        result=_event_jobs(events,bars,atr_map,config,symbol)
        if symbol in CRYPTO and len(result):
            result=apply_perp_costs(result,bars,_funding(data_root,symbol,left,read_right));result["R"]=result.net_R
        elif len(result):
            result["cost_R"]=result.gross_R-result.net_R;result["venue"]="dukascopy_cfd"
        if len(result):
            result=result[pd.to_datetime(result.exit_ts,utc=True)<DEV_END].copy()
            result["known_at"]=pd.to_datetime(result.known_at,utc=True);result["label_end_ts"]=result.exit_ts
            variant=result.get("variant",pd.Series("",index=result.index)).fillna("").astype(str)
            entry_type=result.get("entry_type",pd.Series("market",index=result.index)).fillna("market").astype(str)
            limit=result.get("limit_price",pd.Series(np.nan,index=result.index)).astype(object).fillna("").astype(str)
            result["event_key"]=(symbol+"|"+result.method.astype(str)+"|"+variant+"|"+
                result.ts.astype(str)+"|"+result.side.astype(str)+"|"+entry_type+"|"+limit)
        result.to_parquet(target/path.name,index=False,compression="zstd")
    _manifest(output_root,symbol,"events",config)


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--symbol",choices=tuple(SOURCE),required=True)
    parser.add_argument("--kind",choices=("grid","events"),required=True)
    parser.add_argument("--data-root",type=Path,default=Path("data"));parser.add_argument("--config",type=Path,default=Path("hpc/roihu/sequence/configs/wide_v1.json"))
    parser.add_argument("--output-root",type=Path)
    args=parser.parse_args();config=load_config(args.config)
    root=args.output_root or args.data_root/("labels_wide_v1" if args.kind=="grid" else "events_wide_v1")
    (build_grid_labels if args.kind=="grid" else build_event_labels)(args.symbol,args.data_root,root,config)


if __name__=="__main__":main()
