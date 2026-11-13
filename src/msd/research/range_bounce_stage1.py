"""DEV-only Stage 1 report for the frozen range-bounce combiner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from msd.methods.range_bounce import TIMEFRAMES, active_ranges, setups
from msd.processing.crypto_perp import executable_perp_bars
from msd.processing.labels import deadline_after_trading_days
from msd.processing.timeutil import epoch_seconds

DEV_END = pd.Timestamp("2023-01-01", tz="UTC")
SYMBOLS = ("XAUUSD", "USATECHIDXUSD", "USA500IDXUSD", "BTCUSDT", "ETHUSDT")
STARTS = {"XAUUSD": 2008, "USATECHIDXUSD": 2019, "USA500IDXUSD": 2019,
          "BTCUSDT": 2020, "ETHUSDT": 2020}
SOURCE = {"XAUUSD": "dukascopy", "USATECHIDXUSD": "dukascopy",
          "USA500IDXUSD": "dukascopy", "BTCUSDT": "binance_um", "ETHUSDT": "binance_um"}
STOP_ATR = (.25, .5, 1.)
TARGETS = ("middle", "75pct", "far_edge", "1R", "2R")


def _paths(root: Path, start_year: int) -> list[Path]:
    return [path for path in sorted(root.glob("*.parquet"))
            if path.stem[:4].isdigit() and start_year <= int(path.stem[:4]) <= 2022]


def load_bars(data_root: Path, symbol: str) -> pd.DataFrame:
    paths = _paths(data_root/"bars"/SOURCE[symbol]/symbol, STARTS[symbol])
    if not paths:
        raise FileNotFoundError(symbol)
    columns = ["ts", *[f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc"]]
    bars = pd.concat([pd.read_parquet(path, columns=columns) for path in paths], ignore_index=True)
    bars["ts"] = pd.to_datetime(bars.ts, utc=True).astype("datetime64[ns, UTC]")
    bars = bars[(bars.ts < DEV_END)].sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    if symbol in {"BTCUSDT", "ETHUSDT"}:
        bars = executable_perp_bars(bars, symbol)
    bars["symbol"] = symbol
    if len(bars) and bars.ts.max() >= DEV_END:
        raise AssertionError("Test/Final bar loaded")
    return bars


def load_candles(data_root: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    paths = _paths(data_root/"derived"/f"bars_{timeframe}"/symbol, STARTS[symbol])
    columns = ["ts", "known_at", "bid_h", "bid_l", "bid_c"]
    frame = pd.concat([pd.read_parquet(path, columns=columns) for path in paths], ignore_index=True)
    frame["ts"] = pd.to_datetime(frame.ts, utc=True).astype("datetime64[ns, UTC]")
    frame["known_at"] = pd.to_datetime(frame.known_at, utc=True).astype("datetime64[ns, UTC]")
    return frame[(frame.known_at < DEV_END)].sort_values("known_at").drop_duplicates("known_at").reset_index(drop=True)


def label_setups(candidates: pd.DataFrame, bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Label the frozen 15-option menu with executable bid/ask bars."""
    if candidates.empty:
        return pd.DataFrame()
    from msd._msd_kernels import first_hit_batch

    matrix = bars[[f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc"]].to_numpy(dtype="<f8")
    seconds = np.asarray(epoch_seconds(bars.ts), dtype="<i8")
    jobs: list[float] = []
    metadata: list[dict] = []
    klass = "crypto" if symbol in {"BTCUSDT", "ETHUSDT"} else "index"
    for setup_id, row in enumerate(candidates.itertuples(index=False)):
        entry_i = int(row.entry_index)
        if entry_i >= len(bars):
            continue
        entry_ts = bars.ts.iloc[entry_i]
        contractual = deadline_after_trading_days(entry_ts, 5, klass)
        deadline_i = int(np.searchsorted(seconds, int(epoch_seconds(contractual)), side="left"))
        if deadline_i >= len(bars) or bars.ts.iloc[deadline_i] >= DEV_END:
            continue
        deadline = bars.ts.iloc[deadline_i]  # first executable open at/after the safety cap
        mid = (float(bars.bid_o.iloc[entry_i])+float(bars.ask_o.iloc[entry_i]))/2
        nearest_stop = row.bottom-.25*row.atr if row.side > 0 else row.top+.25*row.atr
        middle = (row.bottom+row.top)/2
        # A gap through the nearest stop or structural midpoint makes the
        # frozen 15-option menu undefined; reject the setup, not one option.
        if row.side*(mid-nearest_stop) <= 0 or row.side*(middle-mid) <= 0:
            continue
        for stop_atr in STOP_ATR:
            stop = float(row.bottom-stop_atr*row.atr if row.side > 0 else row.top+stop_atr*row.atr)
            risk = abs(mid-stop)
            structural = {"middle": (row.bottom+row.top)/2,
                          "75pct": row.bottom+.75*(row.top-row.bottom) if row.side > 0 else row.top-.75*(row.top-row.bottom),
                          "far_edge": row.top if row.side > 0 else row.bottom,
                          "1R": mid+row.side*risk, "2R": mid+row.side*2*risk}
            for target_name in TARGETS:
                target = float(structural[target_name])
                if row.side*(target-mid) <= 0 or row.side*(mid-stop) <= 0:
                    raise AssertionError("invalid frozen option geometry after setup preflight")
                jobs.extend([entry_i-1, int(row.side), mid, stop, target,
                             int(epoch_seconds(deadline)), 1, 0., np.nan, np.nan,
                             1 if klass == "crypto" else 0])
                metadata.append({**row._asdict(), "setup_id": setup_id, "stop_atr": stop_atr,
                                 "target": target_name, "stop_price": stop, "target_price": target,
                                 "deadline_ts": deadline})
    if not jobs:
        return pd.DataFrame()
    values = np.asarray(first_hit_batch(matrix.tobytes(), seconds.tobytes(), jobs, 11), dtype=float).reshape(-1, 9)
    reasons = {1: "tp", -1: "sl", 0: "time", -2: "no_fill"}
    output = []
    for meta, value in zip(metadata, values):
        code, exit_i, fill, exit_price, net_r, gross_r, nights, entry_i, risk = value
        exit_i, entry_i = int(exit_i), int(entry_i)
        if exit_i < 0 or entry_i < 0:
            continue
        exit_ts = bars.ts.iloc[exit_i]
        if exit_ts > meta["deadline_ts"]:
            raise AssertionError(f"exit {exit_ts} after deadline {meta['deadline_ts']}")
        if exit_ts >= DEV_END:
            continue
        output.append({**meta, "entry_ts": bars.ts.iloc[entry_i], "fill_price": fill,
                       "exit_ts": exit_ts, "exit_price": exit_price, "exit_reason": reasons[int(code)],
                       "planned_risk": risk, "gross_R": gross_r, "net_R": net_r,
                       "spread_R": gross_r-net_r, "financing_nights": int(nights)})
    result = pd.DataFrame(output)
    if not result.empty and pd.to_datetime(result.exit_ts, utc=True).max() >= DEV_END:
        raise AssertionError("Test/Final label produced")
    return result


def metrics(labels: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["symbol", "timeframe", "stop_atr", "target"]
    for key, group in labels.groupby(keys, observed=True, sort=True):
        r = group.net_R.to_numpy(float); n = len(r); sd = r.std(ddof=1) if n > 1 else np.nan
        wins = group.exit_reason.eq("tp")
        by_year = group.assign(year=pd.to_datetime(group.entry_ts, utc=True).dt.year).groupby("year").net_R.mean()
        rows.append(dict(zip(keys, key)) | {"trades": n, "hit_rate": float(wins.mean()),
            "net_avg_R": float(r.mean()), "t": float(r.mean()/(sd/np.sqrt(n))) if sd > 0 else np.nan,
            "time_exit_share": float(group.exit_reason.eq("time").mean()),
            "per_year": ", ".join(f"{int(y)}:{v:+.3f}" for y, v in by_year.items())})
    return pd.DataFrame(rows)


def _md_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return ""
    def cell(value):
        if isinstance(value, (float, np.floating)):
            return "" if not np.isfinite(value) else f"{value:.4f}"
        return str(value)
    header = "| " + " | ".join(map(str, frame.columns)) + " |"
    rule = "| " + " | ".join("---" for _ in frame.columns) + " |"
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *body])


def _markdown(all_setups: pd.DataFrame, all_labels: pd.DataFrame) -> str:
    lines = ["# Range-bounce combiner v1 — Stage 1 (DEV only)", "",
             "> Frozen-rule diagnostic only. No model was trained and no trial-ledger row was added. "
             "Only timestamps before 2023-01-01 were loaded; labels that could cross the boundary were dropped.", ""]
    for symbol in SYMBOLS:
        title = "Primary: XAUUSD" if symbol == "XAUUSD" else f"Secondary: {symbol}"
        subset = all_setups[all_setups.symbol.eq(symbol)]
        labels = all_labels[all_labels.symbol.eq(symbol)]
        lines += [f"## {title}", ""]
        yearly = (subset.assign(year=pd.to_datetime(subset.entry_ts, utc=True).dt.year)
                  .groupby(["timeframe", "year"], observed=True).agg(
                      setups=("range_id", "size"), avg_height_atr=("height_atr", "mean"),
                      avg_age_candles=("age_candles", "mean")).reset_index())
        lines += [_md_table(yearly) if len(yearly) else "No setups.", "",
                  "### Fixed-option outcomes", ""]
        table = metrics(labels)
        lines += [_md_table(table.drop(columns="symbol")) if len(table) else "No complete DEV labels.", ""]
    return "\n".join(lines)+"\n"


def run(data_root: Path, output_root: Path, report_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_root.mkdir(parents=True, exist_ok=True); report_path.parent.mkdir(parents=True, exist_ok=True)
    setup_parts, label_parts = [], []
    for symbol in SYMBOLS:
        bars = load_bars(data_root, symbol)
        for timeframe in TIMEFRAMES:
            states = active_ranges(load_candles(data_root, symbol, timeframe), timeframe)
            found = setups(bars, states, timeframe)
            if found.empty:
                continue
            found["symbol"] = symbol
            labelled = label_setups(found, bars, symbol)
            if not labelled.empty:
                # Stage 1 retains only setups with the complete frozen menu;
                # boundary-crossing and next-open gap invalidations are not
                # partially represented.
                kept = np.sort(labelled.setup_id.unique().astype(int))
                found = found.iloc[kept].reset_index(drop=True)
            else:
                found = found.iloc[0:0]
            setup_parts.append(found); label_parts.append(labelled)
        del bars
    all_setups = pd.concat(setup_parts, ignore_index=True) if setup_parts else pd.DataFrame()
    all_labels = pd.concat(label_parts, ignore_index=True) if label_parts else pd.DataFrame()
    all_setups.to_parquet(output_root/"setups.parquet", index=False, compression="zstd")
    all_labels.to_parquet(output_root/"labels.parquet", index=False, compression="zstd")
    report_path.write_text(_markdown(all_setups, all_labels))
    summary = {"setups": len(all_setups), "labels": len(all_labels),
               "symbols": {s: {"setups": int(all_setups.symbol.eq(s).sum()),
                                "labels": int(all_labels.symbol.eq(s).sum())} for s in SYMBOLS}}
    report_path.with_suffix(".json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    return all_setups, all_labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-root", type=Path, default=Path("data/combiner_v1/stage1"))
    parser.add_argument("--report", type=Path, default=Path("reports/research/combiner_v1/stage1_xau.md"))
    args = parser.parse_args(); run(args.data_root, args.output_root, args.report)


if __name__ == "__main__":
    main()
