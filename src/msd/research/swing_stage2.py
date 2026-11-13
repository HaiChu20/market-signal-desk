"""Frozen swing v1 Stage 2: S3 net-R option selection, DEV-only walk-forward."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from msd.research import swing_stage1 as s1

FEATURES = ("return_20_atr", "return_60_atr", "return_126_atr", "atr_price",
            "atr_year_percentile", "high_20_atr", "low_20_atr", "high_55_atr",
            "low_55_atr", "side", "day_of_week", "sl_atr", "tp_R")
OPTIONS = tuple((sl, tp) for sl in s1.SL for tp in s1.TP)
YEARS = tuple(range(2010, 2023))
THRESHOLD = .05
MODEL_PARAMS = {"objective": "regression", "num_leaves": 15,
                "learning_rate": .03, "min_data_in_leaf": 100,
                "feature_fraction": .8, "seed": 7, "verbosity": -1,
                "num_threads": 4}


def daily_features(daily: pd.DataFrame) -> pd.DataFrame:
    """Every value in row D uses bars ending no later than D's NY close."""
    close, atr = daily.c.astype(float), daily.atr.astype(float)
    frame = pd.DataFrame(index=daily.index)
    for n in (20, 60, 126):
        frame[f"return_{n}_atr"] = (close-close.shift(n))/atr
    frame["atr_price"] = atr/close
    times = pd.DatetimeIndex(daily.end)
    calendar = times.asi8
    values = atr.to_numpy(float)
    percentile = np.full(len(daily), np.nan)
    left = np.searchsorted(calendar, calendar-pd.Timedelta(days=365).value, side="left")
    for i in range(len(daily)):
        sample = values[left[i]:i+1]
        sample = sample[np.isfinite(sample)]
        if len(sample) >= 20 and np.isfinite(values[i]):
            percentile[i] = np.mean(sample <= values[i])
    frame["atr_year_percentile"] = percentile
    for n in (20, 55):
        high = close.shift(1).rolling(n, min_periods=n).max()
        low = close.shift(1).rolling(n, min_periods=n).min()
        frame[f"high_{n}_atr"] = (close-high)/atr
        frame[f"low_{n}_atr"] = (close-low)/atr
    frame["day_of_week"] = times.tz_convert(s1.NY).day_of_week
    return frame


def training_mask(exit_times: np.ndarray, year: int) -> np.ndarray:
    """Purge every label not fully resolved before the predicted year."""
    return exit_times < np.datetime64(f"{year}-01-01T00:00:00", "ns")


def choose_option(predictions: np.ndarray, threshold: float = THRESHOLD) -> int | None:
    best = int(np.argmax(predictions))
    return best if np.isfinite(predictions[best]) and predictions[best] >= threshold else None


def _bar_arrays(bars: pd.DataFrame) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray,
                                                pd.DatetimeIndex, pd.DatetimeIndex, np.ndarray]:
    ts = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
    prices = np.column_stack([(bars[f"bid_{c}"].to_numpy(float)+bars[f"ask_{c}"].to_numpy(float))/2
                              for c in "ohlc"])
    mask = s1.globex(ts)
    sessions = s1.ny_day_end(ts)
    closes = pd.DatetimeIndex(sessions[mask]).unique().sort_values()
    first = np.searchsorted(sessions.asi8, closes.asi8, side="right")
    return ts, prices, mask, sessions, closes, first


def market_opportunities(bars: pd.DataFrame, market: str) -> tuple[list[dict], dict]:
    """Label all S3 signal-day entry opportunities, even while another trade is open."""
    ts, prices, mask, sessions, closes, first = _bar_arrays(bars)
    daily = s1.daily_bars(bars)
    signal = s1.signals(daily, int(ts[0].tz_convert(s1.NY).year))
    features = daily_features(daily)
    contract = (s1.TRADED | s1.EVIDENCE)[market]
    opportunities = []
    drops = Counter()
    for i, row in enumerate(signal.itertuples(index=False)):
        if row.S3 == 0 or not np.isfinite(row.atr):
            continue
        ei = s1.entry_index(ts, row.end)
        if ei is None or not mask[ei]:
            drops["missing_entry"] += 1
            continue
        daily_values = features.iloc[i].to_numpy(float)
        base = np.r_[daily_values[:-1], int(row.S3), daily_values[-1]]
        if not np.isfinite(base).all():
            drops["missing_features"] += 1
            continue
        side = int(row.S3)
        entry = float(prices[ei, 0])
        session_number = int(closes.searchsorted(sessions[ei]))
        cap_number = session_number+29
        cap = int(first[cap_number]) if cap_number < len(first) else len(ts)
        while cap < len(ts) and not mask[cap]:
            cap += 1
        labels = []
        for sl, tp in OPTIONS:
            risk = float(row.atr*sl)
            out = s1.exit_trade(ts, prices, mask, ei, side, entry-side*risk,
                                entry+side*risk*tp, cap)
            if out is None or ts[out[0]] >= s1.CUT:
                labels.append(None)
                drops["unresolved_option"] += 1
                continue
            xi, fill, reason = out
            days = (ts[xi]-ts[ei]).total_seconds()/86400
            gross = side*(fill-entry)/risk
            fee = s1.cost_r(contract, market, entry, risk, side, days, reason)
            labels.append({"market":market, "setup":"S3", "sl_atr":sl,
                           "tp_R":tp, "entry_ts":ts[ei].isoformat(),
                           "exit_ts":ts[xi].isoformat(), "year":ts[ei].year,
                           "hold_days":days, "exit":reason, "net_R":gross-fee,
                           "no_carry_R":gross-s1.cost_r(contract,market,entry,risk,side,days,reason,carry=False),
                           "double_cost_R":gross-2*fee, "entry_index":ei, "exit_index":xi,
                           "side":side, "risk":risk, "cap_index":cap})
        opportunities.append({"market":market,"entry_ts":ts[ei].isoformat(),
                              "entry_index":ei,"year":ts[ei].year,
                              "features":base,"side":side,"labels":labels})
    return opportunities, dict(drops)


def make_training_rows(opportunities: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs, ys, exits = [], [], []
    for opp in opportunities:
        for option, label in zip(OPTIONS, opp["labels"]):
            if label is None:
                continue
            xs.append([*opp["features"], *option])
            ys.append(label["net_R"])
            exits.append(pd.Timestamp(label["exit_ts"]).to_datetime64())
    return (np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32),
            np.asarray(exits, dtype="datetime64[ns]"))


def walk_forward(traded: dict[str,list[dict]], evidence: dict[str,list[dict]]) -> tuple[dict, list[dict]]:
    train_opps = [opp for market in s1.TRADED for opp in traded[market]]
    x, y, exits = make_training_rows(train_opps)
    models = []
    for year in YEARS:
        mask = training_mask(exits, year)
        if not mask.any():
            continue
        model = lgb.train(MODEL_PARAMS, lgb.Dataset(x[mask], label=y[mask], feature_name=list(FEATURES)),
                          num_boost_round=300)
        for market, opportunities in (traded | evidence).items():
            current = [opp for opp in opportunities if opp["year"] == year]
            if not current:
                continue
            matrix = np.asarray([[*opp["features"], *option] for opp in current for option in OPTIONS],
                                dtype=np.float32)
            prediction = model.predict(matrix).reshape(len(current), len(OPTIONS))
            for opp, scores in zip(current, prediction):
                opp["predictions"] = scores
        models.append({"year":year,"training_rows":int(mask.sum()),
                       "latest_training_exit":str(exits[mask].max()),
                       "training_markets":list(s1.TRADED)})
        print(f"model {year}: {int(mask.sum())} training rows",flush=True)
    return traded | evidence, models


def sequential_trades(opportunities: list[dict], threshold: float = THRESHOLD) -> tuple[list[dict], dict]:
    """Apply predicted choices in entry order; selected exit blocks later entries."""
    selected = []
    last_exit = -1
    counts = Counter()
    for opp in sorted(opportunities, key=lambda row: row["entry_index"]):
        if "predictions" not in opp:
            continue
        if opp["entry_index"] <= last_exit:
            counts["blocked_open"] += 1
            continue
        counts["flat_opportunities"] += 1
        pick = choose_option(opp["predictions"], threshold)
        if pick is None:
            counts["skipped_prediction"] += 1
            continue
        label = opp["labels"][pick]
        if label is None:
            counts["unresolved_chosen"] += 1
            last_exit = 10**20
            continue
        selected.append(label)
        last_exit = label["exit_index"]
    counts["skip_rate"] = (counts["skipped_prediction"]/counts["flat_opportunities"]
                            if counts["flat_opportunities"] else None)
    return selected, dict(counts)


def _random_percentile(selected: dict[str,list[dict]], data_root: Path) -> tuple[float | None, int]:
    scores = []
    weights = []
    for market in s1.TRADED:
        rows = selected[market]
        if not rows:
            continue
        bars = s1.load_minutes(data_root, market)
        groups = s1.baseline(bars, rows, market)
        for key, values in groups.items():
            count = sum((r["setup"],r["sl_atr"],r["tp_R"]) == key for r in rows)
            scores.append(values)
            weights.append(count)
        del bars
    if not scores:
        return None, 0
    return float(np.percentile(np.average(np.asarray(scores), axis=0, weights=weights), 95)), sum(weights)


def summarize(selected: dict[str,list[dict]], primary: list[dict],
              counts: dict[str,dict], models: list[dict], random_95: float | None,
              random_count: int, drops: dict) -> dict:
    traded_rows = [r for market in s1.TRADED for r in selected[market]]
    evidence_rows = [r for market in s1.EVIDENCE for r in selected[market]]
    pooled = s1._summary(traded_rows)
    primary_summary = s1._summary(primary)
    market_rows = {market:s1._summary(selected[market]) for market in selected}
    market_yearly = {market:{str(year):s1._summary([r for r in selected[market] if r["year"] == year])
                             for year in YEARS}
                     for market in selected}
    yearly = {str(year):s1._summary([r for r in traded_rows if r["year"] == year]) for year in YEARS}
    primary_yearly = {str(year):s1._summary([r for r in primary if r["year"] == year]) for year in YEARS}
    year_positive = sum(yearly[str(year)]["net_R"] is not None and yearly[str(year)]["net_R"] > 0 for year in YEARS)
    pooled["positive_year_share"] = year_positive/len(YEARS)
    evidence_average = float(np.mean([market_rows[m]["net_R"] for m in s1.EVIDENCE
                                      if market_rows[m]["net_R"] is not None])) if evidence_rows else None
    option_distribution = {f"{sl:g}ATR_{tp:g}R":sum(r["sl_atr"]==sl and r["tp_R"]==tp for r in traded_rows)
                           for sl,tp in OPTIONS}
    flat = sum(counts[m].get("flat_opportunities",0) for m in s1.TRADED)
    skipped = sum(counts[m].get("skipped_prediction",0) for m in s1.TRADED)
    total_r = float(sum(r["net_R"] for r in traded_rows))
    primary_total_r = float(sum(r["net_R"] for r in primary))
    criteria = {
        "positive_t": pooled["net_R"] is not None and pooled["net_R"] > 0 and
                      pooled["t_stat"] is not None and pooled["t_stat"] >= 2,
        "positive_markets": sum(market_rows[m]["net_R"] is not None and market_rows[m]["net_R"] > 0
                                for m in s1.TRADED) >= 2,
        "positive_year_share": pooled["positive_year_share"] >= .6,
        "above_random_95": random_95 is not None and pooled["net_R"] is not None and pooled["net_R"] > random_95,
        "positive_evidence_average": evidence_average is not None and evidence_average > 0,
        "beats_primary_total_R": total_r > primary_total_r,
        "beats_primary_net_R_per_trade": pooled["net_R"] is not None and
                                         primary_summary["net_R"] is not None and pooled["net_R"] > primary_summary["net_R"],
    }
    return {"verdict":"PASS" if all(criteria.values()) else "FAIL",
            "criteria":criteria,"predicted_years":list(YEARS),
            "pooled_traded":pooled,"per_market":market_rows,"per_market_year":market_yearly,
            "per_year":yearly,
            "stage1_primary_same_years":{"pooled":primary_summary,"per_year":primary_yearly,
                                         "total_R":primary_total_r},
            "total_R":total_r,"chosen_options":option_distribution,
            "skip_rate":skipped/flat if flat else None,"flat_opportunities":flat,
            "skipped_prediction":skipped,"market_selection_counts":counts,
            "random_direction_95pct_R":random_95,"random_direction_matched_entries":random_count,
            "random_direction_seeds":200,"evidence_market_average_R":evidence_average,
            "models":models,"training_features":list(FEATURES),"model_params":MODEL_PARAMS,
            "num_boost_round":300,"threshold_R":THRESHOLD,
            "dropped":drops,"evidence_mapping":s1.EVIDENCE}


def markdown(result: dict) -> str:
    pooled = result["pooled_traded"]
    primary = result["stage1_primary_same_years"]
    def fmt(value):
        return "" if value is None else f"{value:.4f}" if isinstance(value,float) else str(value)
    lines = ["# Swing v1 Stage 2 — S3 option selection, DEV only", "",
             f"**{result['verdict']}** against frozen section 10.", "",
             "One LightGBM net-R regressor, trained on all S3 entry opportunities × 12 options "
             "with exits before the predicted year. Trades are selected sequentially per market; "
             "the best predicted option is taken at ≥0.05R.", "",
             "Return features are price changes divided by current ATR. High/low distances use "
             "the previous 20 or 55 daily closes. ATR percentile uses the trailing 365 calendar "
             "days including the signal day's completed bar. The first available market year is "
             "warm-up only.", "",
             "| Measure | Stage 2 | Stage 1 S3 primary, same years |",
             "|---|---:|---:|",
             f"| Trades | {pooled['trades']} | {primary['pooled']['trades']} |",
             f"| Net R/trade | {fmt(pooled['net_R'])} | {fmt(primary['pooled']['net_R'])} |",
             f"| Total R | {fmt(result['total_R'])} | {fmt(primary['total_R'])} |",
             f"| t-stat | {fmt(pooled['t_stat'])} | {fmt(primary['pooled']['t_stat'])} |",
             f"| Positive-year share | {fmt(pooled['positive_year_share'])} | {fmt(primary['pooled']['positive_year_share'])} |",
             f"| No-carry R/trade | {fmt(pooled['no_carry_R'])} | {fmt(primary['pooled']['no_carry_R'])} |",
             f"| 2× cost R/trade | {fmt(pooled['double_cost_R'])} | {fmt(primary['pooled']['double_cost_R'])} |",
             "",f"Random-direction 95th percentile: {fmt(result['random_direction_95pct_R'])} R/trade "
             f"({result['random_direction_seeds']} seeds). Evidence-market average: "
             f"{fmt(result['evidence_market_average_R'])} R/trade. Prediction skip rate: "
             f"{fmt(result['skip_rate'])}.", "",
             "## Pass criteria", "",
             "| Criterion | Met |", "|---|---|", *[f"| {k} | {v} |" for k,v in result["criteria"].items()],
             "", "## Per market", "",
             "| Market | Trades | Trades/year | Hold days | Hit rate | Net R | t | Positive years | Max DD R | SL | TP | Cap |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for market,item in result["per_market"].items():
        values=[market,item["trades"],item["trades_per_year"],item["mean_hold_days"],
                item["hit_rate"],item["net_R"],item["t_stat"],item["positive_year_share"],
                item["max_drawdown_R"],item["exits"]["sl"],item["exits"]["tp"],item["exits"]["cap"]]
        lines.append("| " + " | ".join(map(fmt,values)) + " |")
    lines += ["", "## Per predicted year, traded markets pooled", "",
              "| Year | Stage 2 trades | Stage 2 net R | Stage 1 primary trades | Stage 1 primary net R |",
              "|---|---:|---:|---:|---:|"]
    for year,item in result["per_year"].items():
        baseline=primary["per_year"][year]
        lines.append(f"| {year} | {item['trades']} | {fmt(item['net_R'])} | {baseline['trades']} | {fmt(baseline['net_R'])} |")
    lines += ["", "## Chosen option distribution", "",
              "| Option | Trades |", "|---|---:|",
              *[f"| {option} | {count} |" for option,count in result["chosen_options"].items()],
              "", "## Model audit", "",
              "| Predicted year | Training rows | Latest training exit |",
              "|---|---:|---|",
              *[f"| {m['year']} | {m['training_rows']} | {m['latest_training_exit']} |" for m in result["models"]],
              "", "The JSON includes all per-market and per-year metrics, skip counts, model settings, "
              "and the fixed evidence cost mapping. The 07:00 entry requires an exact minute. "
              "An unresolved chosen option at the DEV cutoff is dropped.", ""]
    return "\n".join(lines)


def run(data_root: Path, output: Path, ledger: Path) -> dict:
    traded, evidence, primary = {}, {}, []
    drops = {}
    for market in (*s1.TRADED, *s1.EVIDENCE):
        bars = s1.load_minutes(data_root, market)
        opportunities, counts = market_opportunities(bars, market)
        drops[market] = counts
        if market in s1.TRADED:
            traded[market] = opportunities
            primary.extend(r for r in s1.evaluate_market(bars,market,primary_only=True)[0]
                           if r["setup"] == "S3" and r["year"] in YEARS)
        else:
            evidence[market] = opportunities
        print(f"{market}: {len(opportunities)} S3 opportunities",flush=True)
        del bars
    scored, models = walk_forward(traded, evidence)
    selected = {}
    selection_counts = {}
    for market, opportunities in scored.items():
        selected[market], selection_counts[market] = sequential_trades(opportunities)
    random_95, random_count = _random_percentile(selected, data_root)
    result = summarize(selected, primary, selection_counts, models, random_95, random_count, drops)
    output.mkdir(parents=True,exist_ok=True)
    (output/"stage2.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    (output/"stage2.md").write_text(markdown(result))
    with ledger.open("a",newline="") as file:
        writer=csv.writer(file,lineterminator="\n")
        writer.writerow(["swing-v1-stage2-s3",pd.Timestamp.now(tz="UTC").date().isoformat(),
                         hashlib.sha256(b"swing-v1:stage2:S3:section10").hexdigest(),"swing_v1_stage2",
                         "S3;LightGBM net-R;12 options;threshold=0.05R;walk-forward",
                         "DEV<2023-01-01", "development",
                         json.dumps({"net_R":result["pooled_traded"]["net_R"],
                                     "t":result["pooled_traded"]["t_stat"],
                                     "trades":result["pooled_traded"]["trades"],
                                     "total_R":result["total_R"]}),result["verdict"]])
    return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root",type=Path,default=Path("data"))
    parser.add_argument("--output",type=Path,default=Path("reports/research/swing_v1"))
    parser.add_argument("--ledger",type=Path,default=Path("reports/trials.csv"))
    args=parser.parse_args()
    result=run(args.data_root,args.output,args.ledger)
    print(result["verdict"])


if __name__ == "__main__":
    main()
