"""Causal multi-timeframe windows for the development-only label grid.

One sample is one 15-minute signal anchor. Bars and features are selected by
``known_at <= anchor known_at``. Missing history discards an anchor instead of
padding it with information from a different regime.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
import os

import numpy as np
import pandas as pd

from msd.research.dataset import DEV_END, FORBIDDEN

WINDOWS = {"1m": 240, "15m": 96, "1h": 96, "4h": 60}
FREQUENCIES = {"1m": "1min", "15m": "15min", "1h": "1h", "4h": "4h"}
CHANNELS = ("open", "high", "low", "close", "spread", "volume_z")
SL_GRID = (.5, 1., 1.5, 2., 3.)
TP_GRID = (.5, 1., 1.5, 2., 3., 4., 6.)
SYMBOL_START = {"USATECHIDXUSD": "2018-12-16T23:00:00Z",
                "USA500IDXUSD": "2018-12-16T23:00:00Z",
                "XAUUSD": "2008-01-01T00:00:00Z",
                "BTCUSDT": "2017-01-01T00:00:00Z",
                "ETHUSDT": "2017-01-01T00:00:00Z"}


@contextmanager
def _data_cwd(root: Path):
    previous = Path.cwd()
    os.chdir(root.resolve().parent)
    try:
        yield
    finally:
        os.chdir(previous)


def load_executable_1m(symbol: str, start, end, data_root: Path, *, venue: str | None=None) -> pd.DataFrame:
    """Use the same source and adjusted executable price view as stage 9."""
    from msd.data import load
    from msd.processing.pipeline import (_adjusted_price_view, _cash_era_only,
                                         _feature_label_bars, _modelled_spread,
                                         assert_executable_spread)
    if symbol not in SYMBOL_START:
        raise ValueError(f"Unsupported symbol: {symbol}")
    left = max(pd.Timestamp(start).tz_convert("UTC") if pd.Timestamp(start).tzinfo else
               pd.Timestamp(start).tz_localize("UTC"), pd.Timestamp(SYMBOL_START[symbol]))
    if venue == "binance_perp":
        from msd.processing.crypto_perp import _read_range, executable_perp_bars
        return executable_perp_bars(
            _read_range(Path(data_root)/"bars"/"binance_um", symbol, left, pd.Timestamp(end)), symbol)
    with _data_cwd(Path(data_root)):
        # After the cash-era switch both index primaries are Dukascopy CFD
        # quotes. Passing the source explicitly avoids an unused HistData
        # catalog dependency on the transferred Roihu bundle.
        source = "dukascopy" if symbol in {"USATECHIDXUSD", "USA500IDXUSD"} else None
        bars = load(symbol, left, end, source=source)
        bars = _cash_era_only(bars, symbol)
        bars = _adjusted_price_view(bars.sort_values("ts").reset_index(drop=True))
        bars = _feature_label_bars(bars)
        bars = _modelled_spread(bars, symbol)
        if not bars.empty:
            assert_executable_spread(bars, symbol)
    return bars


@dataclass
class SequenceData:
    windows: dict[str, np.ndarray]  # [anchor, time, channel]
    dense: np.ndarray
    target: np.ndarray  # [anchor, side, SL, TP]
    mask: np.ndarray
    p0: np.ndarray
    anchors: pd.DataFrame  # known_at and label_end_ts, one row per anchor
    feature_names: tuple[str, ...]
    sides: tuple[int, int] = (-1, 1)
    sl_grid: tuple[float, ...] = SL_GRID
    tp_grid: tuple[float, ...] = TP_GRID
    tp_is_r_multiple: bool = False
    labels: pd.DataFrame | None = None

    def __len__(self) -> int:
        return len(self.anchors)


def _prepare_bars(frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
    required = {f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc"}
    if not required <= set(frame):
        raise ValueError(f"Missing bar columns: {sorted(required - set(frame))}")
    bars = frame.copy()
    if "known_at" not in bars:
        if "ts" not in bars:
            raise ValueError("Bars need ts or known_at")
        bars["known_at"] = pd.to_datetime(bars.ts, utc=True) + pd.Timedelta(frequency)
    bars["known_at"] = pd.to_datetime(bars.known_at, utc=True)
    if bars.known_at.isna().any() or bars.known_at.duplicated().any():
        raise ValueError("Bar known_at must be unique and non-null")
    return bars.sort_values("known_at").reset_index(drop=True)


def _encode(bars: pd.DataFrame, mid: float, atr: float) -> np.ndarray:
    bid = bars[[f"bid_{c}" for c in "ohlc"]].to_numpy(float)
    ask = bars[[f"ask_{c}" for c in "ohlc"]].to_numpy(float)
    price = ((bid + ask) / 2 - mid) / atr
    spread = ((ask[:, 3] - bid[:, 3]) / atr)[:, None]
    if "volume" in bars:
        volume = pd.to_numeric(bars.volume, errors="coerce").to_numpy(float)
        # This normalizer is trailing within the selected window only.
        z = np.zeros(len(volume))
        for i in range(len(volume)):
            trailing = volume[max(0, i - 19):i + 1]
            if np.isfinite(trailing).all() and len(trailing) >= 2:
                sd = trailing.std()
                if sd > 0:
                    z[i] = (volume[i] - trailing.mean()) / sd
    else:
        z = np.zeros(len(bars))
    out = np.column_stack((price, spread, z)).astype("float32")
    if not np.isfinite(out).all():
        raise ValueError("Nonfinite sequence channel")
    return out


def grid_from_config(config: dict) -> tuple[tuple[float, ...], tuple[float, ...], bool]:
    """Return (SL-in-ATR, TP-axis, TP-is-R) with the legacy grid as default."""
    grid = config.get("grid")
    if grid is None:
        return SL_GRID, TP_GRID, False
    sl_grid = tuple(float(value) for value in grid.get("sl_atr", ()))
    has_atr, has_r = "tp_atr" in grid, "tp_r" in grid
    if has_atr == has_r:
        raise ValueError("Grid requires exactly one of tp_atr or tp_r")
    tp_grid = tuple(float(value) for value in grid["tp_r" if has_r else "tp_atr"])
    if not sl_grid or not tp_grid or any(value <= 0 for value in (*sl_grid, *tp_grid)):
        raise ValueError("Grid distances must be non-empty and positive")
    if (any(left >= right for left, right in zip(sl_grid, sl_grid[1:])) or
            any(left >= right for left, right in zip(tp_grid, tp_grid[1:]))):
        raise ValueError("Grid distances must be strictly increasing")
    return sl_grid, tp_grid, has_r


def build_windows(bars: dict[str, pd.DataFrame], features: pd.DataFrame,
                  labels: pd.DataFrame, *, windows: dict[str, int] | None = None,
                  feature_cols: list[str] | None = None,
                  sl_grid: tuple[float, ...] = SL_GRID,
                  tp_grid: tuple[float, ...] = TP_GRID,
                  tp_is_r_multiple: bool = False) -> SequenceData:
    """Build complete anchors with a full both-side SL/TP grid.

    Label ``ts`` is the open of the 1m signal bar; its close is its known_at.
    The label outcome is never used as an input. Labels crossing the DEV end are
    rejected even if their anchor lies in DEV.
    """
    lengths = WINDOWS if windows is None else windows
    if set(lengths) != set(WINDOWS) or any(n < 1 for n in lengths.values()):
        raise ValueError("Positive lengths for all four timeframes required")
    prepared = {tf: _prepare_bars(bars[tf], FREQUENCIES[tf]) for tf in WINDOWS}
    f = features.copy()
    f["known_at"] = pd.to_datetime(f.known_at, utc=True)
    f = f.sort_values("known_at").drop_duplicates("known_at", keep="last").reset_index(drop=True)
    if feature_cols is None:
        feature_cols = [c for c in f if c not in {"ts", "known_at"} and not c.endswith("_bar_known_at")
                        and pd.api.types.is_numeric_dtype(f[c]) and c not in FORBIDDEN]
    if set(feature_cols) & FORBIDDEN:
        raise ValueError("Target/outcome columns cannot be dense inputs")
    if "1h_atr14_price" not in f:
        raise ValueError("Features require causal 1h_atr14_price")
    lab = labels.copy()
    lab["ts"] = pd.to_datetime(lab.ts, utc=True)
    lab["known_at"] = pd.to_datetime(lab.known_at, utc=True) if "known_at" in lab else lab.ts + pd.Timedelta(minutes=1)
    lab["exit_ts"] = pd.to_datetime(lab.exit_ts, utc=True)
    lab = lab[(lab.known_at < DEV_END) & (lab.exit_ts < DEV_END)]
    if lab.empty:
        raise ValueError("No completed DEV labels")
    timestamps = {tf: pd.DatetimeIndex(b.known_at) for tf, b in prepared.items()}
    f_times = pd.DatetimeIndex(f.known_at)
    arrays = {tf: [] for tf in WINDOWS}
    dense, targets, masks, baselines, anchor_rows, label_rows = [], [], [], [], [], []
    for anchor, group in lab.groupby("known_at", sort=True):
        if group.ts.iloc[0].minute % 15:
            continue
        tp_column = "tp_r" if tp_is_r_multiple and "tp_r" in group else "tp_atr"
        if group[["side", "sl_atr", tp_column]].duplicated().any():
            raise ValueError("Duplicate grid cell")
        fi = f_times.searchsorted(anchor, side="right") - 1
        if fi < 0:
            continue
        feature = f.iloc[fi]
        atr = float(feature["1h_atr14_price"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        segments = {}
        for tf, n in lengths.items():
            end = timestamps[tf].searchsorted(anchor, side="right")
            if end < n:
                break
            segment = prepared[tf].iloc[end - n:end]
            # Session gaps are expected for indices and gold. These are the
            # last N *observed completed* bars; no missing bar is synthesized.
            # A multi-day hole indicates an absent monthly input, not a
            # routine weekend or exchange holiday.
            if segment.known_at.diff().iloc[1:].gt(pd.Timedelta(days=7)).any():
                break
            segments[tf] = segment
        if len(segments) != len(WINDOWS):
            continue
        close = prepared["1m"].iloc[timestamps["1m"].searchsorted(anchor, side="right") - 1]
        mid = (float(close.bid_c) + float(close.ask_c)) / 2
        row = pd.to_numeric(feature[feature_cols], errors="coerce").to_numpy(float)
        # The production dense table contains deliberately unavailable cross-market
        # fields. Zero imputation is fixed, causal, and independent of future folds.
        row = np.nan_to_num(row, nan=0., posinf=0., neginf=0.)
        y = np.zeros((2, len(sl_grid), len(tp_grid)), dtype="float32")
        mask = np.zeros_like(y, dtype=bool)
        p0 = np.empty_like(y)
        for si, side in enumerate((-1, 1)):
            for i, sl in enumerate(sl_grid):
                for j, tp_value in enumerate(tp_grid):
                    tp_atr = sl * tp_value if tp_is_r_multiple else tp_value
                    p0[si, i, j] = sl / (sl + tp_atr)
        canonical = group.copy()
        if tp_is_r_multiple:
            canonical["_tp_grid"] = (pd.to_numeric(canonical["tp_r"], errors="coerce")
                                      if "tp_r" in canonical else
                                      pd.to_numeric(canonical["tp_atr"], errors="coerce") /
                                      pd.to_numeric(canonical["sl_atr"], errors="coerce"))
        else:
            canonical["_tp_grid"] = pd.to_numeric(canonical["tp_atr"], errors="coerce")
        canonical["_tp_grid"] = canonical["_tp_grid"].round(12)
        for _, item in canonical.iterrows():
            try:
                si = (-1, 1).index(int(item.side))
                i = next(k for k, value in enumerate(sl_grid)
                         if np.isclose(value, float(item.sl_atr)))
                j = next(k for k, value in enumerate(tp_grid)
                         if np.isclose(value, float(item._tp_grid)))
            except (ValueError, StopIteration) as error:
                raise ValueError("Label outside grid") from error
            if int(item.outcome) in (-1, 1):
                y[si, i, j] = float(int(item.outcome) == 1)
                mask[si, i, j] = True
        if not mask.any():
            continue
        for tf, segment in segments.items():
            arrays[tf].append(_encode(segment, mid, atr))
        dense.append(row.astype("float32"))
        targets.append(y)
        masks.append(mask)
        baselines.append(p0)
        anchor_rows.append({"known_at": anchor, "label_end_ts": group.exit_ts.max(),
                            "price": mid, "atr": atr,
                            "spread": float(close.ask_c) - float(close.bid_c)})
        label_rows.append(canonical)
    if not dense:
        raise ValueError("No complete causal windows")
    return SequenceData({tf: np.stack(v) for tf, v in arrays.items()}, np.stack(dense),
                        np.stack(targets), np.stack(masks), np.stack(baselines),
                        pd.DataFrame(anchor_rows), tuple(feature_cols), sl_grid=sl_grid,
                        tp_grid=tp_grid, tp_is_r_multiple=tp_is_r_multiple,
                        labels=pd.concat(label_rows, ignore_index=True))
