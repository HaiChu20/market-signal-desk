"""Frozen swing v1 Stage 1, using only minute bars before 2023 UTC."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from msd.data.catalog import _load_parquet
from msd.data.dukascopy import load as load_dukascopy

NY = ZoneInfo("America/New_York")
CUT = pd.Timestamp("2023-01-01", tz="UTC")
SL = (1., 2., 3.)
TP = (1.5, 2., 3., 5.)
SETUPS = ("S1", "S2", "S3")
TRADED = {"USATECHIDXUSD": "MNQ", "XAUUSD": "MGC", "BTCUSDT": "MBT"}
EVIDENCE = {"USA500IDXUSD": "MNQ", "USA30IDXUSD": "MNQ", "DEUIDXEUR": "MNQ",
            "LIGHTCMDUSD": "MGC", "BRENTCMDUSD": "MGC", "XAGUSD": "MGC",
            "EURUSD": "MNQ", "GBPUSD": "MNQ", "USDJPY": "MNQ", "ETHUSDT": "MBT"}
# spread, commission, stop slip, roll period, annual carry
COST = {"MNQ": (.25, 1.25, .25, 91., .03),
        "MGC": (.1, .25, .1, 61., .04),
        "MBT": (10., 60., 5., 30., .08)}


@dataclass(frozen=True)
class Period:
    """Explicit data and scoring bounds; the default is the frozen DEV period."""

    data_start: pd.Timestamp | None = None
    score_start: pd.Timestamp | None = None
    end: pd.Timestamp | None = CUT


DEV_PERIOD = Period()


def ny_day_end(ts: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Each minute belongs to the first New York 17:00 close after its open."""
    local = ts.tz_convert(NY)
    dates = local.date
    after = (local.hour >= 17)
    closing_dates = pd.DatetimeIndex(pd.to_datetime(dates) + pd.to_timedelta(after.astype(int), unit="D"))
    return (closing_dates + pd.Timedelta(hours=17)).tz_localize(NY).tz_convert("UTC")


def globex(ts: pd.DatetimeIndex) -> np.ndarray:
    local = ts.tz_convert(NY)
    wd, hour = local.day_of_week, local.hour
    return np.asarray(((wd < 5) & (hour < 17)) | ((wd < 4) & (hour >= 18)) | ((wd == 6) & (hour >= 18)))


def load_minutes(root: Path, symbol: str, *, period: Period = DEV_PERIOD) -> pd.DataFrame:
    """Use the project's existing Dukascopy and catalog minute loaders."""
    source = "binance_spot" if symbol.endswith("USDT") else "dukascopy"
    directory = root / "bars" / source / symbol
    paths = sorted(directory.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet"))
    if period.data_start is not None:
        paths = [p for p in paths if p.stem >= period.data_start.strftime("%Y-%m")]
    if period.end is not None:
        paths = [p for p in paths if p.stem < period.end.strftime("%Y-%m")]
    if not paths:
        raise FileNotFoundError(directory)
    parts = []
    for path in paths:
        start = pd.Timestamp(path.stem + "-01", tz="UTC")
        end = start + pd.offsets.MonthBegin(1)
        # Both loaders include their end month/day.
        if source == "dukascopy":
            part = load_dukascopy(symbol, start, end-pd.Timedelta(days=1), root=root / "bars" / source)
        else:
            part = _load_parquet(symbol, start, end-pd.Timedelta(days=1), root / "bars" / source)
        keep = (part.ts >= start) & (part.ts < end)
        if period.data_start is not None:
            keep &= part.ts >= period.data_start
        if period.end is not None:
            keep &= part.ts < period.end
        part = part[keep]
        if len(part):
            cols = ["ts", *[f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc"]]
            part = part[cols]
            part[cols[1:]] = part[cols[1:]].astype("float32")
            parts.append(part)
    bars = pd.concat(parts, ignore_index=True).sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    if period.end is not None and bars.ts.max() >= period.end:
        message = "DEV cutoff violated" if period == DEV_PERIOD else "period end violated"
        raise AssertionError(message)
    return bars


def daily_bars(bars: pd.DataFrame, *, period: Period = DEV_PERIOD) -> pd.DataFrame:
    ts = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
    if len(ts) == 0 or (period.end is not None and ts.max() >= period.end):
        message = "no DEV-only minute bars" if period == DEV_PERIOD else "minute bars outside requested period"
        raise ValueError(message)
    ohlc = np.column_stack([(bars[f"bid_{c}"].to_numpy(float) + bars[f"ask_{c}"].to_numpy(float)) / 2 for c in "ohlc"])
    frame = pd.DataFrame(ohlc, columns=list("ohlc"))
    frame["end"] = ny_day_end(ts)
    daily = frame.groupby("end", sort=True).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    # A daily bar is complete only if its closing instant is covered by data.
    complete_through = period.end if period.end is not None else ts.max() + pd.Timedelta(minutes=1)
    daily = daily[daily.index < complete_through].reset_index()
    prev = daily.c.shift(1)
    tr = pd.concat([daily.h-daily.l, (daily.h-prev).abs(), (daily.l-prev).abs()], axis=1).max(axis=1)
    daily["atr"] = tr.rolling(20, min_periods=20).mean()
    return daily


def signals(daily: pd.DataFrame, first_year: int) -> pd.DataFrame:
    result = daily[["end", "c", "atr"]].copy()
    for setup, n in (("S1", 20), ("S2", 55)):
        high = daily.c.shift(1).rolling(n, min_periods=n).max()
        low = daily.c.shift(1).rolling(n, min_periods=n).min()
        result[setup] = np.where(daily.c > high, 1, np.where(daily.c < low, -1, 0))
    prior = daily.c.shift(126)
    result["S3"] = np.where(daily.c > prior, 1, np.where(daily.c < prior, -1, 0))
    result.loc[prior.isna(), "S3"] = 0
    result.loc[result.end.dt.tz_convert(NY).dt.year <= first_year, list(SETUPS)] = 0
    result.loc[result.atr.isna() | (result.atr <= 0), list(SETUPS)] = 0
    return result


def entry_index(ts: pd.DatetimeIndex, signal_end: pd.Timestamp, sensitivity: bool = False) -> int | None:
    if sensitivity:
        target = signal_end + pd.Timedelta(hours=1)
        # Weekend signals in continuously traded spot markets wait for CME.
        weekday = signal_end.tz_convert(NY).weekday()
        if weekday in (4, 5):
            target = (signal_end.tz_convert(NY) + pd.DateOffset(days=6-weekday, hours=1)).tz_convert("UTC")
    else:
        target = signal_end.normalize() + pd.Timedelta(hours=7)
        if target <= signal_end:
            target += pd.Timedelta(days=1)
        while target.tz_convert(NY).weekday() >= 5:
            target += pd.Timedelta(days=1)
    i = int(ts.searchsorted(target))
    return i if i < len(ts) and ts[i] == target else None


def exit_trade(ts: pd.DatetimeIndex, prices: np.ndarray, mask: np.ndarray, entry: int,
               side: int, stop: float, target: float, cap: int) -> tuple[int, float, str] | None:
    """Minute OHLC is mid; gap fills use the first eligible minute's open."""
    upper = min(cap, len(ts))
    valid = np.flatnonzero(mask[entry:upper]) + entry
    if len(valid):
        view = prices[valid]
        if side > 0:
            hit = (view[:, 0] <= stop) | (view[:, 0] >= target) | (view[:, 2] <= stop) | (view[:, 1] >= target)
        else:
            hit = (view[:, 0] >= stop) | (view[:, 0] <= target) | (view[:, 1] >= stop) | (view[:, 2] <= target)
        found = np.flatnonzero(hit)
    else:
        found = np.empty(0, dtype=int)
    if len(found):
        i = int(valid[found[0]])
        o, h, l, _ = prices[i]
        if side * (o-stop) <= 0:
            return i, float(o), "sl"
        if side * (o-target) >= 0:
            return i, float(o), "tp"
        if (l <= stop if side > 0 else h >= stop):
            return i, float(stop), "sl"
        if (h >= target if side > 0 else l <= target):
            return i, float(target), "tp"
    if cap < len(ts):
        return cap, float(prices[cap, 0]), "cap"
    return None


def cost_r(contract: str, symbol: str, entry: float, risk: float, side: int,
           days: float, reason: str, *, carry: bool = True, multiplier: float = 1.) -> float:
    spread, commission, slip, period, rate = COST[contract]
    if symbol not in TRADED:
        # Evidence values are fixed percentage of price, using closest micro
        # contract's nominal point costs at a representative underlying price.
        reference = {"MNQ": 12000., "MGC": 1800., "MBT": 20000.}[contract]
        scale = entry / reference
        spread, commission, slip = spread*scale, commission*scale, slip*scale
    cash = spread + commission + (slip if reason == "sl" else 0.)
    cash += days / period * (spread + commission)
    if carry:
        cash += side * rate * entry * days / 365.25
    return multiplier * cash / risk


def _summary(rows: list[dict], years: float | None = None) -> dict:
    if not rows:
        return {"trades": 0, "trades_per_year": 0., "mean_hold_days": None, "hit_rate": None,
                "net_R": None, "t_stat": None, "positive_year_share": None,
                "max_drawdown_R": None, "exits": {"sl": 0, "tp": 0, "cap": 0},
                "no_carry_R": None, "double_cost_R": None}
    r = np.array([x["net_R"] for x in rows])
    yrs = sorted({x["year"] for x in rows})
    year_means = [np.mean([x["net_R"] for x in rows if x["year"] == y]) for y in yrs]
    equity = np.r_[0., r.cumsum()]
    sd = r.std(ddof=1) if len(r) > 1 else 0.
    return {"trades": len(rows), "trades_per_year": len(rows)/(years or len(yrs)),
            "mean_hold_days": float(np.mean([x["hold_days"] for x in rows])),
            "hit_rate": float(np.mean([x["exit"] == "tp" for x in rows])),
            "net_R": float(r.mean()), "t_stat": float(r.mean()/sd*np.sqrt(len(r))) if sd > 0 else None,
            "positive_year_share": float(np.mean(np.array(year_means) > 0)),
            "max_drawdown_R": float(np.max(np.maximum.accumulate(equity)-equity)),
            "exits": {k: sum(x["exit"] == k for x in rows) for k in ("sl", "tp", "cap")},
            "no_carry_R": float(np.mean([x["no_carry_R"] for x in rows])),
            "double_cost_R": float(np.mean([x["double_cost_R"] for x in rows]))}


def evaluate_market(bars: pd.DataFrame, symbol: str, *, sensitivity: bool = False,
                    primary_only: bool = False,
                    period: Period = DEV_PERIOD,
                    setups: tuple[str, ...] = SETUPS) -> tuple[list[dict], dict]:
    ts = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
    first_year = int(ts[0].tz_convert(NY).year)
    daily = daily_bars(bars, period=period)
    signal = signals(daily, first_year)
    prices = np.column_stack([(bars[f"bid_{c}"].to_numpy(float) + bars[f"ask_{c}"].to_numpy(float))/2 for c in "ohlc"])
    mask = globex(ts)
    sessions = ny_day_end(ts)
    session_closes = pd.DatetimeIndex(sessions[mask]).unique().sort_values()
    # First eligible open after each 30th subsequent session close.
    session_first = np.searchsorted(sessions.asi8, session_closes.asi8, side="right")
    contract = (TRADED | EVIDENCE)[symbol]
    rows = []
    drops = {"unresolved_at_cutoff": 0, "missing_entry": 0}
    for setup in setups:
        for sl in ((2.,) if primary_only else SL):
            for tp in ((3.,) if primary_only else TP):
                next_free = -1
                for sig in signal.itertuples(index=False):
                    if getattr(sig, setup) == 0 or not np.isfinite(sig.atr):
                        continue
                    ei = entry_index(ts, sig.end, sensitivity)
                    if ei is None:
                        drops["missing_entry"] += 1
                        continue
                    if ei <= next_free or not mask[ei]:
                        continue
                    side = int(getattr(sig, setup))
                    entry = float(prices[ei, 0])
                    risk = float(sig.atr*sl)
                    stop = entry-side*risk
                    target = entry+side*risk*tp
                    session_number = int(session_closes.searchsorted(sessions[ei]))
                    cap_number = session_number+29
                    cap = int(session_first[cap_number]) if cap_number < len(session_first) else len(ts)
                    while cap < len(ts) and not mask[cap]:
                        cap += 1
                    out = exit_trade(ts, prices, mask, ei, side, stop, target, cap)
                    if out is None or (period.end is not None and ts[out[0]] >= period.end):
                        drops["unresolved_at_cutoff"] += 1
                        next_free = len(ts)
                        continue
                    xi, fill, reason = out
                    next_free = xi
                    days = (ts[xi]-ts[ei]).total_seconds()/86400
                    gross = side*(fill-entry)/risk
                    fee = cost_r(contract, symbol, entry, risk, side, days, reason)
                    no_carry_fee = cost_r(contract, symbol, entry, risk, side, days, reason, carry=False)
                    if period.score_start is not None and ts[ei] < period.score_start:
                        continue
                    rows.append({"market": symbol, "setup": setup, "sl_atr": sl, "tp_R": tp,
                                 "entry_ts": ts[ei].isoformat(), "exit_ts": ts[xi].isoformat(),
                                 "year": ts[ei].year, "hold_days": days, "exit": reason,
                                 "net_R": gross-fee, "no_carry_R": gross-no_carry_fee,
                                 "double_cost_R": gross-2*fee,
                                 "entry_index": ei, "side": side, "risk": risk, "cap_index": cap})
    return rows, drops


def baseline(bars: pd.DataFrame, rows: list[dict], symbol: str, seeds: int = 200) -> dict:
    """Fixed observed entry times; independent random direction at each trade."""
    if not rows:
        return {}
    ts = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
    prices = np.column_stack([(bars[f"bid_{c}"].to_numpy(float) + bars[f"ask_{c}"].to_numpy(float))/2 for c in "ohlc"])
    mask = globex(ts)
    contract = (TRADED | EVIDENCE)[symbol]
    output = {}
    for key in sorted({(r["setup"], r["sl_atr"], r["tp_R"]) for r in rows}):
        group = [r for r in rows if (r["setup"], r["sl_atr"], r["tp_R"]) == key]
        pairs = []
        for r in group:
            ei, side, risk, cap = r["entry_index"], r["side"], r["risk"], r["cap_index"]
            entry = float(prices[ei, 0])
            values = []
            for direction in (side, -side):
                out = exit_trade(ts, prices, mask, ei, direction, entry-direction*risk,
                                 entry+direction*risk*key[2], cap)
                if out is None:
                    values.append(np.nan)
                    continue
                xi, fill, reason = out
                days = (ts[xi]-ts[ei]).total_seconds()/86400
                values.append(direction*(fill-entry)/risk - cost_r(contract, symbol, entry, risk, direction, days, reason))
            pairs.append(values)
        matrix = np.asarray(pairs)
        # If a counterfactual cannot resolve before DEV, omit that matched entry.
        matrix = matrix[np.isfinite(matrix).all(axis=1)]
        if len(matrix):
            scores = []
            for seed in range(seeds):
                choices = np.random.default_rng(seed).integers(0, 2, size=len(matrix))
                scores.append(float(matrix[np.arange(len(matrix)), choices].mean()))
            output[key] = scores
    return output


def report(rows: list[dict], drops: dict, random_scores: dict,
           sensitivity_rows: list[dict] | None = None) -> dict:
    details = []
    for setup in SETUPS:
        for sl in SL:
            for tp in TP:
                for market in (*TRADED, *EVIDENCE):
                    part = [r for r in rows if (r["setup"],r["sl_atr"],r["tp_R"],r["market"]) == (setup,sl,tp,market)]
                    if not part:
                        continue
                    item={"setup":setup,"sl_atr":sl,"tp_R":tp,"market":market,
                          "primary":sl==2 and tp==3, **_summary(part)}
                    item["per_year"]={str(y):_summary([r for r in part if r["year"]==y])
                                      for y in sorted({r["year"] for r in part})}
                    details.append(item)
    pooled, verdicts = [], []
    for setup in SETUPS:
        choices=[]
        for sl in SL:
            for tp in TP:
                part=[r for r in rows if r["setup"]==setup and r["sl_atr"]==sl and r["tp_R"]==tp and r["market"] in TRADED]
                item={"setup":setup,"sl_atr":sl,"tp_R":tp,"primary":sl==2 and tp==3,**_summary(part)}
                if part:
                    years=sorted({r["year"] for r in part})
                    item["per_year"]={str(y):_summary([r for r in part if r["year"]==y]) for y in years}
                    score_arrays=[random_scores.get((market,setup,sl,tp)) for market in TRADED]
                    if all(s is not None for s in score_arrays):
                        counts=[sum(r["market"]==m for r in part) for m in TRADED]
                        weighted=np.average(np.asarray(score_arrays),axis=0,weights=counts)
                        item["random_95pct_R"]=float(np.percentile(weighted,95))
                pooled.append(item)
                choices.append(item)
        eligible=[x for x in choices if x["net_R"] is not None]
        if eligible:
            max(eligible,key=lambda x:x["net_R"])["hindsight_best"] = True
        primary=next(x for x in choices if x["primary"])
        market_results=[x for x in details if x["setup"]==setup and x["primary"] and x["market"] in TRADED]
        evidence=[x["net_R"] for x in details if x["setup"]==setup and x["primary"] and x["market"] in EVIDENCE and x["net_R"] is not None]
        evidence_avg=float(np.mean(evidence)) if evidence else None
        primary["evidence_market_average_R"] = evidence_avg
        passed=bool(primary["net_R"] is not None and primary["net_R"]>0 and
                    primary["t_stat"] is not None and primary["t_stat"]>=2 and
                    sum(x["net_R"]>0 for x in market_results)>=2 and
                    primary["positive_year_share"]>=.6 and
                    primary.get("random_95pct_R") is not None and primary["net_R"]>primary["random_95pct_R"] and
                    evidence_avg is not None and evidence_avg>0)
        verdicts.append({"setup":setup,"pass":passed})
    sensitivity_rows = sensitivity_rows or []
    sensitivity = {setup:_summary([r for r in sensitivity_rows if r["setup"] == setup])
                   for setup in SETUPS}
    return {"verdict":"PASS" if any(v["pass"] for v in verdicts) else "FAIL",
            "setup_verdicts":verdicts,"pooled":pooled,"by_market":details,"drops":drops,
            "reopen_sensitivity_primary":sensitivity,
            "evidence_mapping":EVIDENCE,"cost_reference_prices":{"MNQ":12000,"MGC":1800,"MBT":20000},
            "dev_cutoff":"2023-01-01T00:00:00Z","baseline_seeds":200}


def markdown(result: dict) -> str:
    lines=["# Swing v1 Stage 1 — DEV only", "", f"**{result['verdict']}** against section 7.", "",
           "Primary option: **SL 2 ATR, TP 3R**. Hindsight best is descriptive only.", "",
           "Evidence cost mapping: USA500, USA30, DEUIDX, EURUSD, GBPUSD, USDJPY → MNQ; "
           "LIGHTCMD, BRENTCMD, XAGUSD → MGC; ETHUSDT → MBT. Point costs are scaled by "
           "entry price / reference price (MNQ 12000, MGC 1800, MBT 20000).", "",
           "| Setup | Option | Trades | Net R | t | Positive years | Evidence avg R | Random 95% R |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for item in result["pooled"]:
        tag="primary" if item["primary"] else "hindsight" if item.get("hindsight_best") else ""
        def fmt(x): return "" if x is None else f"{x:.3f}"
        lines.append(f"| {item['setup']} | {item['sl_atr']} ATR / {item['tp_R']}R {tag} | {item['trades']} | {fmt(item['net_R'])} | {fmt(item['t_stat'])} | {fmt(item['positive_year_share'])} | {fmt(item.get('evidence_market_average_R'))} | {fmt(item.get('random_95pct_R'))} |")
    lines += ["", "## Primary option cost sensitivity (traded markets pooled)", "",
              "| Setup | Base net R | No carry R | 2× cost R |",
              "|---|---:|---:|---:|"]
    for item in result["pooled"]:
        if item["primary"]:
            lines.append(f"| {item['setup']} | {fmt(item['net_R'])} | {fmt(item['no_carry_R'])} | {fmt(item['double_cost_R'])} |")
    lines += ["", "## 18:00 New York reopen sensitivity (primary option, traded markets pooled)", "",
              "| Setup | Trades | Net R | t |", "|---|---:|---:|---:|"]
    for setup, item in result["reopen_sensitivity_primary"].items():
        lines.append(f"| {setup} | {item['trades']} | {item['net_R']} | {item['t_stat']} |")
    lines += ["", "## Per-market option metrics", "",
              "| Setup | SL ATR | TP R | Market | Trades | Trades/year | Hold days | Hit rate | Net R | t | Positive years | Max DD R | SL | TP | Cap | No carry R | 2× cost R |",
              "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    def cell(value):
        if value is None:
            return ""
        return f"{value:.3f}" if isinstance(value, float) else str(value)
    for item in result["by_market"]:
        values = [item["setup"], item["sl_atr"], item["tp_R"], item["market"],
                  item["trades"], item["trades_per_year"], item["mean_hold_days"],
                  item["hit_rate"], item["net_R"], item["t_stat"],
                  item["positive_year_share"], item["max_drawdown_R"],
                  item["exits"]["sl"], item["exits"]["tp"], item["exits"]["cap"],
                  item["no_carry_R"], item["double_cost_R"]]
        lines.append("| " + " | ".join(map(cell, values)) + " |")
    lines += ["", "## Per-year primary option (traded markets pooled)", "",
              "| Setup | Year | Trades | Net R | t | Positive year |",
              "|---|---:|---:|---:|---:|---:|"]
    for item in result["pooled"]:
        if not item["primary"]:
            continue
        for year, year_item in item.get("per_year", {}).items():
            lines.append(f"| {item['setup']} | {year} | {year_item['trades']} | {cell(year_item['net_R'])} | {cell(year_item['t_stat'])} | {year_item['net_R'] > 0} |")
    lines += ["", "Full per-year rows for every market and option are in `stage1.json`.",
              "Signals require an exact 07:00 UTC minute; missing minutes are skipped. "
              "The first available year per market is warm-up only (BTC starts in 2017, so trades begin in 2018).", "",
              "", f"Unresolved trades dropped at DEV cutoff: {result['drops']['unresolved_at_cutoff']}.", ""]
    return "\n".join(lines)


def run(data_root: Path, output: Path, ledger: Path) -> dict:
    all_rows=[]; sensitivity_rows=[]; drops={"unresolved_at_cutoff":0,"missing_entry":0}; random_scores={}
    for market in (*TRADED, *EVIDENCE):
        bars=load_minutes(data_root,market)
        rows,counts=evaluate_market(bars,market)
        all_rows.extend(rows)
        for key,value in counts.items(): drops[key]+=value
        if market in TRADED:
            sensitivity_rows.extend(evaluate_market(bars,market,sensitivity=True,primary_only=True)[0])
            scores=baseline(bars,rows,market)
            random_scores.update({(market,*key):value for key,value in scores.items()})
        print(f"{market}: {len(rows)} outcomes",flush=True)
        del bars
    result=report(all_rows,drops,random_scores,sensitivity_rows)
    output.mkdir(parents=True,exist_ok=True)
    (output/"stage1.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    (output/"stage1.md").write_text(markdown(result))
    with ledger.open("a",newline="") as file:
        writer=csv.writer(file)
        for setup in SETUPS:
            primary=next(x for x in result["pooled"] if x["setup"]==setup and x["primary"])
            writer.writerow([f"swing-v1-stage1-{setup.lower()}",pd.Timestamp.now(tz="UTC").date().isoformat(),
                             hashlib.sha256(f"swing-v1:{setup}:frozen".encode()).hexdigest(),"swing_v1",
                             f"{setup};SL=2ATR;TP=3R;12 options reported", "DEV<2023-01-01", "development",
                             json.dumps({"net_R":primary["net_R"],"t":primary["t_stat"],"trades":primary["trades"]}),
                             result["verdict"]])
    return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root",type=Path,default=Path("data"))
    parser.add_argument("--output",type=Path,default=Path("reports/research/swing_v1"))
    parser.add_argument("--ledger",type=Path,default=Path("reports/trials.csv"))
    args=parser.parse_args()
    result=run(args.data_root,args.output,args.ledger)
    print(result["verdict"])


if __name__=="__main__":
    main()
