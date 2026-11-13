"""One-shot Final-v2 Donchian exam. Run only by the data owner."""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import pandas as pd
import pyarrow.parquet as pq

from msd.methods import donchian_atr_breakout
from msd.processing.crypto_perp import apply_perp_costs
from msd.processing.features import build_features, indicator_frame, prepare_feature_cache
from msd.processing.pipeline import (
    _active_mask,
    _adjusted_price_view,
    _feature_label_bars,
    _modelled_spread,
    replay_events_only,
)
from msd.processing.timeframes import build_all_timeframes, build_timeframe
from msd.processing.wide_v1 import _bars, _event_jobs, _funding

from .gating import gate_open_signals
from .ledger import FIELDS, read_trials
from .report_card import metrics
from .test_exam_v1 import (
    FROZEN_CODE,
    WIDE_CONFIG_SHA,
    _event_identity,
    _finite,
    _random_percentile,
)

SCORE_START = pd.Timestamp("2025-01-01", tz="UTC")
WARMUP_START = pd.Timestamp("2024-01-01", tz="UTC")
RULE_NAME = "donchian_atr_breakout"
RUN_ID = "final-v2-donchian"
SYMBOLS = ("USATECHIDXUSD", "USA500IDXUSD", "XAUUSD", "BTCUSDT")
RULE = {"symbols": SYMBOLS, "sl_atr": 3.0, "tp_r": 3.0}
DETECTOR_FILES = (
    "src/msd/methods/donchian_atr_breakout.py",
    "src/msd/methods/_checkpoint.py",
    "src/msd/methods/_detectors.py",
    "src/msd/methods/requirements.py",
)
SOURCE = {symbol: "dukascopy" for symbol in SYMBOLS if symbol != "BTCUSDT"} | {
    "BTCUSDT": "binance_spot"
}


def _config_hash() -> str:
    digest = hashlib.sha256()
    for path in (Path("docs/final_check_v2.md"), Path("docs/test_preregistration_v1.md")):
        digest.update(path.read_bytes())
        digest.update(b"\0")
    digest.update(json.dumps(RULE, sort_keys=True).encode())
    return digest.hexdigest()


def _assert_frozen_provenance() -> None:
    wide = Path("hpc/roihu/sequence/configs/wide_v1.json")
    if hashlib.sha256(wide.read_bytes()).hexdigest() != WIDE_CONFIG_SHA:
        raise RuntimeError("wide_v1 config changed")
    check = subprocess.run(
        ["git", "diff", "--quiet", FROZEN_CODE, "--", *DETECTOR_FILES], check=False
    )
    if check.returncode:
        raise RuntimeError(f"Donchian detector differs from frozen commit {FROZEN_CODE}")


def _month_paths(
    root: Path, start: pd.Timestamp, end_exclusive: pd.Timestamp | None = None
) -> list[Path]:
    return sorted(
        path
        for path in root.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].parquet")
        if path.stem >= start.strftime("%Y-%m")
        and (
            end_exclusive is None
            or pd.Timestamp(f"{path.stem}-01", tz="UTC") < end_exclusive
        )
    )


def _range(paths: list[Path], label: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if not paths:
        raise FileNotFoundError(f"no monthly parquet files for {label}")
    first = pd.read_parquet(paths[0], columns=["ts"])["ts"]
    last = pd.read_parquet(paths[-1], columns=["ts"])["ts"]
    stamps = pd.concat([first, last], ignore_index=True)
    stamps = pd.to_datetime(stamps, utc=True, errors="coerce").dropna()
    if stamps.empty:
        raise ValueError(f"no timestamps in {paths[0]} or {paths[-1]}")
    return stamps.min(), stamps.max() + pd.Timedelta(minutes=1)


def _require_columns(paths: list[Path], columns: set[str], label: str) -> None:
    for path in paths:
        missing = columns - set(pq.read_schema(path).names)
        if missing:
            raise ValueError(f"{label} {path} missing columns: {', '.join(sorted(missing))}")


def _require_months(paths: list[Path], start: pd.Timestamp, end: pd.Timestamp, label: str) -> None:
    actual = {path.stem for path in paths}
    expected = {
        str(month)
        for month in pd.period_range(
            start.tz_localize(None).to_period("M"),
            (end - pd.Timedelta(nanoseconds=1)).tz_localize(None).to_period("M"),
            freq="M",
        )
    }
    missing = sorted(expected - actual)
    if missing:
        raise FileNotFoundError(f"{label} missing months: {', '.join(missing)}")


def input_inventory(data_root: Path) -> dict:
    """Return file names and timestamp coverage only; never compute events or returns."""
    rows: dict[str, dict] = {}
    ends: dict[str, pd.Timestamp] = {}
    for symbol in SYMBOLS:
        detection_root = data_root / "bars" / SOURCE[symbol] / symbol
        detection = _month_paths(detection_root, WARMUP_START)
        _require_columns(
            detection,
            {"ts", *(f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc")},
            f"{symbol} detector bars",
        )
        detection_start, detection_end = _range(detection, f"{symbol} detector bars")
        label_source = "binance_um" if symbol == "BTCUSDT" else "dukascopy"
        label_root = data_root / "bars" / label_source / symbol
        labels = _month_paths(label_root, SCORE_START)
        _require_columns(
            labels,
            {"ts", *(f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc")},
            f"{symbol} executable bars",
        )
        label_start, label_end = _range(labels, f"{symbol} executable bars")
        end = min(detection_end, label_end)
        if end <= SCORE_START:
            raise FileNotFoundError(f"{symbol} has no Final-v2 overlap")
        _require_months(detection, WARMUP_START, end, f"{symbol} detector bars")
        _require_months(labels, SCORE_START, end, f"{symbol} executable bars")
        row = {
            "detector_source": SOURCE[symbol],
            "detector_files": [str(path) for path in detection],
            "detector_range": [detection_start.isoformat(), detection_end.isoformat()],
            "execution_source": label_source,
            "execution_files": [str(path) for path in labels],
            "execution_range": [label_start.isoformat(), label_end.isoformat()],
            "end_exclusive": end.isoformat(),
        }
        if symbol == "BTCUSDT":
            funding_root = data_root / "aux" / "funding" / symbol
            funding = _month_paths(funding_root, SCORE_START)
            _require_columns(funding, {"ts", "funding_rate"}, "BTCUSDT funding")
            _require_months(funding, SCORE_START, end, "BTCUSDT funding")
            funding_start, funding_end = _range(funding, "BTCUSDT funding")
            if funding_end < end - pd.Timedelta(hours=8):
                raise FileNotFoundError(
                    f"BTCUSDT funding ends at {funding_end}, before bar end {end}"
                )
            row.update(
                funding_files=[str(path) for path in funding],
                funding_range=[funding_start.isoformat(), funding_end.isoformat()],
            )
        rows[symbol] = row
        ends[symbol] = end
    return {
        "warmup_start": WARMUP_START.isoformat(),
        "score_start": SCORE_START.isoformat(),
        "symbols": rows,
        "end_exclusive": {symbol: stamp.isoformat() for symbol, stamp in ends.items()},
    }


def _read_detection_bars(
    data_root: Path, symbol: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    paths = _month_paths(data_root / "bars" / SOURCE[symbol] / symbol, start, end)
    parts = [pd.read_parquet(path) for path in paths]
    frame = pd.concat(parts, ignore_index=True)
    frame["ts"] = pd.to_datetime(frame.ts, utc=True)
    frame = frame[(frame.ts >= start) & (frame.ts < end)]
    frame = frame.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    frame = _feature_label_bars(_adjusted_price_view(frame))
    frame = _modelled_spread(frame, symbol)
    frame["sym"] = symbol
    return frame


def _detector_features(bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    bars = bars.copy()
    bars["ts"] = pd.to_datetime(bars.ts, utc=True).astype("datetime64[ns, UTC]")
    hourly = build_timeframe(bars, symbol, "1h")
    indicators = indicator_frame(hourly, "1h")
    completed = pd.DataFrame(
        {
            "known_at": pd.to_datetime(hourly.known_at, utc=True),
            "1h_atr14": indicators.atr14.astype("float32"),
            "1h_donchian20_position": indicators.donchian20_position.astype("float32"),
        }
    )
    active = bars.loc[_active_mask(bars, symbol)].reset_index(drop=True)
    minute = active[["ts"]].copy()
    minute["ts"] = pd.to_datetime(minute.ts, utc=True).astype("datetime64[ns, UTC]")
    minute["known_at"] = (minute.ts + pd.Timedelta(minutes=1)).astype(
        "datetime64[ns, UTC]"
    )
    return pd.merge_asof(
        minute.sort_values("known_at"),
        completed.sort_values("known_at"),
        on="known_at",
        direction="backward",
    )


def _write_events(frame: pd.DataFrame, root: Path, symbol: str) -> list[dict]:
    records = []
    if frame.empty:
        return records
    months = pd.to_datetime(frame.ts, utc=True).dt.tz_localize(None).dt.to_period("M")
    target = root / symbol
    target.mkdir(parents=True, exist_ok=True)
    for month, group in frame.groupby(months, sort=True):
        path = target / f"{month}.parquet"
        group.to_parquet(path, index=False, compression="zstd")
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "rows": len(group),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return records


def _detection_inventory(
    data_root: Path,
    warmup_start: pd.Timestamp,
    score_start: pd.Timestamp,
    end_exclusive: pd.Timestamp,
) -> dict:
    rows = {}
    ends = {}
    for symbol in SYMBOLS:
        paths = _month_paths(
            data_root / "bars" / SOURCE[symbol] / symbol,
            warmup_start,
            end_exclusive,
        )
        label = f"{symbol} detector bars"
        _require_columns(
            paths,
            {"ts", *(f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc")},
            label,
        )
        start, available_end = _range(paths, label)
        _require_months(paths, warmup_start, end_exclusive, label)
        rows[symbol] = {
            "detector_source": SOURCE[symbol],
            "detector_files": [str(path) for path in paths],
            "detector_range": [start.isoformat(), available_end.isoformat()],
            "end_exclusive": end_exclusive.isoformat(),
        }
        ends[symbol] = end_exclusive.isoformat()
    return {
        "warmup_start": warmup_start.isoformat(),
        "score_start": score_start.isoformat(),
        "symbols": rows,
        "end_exclusive": ends,
    }


def generate_events(
    data_root: Path,
    event_root: Path,
    *,
    warmup_start: pd.Timestamp = WARMUP_START,
    score_start: pd.Timestamp = SCORE_START,
    end_exclusive: pd.Timestamp | None = None,
) -> Path:
    """Recreate frozen Donchian events from minute bars for an explicit window."""
    _assert_frozen_provenance()
    if event_root.exists():
        raise FileExistsError(f"event root already exists: {event_root}")
    warmup_start = pd.Timestamp(warmup_start)
    score_start = pd.Timestamp(score_start)
    if end_exclusive is None:
        if warmup_start != WARMUP_START or score_start != SCORE_START:
            raise ValueError("a non-Final generation window requires end_exclusive")
        inventory = input_inventory(data_root)
    else:
        end_exclusive = pd.Timestamp(end_exclusive)
        if not warmup_start < score_start < end_exclusive:
            raise ValueError("generation requires warmup_start < score_start < end_exclusive")
        inventory = _detection_inventory(
            data_root, warmup_start, score_start, end_exclusive
        )
    event_root.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{event_root.name}-", dir=event_root.parent))
    files = []
    try:
        for symbol in SYMBOLS:
            end = pd.Timestamp(inventory["end_exclusive"][symbol])
            bars = _read_detection_bars(data_root, symbol, warmup_start, end)
            active = bars.loc[_active_mask(bars, symbol)].reset_index(drop=True)
            features = _detector_features(bars, symbol)
            events = donchian_atr_breakout.detect(features, pd.DataFrame(), active)
            frame = pd.DataFrame(events)
            if len(frame):
                frame["ts"] = pd.to_datetime(frame.ts, utc=True)
                frame["known_at"] = pd.to_datetime(frame.known_at, utc=True)
                atr = features.set_index("ts")["1h_atr14"]
                frame["1h_atr14"] = frame.ts.map(atr).astype(float)
                frame = frame[(frame.ts >= score_start) & (frame.ts < end)].copy()
                frame["event_key"] = _event_identity(frame)
                frame = frame.sort_values(["known_at", "event_key"]).drop_duplicates("event_key")
            files.extend(_write_events(frame, temp, symbol))
        manifest = {
            "protocol": "final_v2_donchian_events",
            "frozen_code": FROZEN_CODE,
            "wide_config_sha256": WIDE_CONFIG_SHA,
            "config_hash": _config_hash(),
            "warmup_start": warmup_start.isoformat(),
            "score_start": score_start.isoformat(),
            "inventory": inventory,
            "files": files,
        }
        (temp / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        os.replace(temp, event_root)
    except BaseException:
        # Leave a partial temporary directory for diagnosis; never overwrite it.
        raise
    return event_root / "manifest.json"


def rebuild_dev_features(data_root: Path, feature_root: Path) -> dict:
    """Call the production feature builder unchanged and persist its replay subset."""
    if feature_root.exists():
        raise FileExistsError(f"scratch feature root already exists: {feature_root}")
    boundary = pd.Timestamp("2023-01-01", tz="UTC")
    input_start = pd.Timestamp("2020-12-01", tz="UTC") - pd.Timedelta(days=370)
    columns = ["ts", "known_at", "1m_atr14", "1h_atr14", "1h_donchian20_position"]
    report = {}
    for symbol in SYMBOLS:
        paths = _month_paths(
            data_root / "bars" / SOURCE[symbol] / symbol, input_start, boundary
        )
        assert paths and all(
            pd.Timestamp(f"{path.stem}-01", tz="UTC") < boundary for path in paths
        ), f"{symbol} input path reaches 2023+"
        started = time.perf_counter()
        bars = _read_detection_bars(data_root, symbol, input_start, boundary)
        assert pd.to_datetime(bars.ts, utc=True).lt(boundary).all(), (
            f"{symbol} feature rebuild read a 2023+ bar"
        )
        timeframes = build_all_timeframes(bars, symbol)
        cache = prepare_feature_cache(bars, symbol, timeframes)
        target = feature_root / symbol
        target.mkdir(parents=True, exist_ok=True)
        rows = 0
        for month in pd.period_range("2020-12", "2022-12", freq="M"):
            left = pd.Timestamp(month.start_time, tz="UTC")
            right = pd.Timestamp(month.end_time, tz="UTC") + pd.Timedelta(nanoseconds=1)
            features = build_features(
                bars,
                symbol,
                timeframes,
                levels=None,
                auxiliary=None,
                cross_asset=None,
                output_start=left,
                output_end=right,
                cache=cache,
            )
            absent = set(columns) - set(features)
            if absent:
                raise RuntimeError(
                    f"production feature builder omitted {symbol} {month}: {sorted(absent)}"
                )
            selected = features[columns].copy()
            assert pd.to_datetime(selected.ts, utc=True).lt(boundary).all(), (
                f"{symbol} feature output reaches 2023+"
            )
            selected.to_parquet(target / f"{month}.parquet", index=False, compression="zstd")
            rows += len(selected)
        report[symbol] = {
            "rows": rows,
            "months": 25,
            "runtime_seconds": time.perf_counter() - started,
        }
        del bars, timeframes, cache, features, selected
        gc.collect()
    return report


def _replay_requirements(
    data_root: Path,
    feature_root: Path | None = None,
    level_root: Path | None = None,
) -> list[str]:
    """List missing persisted inputs without opening any 2023+ data file."""
    missing = []
    required = {"ts", "known_at", "1m_atr14", "1h_atr14", "1h_donchian20_position"}
    months = pd.period_range("2020-12", "2022-12", freq="M")
    for symbol in SYMBOLS:
        symbol_feature_root = (feature_root or data_root / "features") / symbol
        if not symbol_feature_root.exists():
            missing.append(
                f"{symbol_feature_root} directory (needs 2020-12..2022-12 monthly parquet with "
                f"{', '.join(sorted(required))})"
            )
        else:
            for month in months:
                path = symbol_feature_root / f"{month}.parquet"
                if not path.exists():
                    missing.append(str(path))
                else:
                    absent = required - set(pq.read_schema(path).names)
                    if absent:
                        missing.append(f"{path} columns {', '.join(sorted(absent))}")
        level = (level_root or data_root / "levels") / f"{symbol}.parquet"
        if not level.exists():
            missing.append(str(level))
        source = data_root / "bars" / SOURCE[symbol] / symbol
        for month in months:
            path = source / f"{month}.parquet"
            if not path.exists():
                missing.append(str(path))
    return missing


def _parity_frame(
    root: Path,
    symbol: str,
    feature_root: Path,
    *,
    reference: bool,
) -> pd.DataFrame:
    parts = []
    for path in sorted((root / symbol).glob("2022-*.parquet")):
        frame = pd.read_parquet(path)
        parts.append(frame[frame.method.eq(RULE_NAME)])
    if not parts:
        return pd.DataFrame(columns=["ts", "known_at", "side", "1h_atr14"])
    frame = pd.concat(parts, ignore_index=True)
    frame["ts"] = pd.to_datetime(frame.ts, utc=True).astype("datetime64[ns, UTC]")
    frame["known_at"] = pd.to_datetime(frame.known_at, utc=True).astype(
        "datetime64[ns, UTC]"
    )
    frame = frame.sort_values(["ts", "known_at", "side"]).drop_duplicates(
        ["ts", "known_at", "side"]
    )
    if reference:
        feature_parts = [
            pd.read_parquet(path, columns=["ts", "1h_atr14"])
            for path in sorted((feature_root / symbol).glob("2022-*.parquet"))
        ]
        features = pd.concat(feature_parts, ignore_index=True)
        features["ts"] = pd.to_datetime(features.ts, utc=True).astype(
            "datetime64[ns, UTC]"
        )
        atr = features.drop_duplicates("ts", keep="last").set_index("ts")["1h_atr14"]
        frame["1h_atr14"] = frame.ts.map(atr).astype(float)
    return frame[["ts", "known_at", "side", "1h_atr14"]].reset_index(drop=True)


def _compare_parity(left: pd.DataFrame, right: pd.DataFrame) -> dict:
    merged = left.merge(
        right,
        on=["ts", "side"],
        how="outer",
        suffixes=("_generated", "_reference"),
        indicator=True,
    )
    both = merged._merge.eq("both")
    known_mismatch = both & merged.known_at_generated.ne(merged.known_at_reference)
    atr_mismatch = both & merged["1h_atr14_generated"].ne(
        merged["1h_atr14_reference"]
    )
    return {
        "generated_events": len(left),
        "reference_events": len(right),
        "generated_only": int(merged._merge.eq("left_only").sum()),
        "reference_only": int(merged._merge.eq("right_only").sum()),
        "known_at_mismatches": int(known_mismatch.sum()),
        "atr_mismatches": int(atr_mismatch.sum()),
        "side_or_ts_mismatches": int((~both).sum()),
        "exact": bool(
            len(left) == len(right)
            and not (~both).any()
            and not known_mismatch.any()
            and not atr_mismatch.any()
        ),
    }


def run_dev_parity(data_root: Path, parity_root: Path) -> Path:
    """Generate 2022 events and compare with the original persisted-feature replay."""
    report = parity_root / "parity_report.json"
    if parity_root.exists():
        raise FileExistsError(f"parity root already exists: {parity_root}")
    parity_root.mkdir(parents=True)
    generated_root = parity_root / "generated"
    started = time.perf_counter()
    generate_events(
        data_root,
        generated_root,
        warmup_start=pd.Timestamp("2021-01-01", tz="UTC"),
        score_start=pd.Timestamp("2022-01-01", tz="UTC"),
        end_exclusive=pd.Timestamp("2023-01-01", tz="UTC"),
    )
    generated_seconds = time.perf_counter() - started
    generated = {
        symbol: _parity_frame(generated_root, symbol, parity_root, reference=False)
        for symbol in SYMBOLS
    }
    feature_root = parity_root / "rebuilt_features"
    rebuild_started = time.perf_counter()
    feature_build = rebuild_dev_features(data_root, feature_root)
    feature_build_seconds = time.perf_counter() - rebuild_started
    level_root = parity_root / "empty_levels_for_donchian"
    level_root.mkdir()
    for symbol in SYMBOLS:
        pd.DataFrame(
            {"known_at": pd.Series(dtype="datetime64[ns, UTC]")}
        ).to_parquet(level_root / f"{symbol}.parquet", index=False)
    missing = _replay_requirements(data_root, feature_root, level_root)
    payload = {
        "window": "2022-01-01 inclusive / 2023-01-01 exclusive",
        "warmup_start": "2021-01-01T00:00:00+00:00",
        "hard_end_exclusive": "2023-01-01T00:00:00+00:00",
        "generated_runtime_seconds": generated_seconds,
        "feature_rebuild_runtime_seconds": feature_build_seconds,
        "feature_rebuild": feature_build,
        "symbols": {
            symbol: {"generated_events": len(generated[symbol])} for symbol in SYMBOLS
        },
    }
    if missing:
        payload.update(
            status="BLOCKED_MISSING_REPLAY_INPUTS",
            missing_replay_inputs=missing,
            replay_runtime_seconds=None,
            mismatches=None,
        )
    else:
        replay_root = parity_root / "replay_events_only"
        replay_started = time.perf_counter()
        for symbol in SYMBOLS:
            replay_events_only(
                symbol,
                2021,
                2022,
                replay_root,
                data_root,
                method_names={RULE_NAME},
                hard_end_exclusive=pd.Timestamp("2023-01-01", tz="UTC"),
                feature_root=feature_root,
                level_root=level_root,
            )
        replay_seconds = time.perf_counter() - replay_started
        comparisons = {}
        for symbol in SYMBOLS:
            reference = _parity_frame(
                replay_root, symbol, feature_root, reference=True
            )
            comparisons[symbol] = _compare_parity(generated[symbol], reference)
            payload["symbols"][symbol].update(comparisons[symbol])
        payload.update(
            status="PASS" if all(item["exact"] for item in comparisons.values()) else "FAIL",
            replay_runtime_seconds=replay_seconds,
            mismatches=comparisons,
        )
    payload["total_runtime_seconds"] = time.perf_counter() - started
    report.write_text(json.dumps(_finite(payload), indent=2, allow_nan=False) + "\n")
    return report


def _load_manifest(event_root: Path) -> dict:
    path = event_root / "manifest.json"
    manifest = json.loads(path.read_text())
    expected = {
        "protocol": "final_v2_donchian_events",
        "frozen_code": FROZEN_CODE,
        "wide_config_sha256": WIDE_CONFIG_SHA,
        "config_hash": _config_hash(),
        "warmup_start": WARMUP_START.isoformat(),
        "score_start": SCORE_START.isoformat(),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RuntimeError(f"event manifest {key} mismatch")
    for item in manifest.get("files", []):
        source = event_root / item["path"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError(f"event file changed: {source}")
    return manifest


def _load_events(event_root: Path, symbol: str, end: pd.Timestamp) -> pd.DataFrame:
    parts = []
    for path in sorted((event_root / symbol).glob("*.parquet")):
        frame = pd.read_parquet(path)
        if len(frame):
            parts.append(frame[frame.method.eq(RULE_NAME)])
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True)
    frame["ts"] = pd.to_datetime(frame.ts, utc=True)
    frame["known_at"] = pd.to_datetime(frame.known_at, utc=True)
    frame = frame[(frame.ts >= SCORE_START) & (frame.ts < end)].copy()
    frame["event_key"] = _event_identity(frame)
    return frame.sort_values(["known_at", "event_key"]).drop_duplicates("event_key").reset_index(drop=True)


def _label_events(
    events: pd.DataFrame,
    symbol: str,
    data_root: Path,
    end: pd.Timestamp,
    *,
    opposite: bool = False,
) -> tuple[pd.DataFrame, int]:
    if events.empty:
        return pd.DataFrame(), 0
    source = events.copy()
    if opposite:
        source["side"] = -source.side.astype(int)
    config = {"sl_atr": [RULE["sl_atr"]], "tp_r": [RULE["tp_r"]], "max_hold_trading_days": 1}
    parts = []
    dropped = 0
    months = source.ts.dt.tz_localize(None).dt.to_period("M")
    for month, group in source.groupby(months, sort=True):
        left = pd.Timestamp(month.start_time, tz="UTC")
        month_end = pd.Timestamp(month.end_time, tz="UTC") + pd.Timedelta(nanoseconds=1)
        read_right = min(month_end + pd.Timedelta(days=8), end)
        bars = _bars(data_root, symbol, left, read_right)
        positions = pd.Series(range(len(bars)), index=pd.to_datetime(bars.ts, utc=True))
        event_positions = group.ts.map(positions)
        missing = event_positions.isna()
        if missing.any():
            raise RuntimeError(
                f"{symbol} executable bars missing {int(missing.sum())} event minutes in {month}"
            )
        late = event_positions.astype(int).add(2).ge(len(bars))
        dropped += int(late.sum())
        group = group.loc[~late]
        if group.empty:
            continue
        atr_map = pd.Series(group["1h_atr14"].to_numpy(float), index=group.ts)
        result = _event_jobs(group, bars, atr_map, config, symbol)
        if result.empty:
            raise RuntimeError(f"{symbol} label kernel returned no rows for eligible events in {month}")
        if len(result) != len(group):
            raise RuntimeError(f"{symbol} label kernel skipped eligible events in {month}")
        if symbol == "BTCUSDT":
            result = apply_perp_costs(result, bars, _funding(data_root, symbol, left, read_right))
        else:
            result["cost_R"] = result.gross_R - result.net_R
            result["spread_R"] = result.cost_R
            result["venue"] = "dukascopy_cfd"
        resolved = _resolved_before_end(result, end)
        dropped += len(group) - int(resolved.sum())
        result = result.loc[resolved].copy()
        if len(result):
            result["label_end_ts"] = pd.to_datetime(result.exit_ts, utc=True)
            parts.append(result)
    if not parts:
        return pd.DataFrame(), dropped
    return pd.concat(parts, ignore_index=True), dropped


def _resolved_before_end(result: pd.DataFrame, end: pd.Timestamp) -> pd.Series:
    """A hit is resolved, or its real time-exit bar exists before local data end."""
    deadline = pd.to_datetime(result.deadline_ts, utc=True)
    exit_ts = pd.to_datetime(result.exit_ts, utc=True, errors="coerce")
    time_exit = result.outcome.eq("time") & exit_ts.ge(deadline) & exit_ts.lt(end)
    return result.outcome.isin(["tp", "sl"]) | time_exit


def _verdict(net_avg_r: float | None) -> str:
    return "KEEP" if net_avg_r is not None and net_avg_r > 0 else "DROP"


def _result(data_root: Path, event_root: Path, manifest: dict) -> tuple[dict, pd.DataFrame]:
    normal_parts = []
    opposite_parts = []
    dropped = 0
    event_count = 0
    for symbol in SYMBOLS:
        end = pd.Timestamp(manifest["inventory"]["end_exclusive"][symbol])
        events = _load_events(event_root, symbol, end)
        event_count += len(events)
        normal, unresolved = _label_events(events, symbol, data_root, end)
        reverse, _ = _label_events(events, symbol, data_root, end, opposite=True)
        normal_parts.append(normal)
        opposite_parts.append(reverse)
        dropped += unresolved
    candidates = pd.concat(normal_parts, ignore_index=True) if normal_parts else pd.DataFrame()
    reverse = pd.concat(opposite_parts, ignore_index=True) if opposite_parts else pd.DataFrame()
    signals = gate_open_signals(candidates)
    percentile, matched = _random_percentile(signals, reverse, 200)
    pooled = metrics(signals, None)
    pooled.update(
        random_direction_percentile=percentile,
        random_direction_matched_signals=matched,
        random_direction_seeds=200,
        events=event_count,
        dropped_at_end=dropped,
    )
    pooled["verdict"] = _verdict(pooled.get("net_avg_R"))
    pooled["per_market"] = {
        symbol: metrics(signals[signals.sym.eq(symbol)], None) for symbol in SYMBOLS
    }
    final_year = max(pd.Timestamp(value).year for value in manifest["inventory"]["end_exclusive"].values())
    entry_year = pd.to_datetime(signals.entry_ts, utc=True).dt.year if len(signals) else pd.Series(dtype=int)
    pooled["per_year"] = {
        str(year): metrics(signals[entry_year.eq(year)], None)
        for year in range(SCORE_START.year, final_year + 1)
    }
    return _finite(pooled), signals


def _fmt(value: object) -> str:
    return "NA" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)


def markdown(result: dict) -> str:
    lines = [
        "# Final v2 — intraday Donchian ATR breakout",
        "",
        f"**{result['verdict']}** — the frozen verdict uses only pooled net R per trade > 0.",
        "",
        "Decisions begin at 2025-01-01 00:00 UTC. Detector state is warmed on 2024 minute bars. "
        "Trades still open at each market's local data end are dropped, not censored.",
        "",
        "| Trades | Hit rate | Net R/trade | t | Profit factor | Random percentile | Dropped at end |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {result['n']} | {_fmt(result.get('hit_rate'))} | {_fmt(result.get('net_avg_R'))} | "
        f"{_fmt(result.get('t_stat'))} | {_fmt(result.get('profit_factor'))} | "
        f"{_fmt(result.get('random_direction_percentile'))} | {result['dropped_at_end']} |",
        "",
        "Random-direction percentile uses exactly 200 deterministic seeds and the same entries and geometry.",
    ]
    for title, key in (("Per market", "per_market"), ("Per year", "per_year")):
        lines += [
            "",
            f"## {title}",
            "",
            "| Scope | Trades | Hit rate | Net R/trade | t | Profit factor |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for scope, item in result[key].items():
            lines.append(
                f"| {scope} | {item['n']} | {_fmt(item.get('hit_rate'))} | "
                f"{_fmt(item.get('net_avg_R'))} | {_fmt(item.get('t_stat'))} | "
                f"{_fmt(item.get('profit_factor'))} |"
            )
    return "\n".join(lines) + "\n"


def _ensure_once(output: Path, ledger: Path) -> None:
    if (output / "donchian.md").exists() or (output / "donchian.json").exists():
        raise FileExistsError("Final-v2 Donchian output already exists; refusing to rerun")
    if any(row["run_id"] == RUN_ID for row in read_trials(ledger)):
        raise RuntimeError("Final-v2 Donchian trial already exists; refusing to rerun")


def _append_trial(ledger: Path, result: dict, manifest: dict) -> None:
    row = dict(
        zip(
            FIELDS,
            (
                RUN_ID,
                pd.Timestamp.now(tz="UTC").date().isoformat(),
                _config_hash(),
                RULE_NAME,
                json.dumps(
                    {
                        "protocol": "final_v2",
                        "frozen_code": FROZEN_CODE,
                        "sl_atr": RULE["sl_atr"],
                        "tp_r": RULE["tp_r"],
                        "max_hold_trading_days": 1,
                        "random_direction_seeds": 200,
                        "symbols": SYMBOLS,
                    },
                    sort_keys=True,
                ),
                "2025-01-01 / local data end",
                "final",
                json.dumps(result, sort_keys=True, allow_nan=False),
                f"{result['verdict']}; dropped_at_end={result['dropped_at_end']}; "
                f"event_manifest={manifest['config_hash']}",
            ),
        )
    )
    ledger.parent.mkdir(parents=True, exist_ok=True)
    new = not ledger.exists()
    with ledger.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        writer.writerow(row)


def run(data_root: Path, event_root: Path, output: Path, ledger: Path) -> dict:
    _ensure_once(output, ledger)
    _assert_frozen_provenance()
    manifest = _load_manifest(event_root)
    if input_inventory(data_root) != manifest["inventory"]:
        raise RuntimeError("input file coverage changed after event generation")
    result, _ = _result(data_root, event_root, manifest)
    payload = {
        "protocol": "docs/final_check_v2.md part B",
        "score_start": SCORE_START.isoformat(),
        "frozen_code": FROZEN_CODE,
        "wide_config_sha256": WIDE_CONFIG_SHA,
        "settings": RULE,
        "input_end_exclusive": manifest["inventory"]["end_exclusive"],
        "result": result,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "donchian.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    (output / "donchian.md").write_text(markdown(result))
    _append_trial(ledger, result, manifest)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--event-root", type=Path, default=Path("data/final_v2_donchian_events"))
    parser.add_argument("--output", type=Path, default=Path("reports/research/final_v2"))
    parser.add_argument("--ledger", type=Path, default=Path("reports/trials.csv"))
    parser.add_argument("--parity-root", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check-inputs", action="store_true")
    action.add_argument("--generate-events", action="store_true")
    action.add_argument("--run-final-once", action="store_true")
    action.add_argument("--parity-dev-2022", action="store_true")
    args = parser.parse_args()
    if args.check_inputs:
        print(json.dumps(input_inventory(args.data_root), indent=2))
    elif args.generate_events:
        print(generate_events(args.data_root, args.event_root))
    elif args.parity_dev_2022:
        root = args.parity_root or args.data_root / "tmp_parity" / "donchian_2022"
        print(run_dev_parity(args.data_root, root))
    else:
        print(run(args.data_root, args.event_root, args.output, args.ledger)["result"]["verdict"])


if __name__ == "__main__":
    main()
