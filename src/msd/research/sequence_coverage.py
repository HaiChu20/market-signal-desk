"""Low-memory audit of sequence anchor eligibility by symbol and DEV year."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from msd.research.sequence_data import WINDOWS, FREQUENCIES

SOURCE = {"BTCUSDT": "binance_spot", "ETHUSDT": "binance_spot",
          "USATECHIDXUSD": "dukascopy", "USA500IDXUSD": "dukascopy", "XAUUSD": "dukascopy"}


def _read(root: Path, months, columns):
    frames = []
    for month in months:
        path = root / f"{month}.parquet"
        if not path.exists():
            continue
        available = set(pq.read_schema(path).names)
        use = [name for name in columns if name in available]
        frames.append(pd.read_parquet(path, columns=use))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def anchor_coverage(data_root: Path, symbol: str, year: int) -> dict:
    """Count the same time/ATR/history/resolved-label gates as build_windows.

    Reads only timestamp, outcome and ATR columns. Processing one year at a
    time bounds memory independently of the 2008-2022 XAU history length.
    """
    start = pd.Timestamp(year, 1, 1, tz="UTC")
    end = min(start + pd.DateOffset(years=1), pd.Timestamp("2023-01-01", tz="UTC"))
    months = pd.period_range((start - pd.Timedelta(days=30)).tz_localize(None).to_period("M"),
                             (end - pd.Timedelta(minutes=1)).tz_localize(None).to_period("M"), freq="M")
    labels = _read(data_root / "labels" / symbol, months[1:], ["ts", "outcome", "exit_ts"])
    if labels.empty:
        return {"symbol": symbol, "year": year, "anchors": 0, "kept": 0, "coverage": 0.}
    labels["ts"] = pd.to_datetime(labels.ts, utc=True)
    labels["exit_ts"] = pd.to_datetime(labels.exit_ts, utc=True)
    labels = labels[(labels.ts >= start) & (labels.ts < end) &
                    (labels.ts.dt.minute % 15 == 0) &
                    (labels.exit_ts < pd.Timestamp("2023-01-01", tz="UTC")) &
                    labels.outcome.isin((-1, 1))]
    anchors = pd.DatetimeIndex(labels.ts.drop_duplicates().sort_values() + pd.Timedelta(minutes=1))
    if not len(anchors):
        return {"symbol": symbol, "year": year, "anchors": 0, "kept": 0, "coverage": 0.}
    valid = np.ones(len(anchors), dtype=bool)
    feature = _read(data_root / "features" / symbol, months, ["known_at", "1h_atr14_price"])
    if feature.empty:
        valid[:] = False
    else:
        feature["known_at"] = pd.to_datetime(feature.known_at, utc=True)
        feature = feature.sort_values("known_at").drop_duplicates("known_at", keep="last")
        ix = pd.DatetimeIndex(feature.known_at).searchsorted(anchors, side="right") - 1
        valid &= ix >= 0
        atr = feature["1h_atr14_price"].to_numpy(float)
        valid &= np.isfinite(atr[np.maximum(ix, 0)]) & (atr[np.maximum(ix, 0)] > 0)
    for tf, length in WINDOWS.items():
        folder = (data_root / "bars" / SOURCE[symbol] / symbol if tf == "1m"
                  else data_root / "derived" / f"bars_{tf}" / symbol)
        frame = _read(folder, months, ["ts", "known_at", "bad_tick", "stale_expired"])
        if frame.empty:
            valid[:] = False
            continue
        if "bad_tick" in frame:
            frame = frame[~frame.bad_tick.fillna(False).astype(bool)]
        if "stale_expired" in frame:
            frame = frame[~frame.stale_expired.fillna(False).astype(bool)]
        times = pd.DatetimeIndex(pd.to_datetime(frame.known_at, utc=True) if "known_at" in frame
                                 else pd.to_datetime(frame.ts, utc=True) + pd.Timedelta(FREQUENCIES[tf]))
        times = times.drop_duplicates().sort_values()
        ix = times.searchsorted(anchors, side="right")
        valid &= ix >= length
        if len(times) >= length:
            gaps = pd.Series(times).diff().gt(pd.Timedelta(days=7)).astype(int)
            bad = gaps.rolling(length - 1, min_periods=1).sum().to_numpy()
            valid &= bad[np.maximum(ix - 1, 0).clip(max=len(bad) - 1)] == 0
    kept = int(valid.sum())
    return {"symbol": symbol, "year": year, "anchors": len(anchors),
            "kept": kept, "coverage": kept / len(anchors)}
