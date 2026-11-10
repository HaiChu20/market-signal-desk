"""Data manifests, catalog generation, and source-aware local loading."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

SOURCE_DIRS = {
    "dukascopy": Path("data/bars/dukascopy"),
    "histdata": Path("data/bars/histdata"),
    "binance_spot": Path("data/bars/binance_spot"),
    "binance_um": Path("data/bars/binance_um"),
}


def write_manifest(source: str, symbol: str, frame: pd.DataFrame, price_type: str, volume_type: str, root: Path | None = None) -> Path:
    if source not in SOURCE_DIRS:
        raise ValueError(source)
    target_root = root or SOURCE_DIRS[source]
    path = target_root / symbol / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = json.loads(path.read_text()) if path.exists() else {}
    months = dict(prior.get("months", {}))
    if len(frame):
        frame = frame.copy()
        frame["ts"] = pd.to_datetime(frame.ts, utc=True)
        month = frame.ts.dt.strftime("%Y-%m").iloc[0]
        months[month] = {"first_ts": str(frame.ts.min()), "last_ts": str(frame.ts.max()), "bars": int(len(frame))}
    first = min((pd.Timestamp(value["first_ts"]) for value in months.values()), default=None)
    last = max((pd.Timestamp(value["last_ts"]) for value in months.values()), default=None)
    document = {"source": source, "symbol": symbol,
                "first_ts": str(first) if first is not None else None,
                "last_ts": str(last) if last is not None else None,
                "bars": sum(int(value["bars"]) for value in months.values()), "columns": list(frame.columns),
                "price_type": price_type, "volume_type": volume_type, "months": months}
    path.write_text(json.dumps(document, indent=2) + "\n")
    return path


def rebuild_manifest(source: str, symbol: str) -> Path:
    """Recompute a dataset manifest from its on-disk monthly Parquet files.

    Month metadata is read from Parquet rather than trusted from the existing
    manifest, so orphaned/stale month entries are removed. Files without an
    ``msd_complete`` marker are conservatively marked incomplete.
    """
    if source not in SOURCE_DIRS:
        raise ValueError(source)
    directory = SOURCE_DIRS[source] / symbol
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet"))
    if not files:
        raise FileNotFoundError(f"no monthly parquet files for {source}:{symbol} under {directory}")
    manifest_path = directory / "manifest.json"
    prior = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    months: dict[str, dict] = {}
    columns: list[str] = []
    def file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    for path in files:
        metadata = pq.read_metadata(path)
        schema = pq.read_schema(path)
        if not columns:
            columns = schema.names
        table = pq.read_table(path, columns=["ts"])
        ts = pd.to_datetime(table.column("ts").to_pandas(), utc=True)
        month = path.stem
        if len(ts):
            first_ts, last_ts = ts.min(), ts.max()
            expected_month = first_ts.strftime("%Y-%m") == month and last_ts.strftime("%Y-%m") == month
            raw_complete = (metadata.metadata or {}).get(b"msd_complete")
            complete = raw_complete == b"1" if raw_complete is not None else False
            months[month] = {
                "first_ts": str(first_ts), "last_ts": str(last_ts),
                "bars": int(metadata.num_rows), "complete": bool(complete and expected_month),
                "sha256": file_sha256(path),
            }
        else:
            months[month] = {
                "first_ts": None, "last_ts": None, "bars": 0, "complete": False,
                "sha256": file_sha256(path),
            }
    populated = [month for month in months.values() if month["bars"]]
    first = min((pd.Timestamp(month["first_ts"]) for month in populated), default=None)
    last = max((pd.Timestamp(month["last_ts"]) for month in populated), default=None)
    price_type = prior.get("price_type", "bidask" if source == "dukascopy" else "trade" if source.startswith("binance") else "bid")
    volume_type = prior.get("volume_type", "tick" if source == "dukascopy" else "real" if source.startswith("binance") else "none")
    document = {
        "source": source, "symbol": symbol,
        "first_ts": str(first) if first is not None else None,
        "last_ts": str(last) if last is not None else None,
        "bars": sum(int(month["bars"]) for month in months.values()),
        "columns": columns, "price_type": price_type, "volume_type": volume_type,
        "months": months,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n")
    temporary.replace(manifest_path)
    return manifest_path


def load_source(symbol: str, start, end, source: str) -> pd.DataFrame:
    if source not in SOURCE_DIRS:
        raise ValueError(f"unknown data source: {source}")
    root = SOURCE_DIRS[source] / symbol
    files = sorted(root.glob("*.parquet")) if root.exists() else []
    if not files:
        raise FileNotFoundError(f"no {source} data files for {symbol} under {root}")
    if source == "dukascopy":
        from .dukascopy import load
        return load(symbol, start, end)
    if source == "histdata":
        from .histdata import load
        return load(symbol, start, end)
    if source == "binance_spot":
        return _load_parquet(symbol, start, end, SOURCE_DIRS[source])
    if source == "binance_um":
        return _load_parquet(symbol, start, end, SOURCE_DIRS[source])
    raise ValueError(f"unknown data source: {source}")


def _load_parquet(symbol: str, start, end, root: Path) -> pd.DataFrame:
    start, end = _utc(start), _utc(end)
    paths = sorted((root / symbol).glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet")) if (root / symbol).exists() else []
    frames = [pd.read_parquet(path) for path in paths if start.strftime("%Y-%m") <= path.stem <= end.strftime("%Y-%m")]
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result.ts = pd.to_datetime(result.ts, utc=True).astype("datetime64[ns, UTC]")
    return result[(result.ts >= start) & (result.ts < end + pd.Timedelta(days=1))].sort_values("ts").reset_index(drop=True)


def _utc(value) -> pd.Timestamp:
    stamp=pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def build_catalog() -> str:
    lines = ["# Data catalog", "", "Dataset manifests and local bar inventories. Sizes include Parquet only.", "",
             "| Source | Symbol | First ts | Last ts | Bars | Parquet size | Columns | Price type | Volume type |", "|---|---|---|---|---:|---:|---|---|---|"]
    datasets = []
    for source, base in SOURCE_DIRS.items():
        if not base.exists():
            continue
        for directory in sorted(p for p in base.iterdir() if p.is_dir()):
            files = sorted(directory.glob("*.parquet"))
            if not files:
                continue
            frames = [pd.read_parquet(path, columns=["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"])
                      for path in files]
            frame = pd.concat(frames, ignore_index=True)
            manifest = directory / "manifest.json"
            if manifest.exists():
                meta = json.loads(manifest.read_text())
            else:
                price = "bidask" if bool((frame.ask_o != frame.bid_o).any()) else "trade" if source.startswith("binance") else "bid"
                meta = {"price_type": price, "volume_type": "real" if frame.volume.notna().any() else "none"}
            datasets.append((source, directory.name, frame, files, meta))
            size = sum(path.stat().st_size for path in files)
            columns = ", ".join(frame.columns)
            lines.append(f"| {source} | {directory.name} | {frame.ts.min()} | {frame.ts.max()} | {len(frame):,} | {size / 1024**2:.1f} MiB | {columns} | {meta['price_type']} | {meta['volume_type']} |")
    lines += ["", "## Primary source per instrument and period", "",
              "| Instrument | Period | Primary source | Reason |", "|---|---|---|---|"]
    primary = [
        ("Nasdaq-100", "2010-11–2018-12-16 23:00 UTC", "HistData NSXUSD (futures_cont, back-adjusted)", "only full-day early source; roll and feed regime are explicit"),
        ("Nasdaq-100", "2018-12-16 23:00 UTC onward", "Dukascopy USATECHIDXUSD", "HistData matches closes; Dukascopy adds real bid/ask and tick volume"),
        ("S&P 500", "2010-11–2018-12-16 23:00 UTC", "HistData SPXUSD (futures_cont, back-adjusted)", "only full-day early source; roll and feed regime are explicit"),
        ("S&P 500", "2018-12-16 23:00 UTC onward", "Dukascopy USA500IDXUSD", "HistData matches closes; Dukascopy adds real bid/ask and tick volume"),
        ("Gold", "all available", "Dukascopy XAUUSD", "primary bid/ask source"),
        ("BTC / ETH spot", "all available", "Binance spot", "trade OHLC and real volume/flow"),
        ("BTC / ETH futures", "2019-09 onward", "Binance USD-M", "futures trade OHLC and flow"),
        ("FX, metals, indices, energy context", "all available", "Dukascopy", "primary multi-asset source"),
    ]
    lines.extend(f"| {a} | {b} | {c} | {d} |" for a, b, c, d in primary)
    lines += _gold_bars_per_day_lines()
    lines += ["", "NQ/SPX HistData feed switch was measured at the first exact cash-price bar on 2018-12-16 23:00 UTC. Before it, HistData is a futures-continuous feed: `feed=futures_cont`, quarter rolls are flagged, and `adj_bid_*` applies additive backward adjustments. After it, the primary series is Dukascopy (`feed=cash_cfd`). The switch is intentionally not hidden by source blending. A homogeneous real-volume alternative is CME futures through Databento (paid; $125 credit); no account was created.",
              "", "HistData GRXEUR can be checked against only one Dukascopy DEUIDXEUR month (2014-01), and no LIGHTCMDUSD overlap is present for WTIUSD. Their feed regime and DST behavior therefore remain unverified against a second source; the files are marked `unclassified` rather than assumed to be cash or futures."]
    lines += ["", "## Quality and coverage", "", "Per-source/year coverage and recurring gaps are in `reports/data/data_quality_<SYMBOL>.md`; HistData/Dukascopy cross-validation is in `reports/data/histdata_vs_dukascopy.md`.", ""]
    result = "\n".join(lines)
    path = Path("reports/data/data_catalog.md"); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(result + "\n")
    return result


def _gold_bars_per_day_lines() -> list[str]:
    """Catalog the observed daily-bar density for gold by UTC year."""
    root=SOURCE_DIRS["dukascopy"]/"XAUUSD"
    files=sorted(root.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet")) if root.exists() else []
    if not files: return ["", "## Gold bars per day", "", "No Dukascopy XAUUSD monthly files are available yet.", ""]
    frames=[pd.read_parquet(path,columns=["ts"]) for path in files]
    ts=pd.to_datetime(pd.concat(frames,ignore_index=True).ts,utc=True)
    daily=pd.DataFrame({"year":ts.dt.year,"day":ts.dt.floor("D")}).groupby(["year","day"]).size().rename("bars")
    lines=["", "## Gold bars per day", "", "UTC calendar-day counts from Dukascopy XAUUSD. Median and 10th–90th percentile expose sparse early history.", "",
           "| Year | Days | Median bars/day | P10 | P90 | Days ≥ 1,000 bars |", "|---:|---:|---:|---:|---:|---:|"]
    for year,values in daily.groupby(level="year"):
        arr=values.to_numpy(float)
        lines.append(f"| {year} | {len(arr):,} | {np.median(arr):.0f} | {np.percentile(arr,10):.0f} | {np.percentile(arr,90):.0f} | {int((arr>=1000).sum()):,} |")
    lines.append("")
    return lines


def refresh_gold_coverage_section() -> Path:
    """Refresh only the gold section without scanning every catalog dataset."""
    path=Path("reports/data/data_catalog.md")
    old=path.read_text() if path.exists() else "# Data catalog\n"
    marker="## Gold bars per day"
    if marker in old: old=old[:old.index(marker)].rstrip()+"\n"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(old+"\n".join(_gold_bars_per_day_lines())+"\n")
    return path
