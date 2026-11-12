"""Compare versioned Binance-perp DEV labels with frozen CFD-cost labels."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ("BTCUSDT", "ETHUSDT")


def _old_month(data_root: Path, symbol: str, path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    bars = pd.read_parquet(data_root/"bars"/"binance_spot"/symbol/path.name,
                           columns=["ts", "bid_o", "ask_o"])
    mid = pd.Series((bars.bid_o+bars.ask_o).to_numpy(float)/2,
                    index=pd.to_datetime(bars.ts, utc=True))
    entry_mid = pd.to_datetime(frame.entry_ts, utc=True).map(mid)
    half = (frame.fill_price-entry_mid).abs()
    spread_r = 2*half/frame.planned_risk
    finance_r = frame.gross_R-frame.net_R
    return pd.DataFrame({"sl_atr": frame.sl_atr, "gross_R": frame.gross_R+spread_r,
                         "cost_R": spread_r+finance_r, "net_R": frame.net_R})


def _aggregate(paths: list[Path], reader) -> list[dict]:
    parts = [reader(path) for path in paths]
    frame = pd.concat(parts, ignore_index=True)
    return frame.groupby("sl_atr", observed=True).agg(
        n=("net_R", "size"), mean_gross_R=("gross_R", "mean"),
        mean_cost_R=("cost_R", "mean"), mean_net_R=("net_R", "mean")).reset_index().to_dict("records")


def write_report(data_root: Path=Path("data"), venue_root: Path=Path("data/venues/binance_perp"),
                 output: Path=Path("reports/research/dev_v4_crypto_costs.md")) -> dict:
    result = {}
    lines = ["# Binance USDT-M perpetual DEV cost sanity", "",
        "**PRELIMINARY. Development labels for 2020--2022 only. Test and Final were not loaded.**", "",
        "The old CFD gross is restated before its embedded round-trip spread using the entry half-spread; "
        "the new gross is persisted before spread, fees, and funding, so gross - cost = net in both columns.", ""]
    for symbol in SYMBOLS:
        old_paths = sorted((data_root/"labels"/symbol).glob("202[0-2]-*.parquet"))
        new_paths = sorted((venue_root/"labels"/symbol).glob("202[0-2]-*.parquet"))
        old = _aggregate(old_paths, lambda path: _old_month(data_root, symbol, path))
        new = _aggregate(new_paths, lambda path: pd.read_parquet(path,
            columns=["sl_atr", "gross_R", "cost_R", "net_R"]))
        result[symbol] = {"old_cfd": old, "new_binance_perp": new}
        lines += [f"## {symbol}", "", "| Venue | SL ATR | n | Mean gross R | Mean cost R | Mean net R |",
                  "|---|---:|---:|---:|---:|---:|"]
        for venue, rows in (("old CFD", old), ("Binance perp", new)):
            for row in rows:
                lines.append(f"| {venue} | {row['sl_atr']:.1f} | {row['n']:,} | "
                    f"{row['mean_gross_R']:.4f} | {row['mean_cost_R']:.4f} | {row['mean_net_R']:.4f} |")
        examples = pd.concat([pd.read_parquet(path) for path in new_paths], ignore_index=True)
        keys = pd.DataFrame({"ts": examples.ts.astype(str), "side": examples.side,
                             "sl": examples.sl_atr, "tp": examples.tp_atr})
        examples["sample"] = pd.util.hash_pandas_object(keys, index=False).astype("uint64")
        examples = examples.nsmallest(10, "sample")
        result[symbol]["examples"] = examples[["ts", "side", "sl_atr", "tp_atr", "fill_price",
            "exit_price", "spread_R", "fee_R", "funding_rate_sum", "funding_R", "gross_R",
            "cost_R", "net_R", "exit_reason"]].astype(object).where(pd.notna(examples), None).to_dict("records")
        lines += ["", "### Ten deterministic decomposed rows", "",
            "| ts | side | SL | TP | fill | exit | spread R | fee R | funding sum | funding R | gross R | cost R | net R | reason |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
        for row in result[symbol]["examples"]:
            lines.append(f"| {row['ts']} | {row['side']} | {row['sl_atr']} | {row['tp_atr']} | "
                f"{row['fill_price']:.4f} | {row['exit_price']:.4f} | {row['spread_R']:.4f} | "
                f"{row['fee_R']:.4f} | {row['funding_rate_sum']:.6f} | {row['funding_R']:.4f} | "
                f"{row['gross_R']:.4f} | {row['cost_R']:.4f} | {row['net_R']:.4f} | {row['exit_reason']} |")
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text("\n".join(lines)+"\n")
    (venue_root/"sanity.json").write_text(json.dumps(result, indent=2, default=str, allow_nan=False)+"\n")
    return result


if __name__ == "__main__":
    write_report()
