"""Stream Binance aggTrade archives into minute-flow and spot 1-second bars.

Only archives with a verified ``.zip.sha256`` sidecar are considered complete.
Input CSV members are read in Arrow blocks; raw trades are never materialized as
a whole-month table. Invoke with ``python -m msd.data.aggtrades_flow``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
from pathlib import Path
import re
import resource
import shutil
import sys
import time
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .archive_download import MIN_FREE_BYTES

RAW_ROOT = Path("data/raw/binance/aggTrades")
MINUTE_ROOT = Path("data/bars/binance_flow")
SECOND_ROOT = Path("data/bars/binance_1s/spot")
MISMATCH_LOG = Path("data/logs/aggtrades_flow_mismatch.csv")
MAX_RSS_BYTES = int(1.5 * 1024**3)
BLOCK_BYTES = 8 * 1024 * 1024
REQUIRED_COLUMNS = (
    "agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
    "transact_time", "is_buyer_maker",
)
OPTIONAL_COLUMNS = ("is_best_match",)


def _sidecar_sha256(archive: Path) -> str | None:
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    if not sidecar.is_file():
        return None
    text = sidecar.read_text().strip()
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not match:
        raise ValueError(f"Invalid checksum sidecar: {sidecar}")
    expected = match.group(1).lower()
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch for {archive}: expected {expected}, got {actual}")
    return actual


def _archive_info(path: Path) -> tuple[str, str, str]:
    match = re.fullmatch(r"(?P<symbol>[A-Z0-9]+)-aggTrades-(?P<year>\d{4})-(?P<month>\d{2})\.zip", path.name)
    if not match:
        raise ValueError(f"Unexpected aggTrades archive name: {path.name}")
    market = path.parent.parent.name
    if market not in {"spot", "um"}:
        raise ValueError(f"Unknown aggTrades market directory: {path}")
    return market, match.group("symbol"), f"{match.group('year')}-{match.group('month')}"


def _column_name(raw: str) -> str:
    name = raw.strip().lstrip("\ufeff").lower()
    aliases = {"transacttime": "transact_time", "is_buyermaker": "is_buyer_maker",
               "aggtradeid": "agg_trade_id", "firsttradeid": "first_trade_id",
               "lasttradeid": "last_trade_id", "qty": "quantity"}
    return aliases.get(name, name)


def _csv_reader(member, first_line: bytes):
    """Create a streaming Arrow CSV reader for header and headerless variants."""
    text = first_line.decode("utf-8-sig", errors="replace").strip()
    fields = [_column_name(value) for value in next(csv.reader([text]))]
    header = "agg_trade_id" in fields or "transact_time" in fields
    if header:
        names = fields
        skip_rows = 1
    else:
        names = list(REQUIRED_COLUMNS)
        if len(fields) == 8:
            names += list(OPTIONAL_COLUMNS)
        if len(fields) != len(names):
            raise ValueError(f"Unexpected headerless aggTrades field count: {len(fields)}")
        skip_rows = 0
    missing = set(REQUIRED_COLUMNS) - set(names)
    if missing:
        raise ValueError(f"aggTrades CSV is missing required columns: {sorted(missing)}")
    types = {"agg_trade_id": pa.int64(), "price": pa.float64(), "quantity": pa.float64(),
             "first_trade_id": pa.int64(), "last_trade_id": pa.int64(),
             "transact_time": pa.int64(), "is_buyer_maker": pa.bool_()}
    types = {name: kind for name, kind in types.items() if name in names}
    return pacsv.open_csv(
        member,
        read_options=pacsv.ReadOptions(skip_rows=skip_rows, column_names=names,
                                       block_size=BLOCK_BYTES, use_threads=False),
        parse_options=pacsv.ParseOptions(delimiter=","),
        convert_options=pacsv.ConvertOptions(column_types=types, strings_can_be_null=True),
    )


def _time_to_ms(values: np.ndarray) -> tuple[np.ndarray, str]:
    if not len(values):
        return values.astype(np.int64), "ms"
    magnitude = int(values[0])
    if magnitude >= 100_000_000_000_000:
        # Binance spot files use microseconds from 2025 onward.
        if magnitude >= 100_000_000_000_000_000:
            raise ValueError(f"Unsupported aggTrade timestamp magnitude: {magnitude}")
        return values.astype(np.int64) // 1000, "us"
    if magnitude < 1_000_000_000_000:
        raise ValueError(f"Unsupported aggTrade timestamp magnitude: {magnitude}")
    return values.astype(np.int64), "ms"


def _aggregate_block(table: pa.Table, time_unit: str | None = None):
    frame = table.select(["agg_trade_id", "price", "quantity", "transact_time", "is_buyer_maker"]).to_pandas()
    if frame.empty:
        return None, None, time_unit
    raw_time = frame.transact_time.to_numpy(dtype=np.int64, copy=False)
    times_ms, detected_unit = _time_to_ms(raw_time)
    if time_unit is not None and detected_unit != time_unit:
        raise ValueError(f"Timestamp unit changed within file: {time_unit} -> {detected_unit}")
    time_unit = detected_unit
    price = frame.price.to_numpy(dtype=np.float64, copy=False)
    qty = frame.quantity.to_numpy(dtype=np.float64, copy=False)
    ids = frame.agg_trade_id.to_numpy(dtype=np.int64, copy=False)
    maker = frame.is_buyer_maker.to_numpy(dtype=bool, copy=False)
    # Binance marks buyer_is_maker=True when the taker was a seller.
    buy = ~maker
    notional = price * qty
    minute_key = times_ms // 60_000
    second_key = times_ms // 1_000
    base = pd.DataFrame({"key": minute_key, "ms": times_ms, "id": ids,
                         "price": price, "qty": qty, "buy": buy,
                         "notional": notional,
                         "buy_vol": np.where(buy, qty, 0.0),
                         "sell_vol": np.where(~buy, qty, 0.0),
                         "buy_n": buy.astype(np.int64), "sell_n": (~buy).astype(np.int64),
                         "large100k_buy": np.where(buy & (notional >= 100_000), notional, 0.0),
                         "large100k_sell": np.where(~buy & (notional >= 100_000), notional, 0.0),
                         "large1m_buy": np.where(buy & (notional >= 1_000_000), notional, 0.0),
                         "large1m_sell": np.where(~buy & (notional >= 1_000_000), notional, 0.0)})
    minute_group = base.groupby("key", sort=False, observed=True)
    minute = minute_group.agg(
        o=("price", "first"), h=("price", "max"), l=("price", "min"), c=("price", "last"),
        buy_vol=("buy_vol", "sum"), sell_vol=("sell_vol", "sum"),
        buy_n=("buy_n", "sum"), sell_n=("sell_n", "sum"),
        _qty=("qty", "sum"), _notional=("notional", "sum"),
        max_trade_qty=("qty", "max"),
        large100k_buy_notional=("large100k_buy", "sum"),
        large100k_sell_notional=("large100k_sell", "sum"),
        large1m_buy_notional=("large1m_buy", "sum"),
        large1m_sell_notional=("large1m_sell", "sum"),
        first_agg_id=("id", "first"), last_agg_id=("id", "last"),
        _n=("id", "size"),
    ).reset_index(names="minute")
    hi_idx = minute_group.price.idxmax().to_numpy(dtype=np.int64)
    lo_idx = minute_group.price.idxmin().to_numpy(dtype=np.int64)
    minute["high_ms"] = (times_ms[hi_idx] - minute.minute.to_numpy(dtype=np.int64) * 60_000).astype(np.int32)
    minute["low_ms"] = (times_ms[lo_idx] - minute.minute.to_numpy(dtype=np.int64) * 60_000).astype(np.int32)

    base["second"] = second_key
    second_group = base.groupby("second", sort=False, observed=True)
    second = second_group.agg(o=("price", "first"), h=("price", "max"),
                              l=("price", "min"), c=("price", "last"),
                              volume=("qty", "sum"), buy_vol=("buy_vol", "sum"),
                              n=("id", "size")).reset_index()
    return minute, second, time_unit


def _combine_partials(parts: list[pd.DataFrame], *, seconds: bool) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True)
    key = "second" if seconds else "minute"
    # Blocks and members are chronological. Stable sorting also guarantees
    # first/last prices and equal-extreme offsets are deterministic.
    frame = frame.sort_values(key, kind="stable")
    group = frame.groupby(key, sort=True, observed=True)
    if seconds:
        result = group.agg(o=("o", "first"), h=("h", "max"), l=("l", "min"),
                           c=("c", "last"), volume=("volume", "sum"),
                           buy_vol=("buy_vol", "sum"), n=("n", "sum")).reset_index()
        result["ts"] = pd.to_datetime(result.second.astype(np.int64) * 1000, unit="ms", utc=True).astype("datetime64[ns, UTC]")
        result["known_at"] = (result.ts + pd.Timedelta(seconds=1)).astype("datetime64[ns, UTC]")
        return result[["ts", "known_at", "o", "h", "l", "c", "volume", "buy_vol", "n"]]
    result = group.agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
                       buy_vol=("buy_vol", "sum"), sell_vol=("sell_vol", "sum"),
                       buy_n=("buy_n", "sum"), sell_n=("sell_n", "sum"),
                       _qty=("_qty", "sum"), _notional=("_notional", "sum"),
                       max_trade_qty=("max_trade_qty", "max"),
                       large100k_buy_notional=("large100k_buy_notional", "sum"),
                       large100k_sell_notional=("large100k_sell_notional", "sum"),
                       large1m_buy_notional=("large1m_buy_notional", "sum"),
                       large1m_sell_notional=("large1m_sell_notional", "sum"),
                       first_agg_id=("first_agg_id", "first"), last_agg_id=("last_agg_id", "last"),
                       _n=("_n", "sum")).reset_index()
    high_rows=group.h.idxmax().to_numpy(dtype=np.int64)
    low_rows=group.l.idxmin().to_numpy(dtype=np.int64)
    result["high_ms"]=frame.loc[high_rows,"high_ms"].to_numpy(dtype=np.int32)
    result["low_ms"]=frame.loc[low_rows,"low_ms"].to_numpy(dtype=np.int32)
    # The first/last ids of successive chunks may have gaps. Count missing ids
    # within each minute from the complete id span, not per Arrow block.
    result["id_gaps"] = (result.last_agg_id - result.first_agg_id + 1 - result._n).clip(lower=0).astype(np.int64)
    result["delta"] = result.buy_vol - result.sell_vol
    result["vwap"] = np.divide(result._notional, result._qty,
                               out=np.full(len(result), np.nan), where=result._qty.to_numpy() != 0)
    result["ts"] = pd.to_datetime(result.minute.astype(np.int64) * 60_000, unit="ms", utc=True).astype("datetime64[ns, UTC]")
    result["known_at"] = (result.ts + pd.Timedelta(minutes=1)).astype("datetime64[ns, UTC]")
    return result[["ts", "known_at", "o", "h", "l", "c", "buy_vol", "sell_vol", "delta",
                   "buy_n", "sell_n", "vwap", "max_trade_qty", "large100k_buy_notional",
                   "large100k_sell_notional", "large1m_buy_notional", "large1m_sell_notional",
                   "first_agg_id", "last_agg_id", "id_gaps", "high_ms", "low_ms"]]


def _stream_archive(archive: Path, *, second_output_path: Path | None = None,
                    source_sha: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame | None, str]:
    minute_parts: list[pd.DataFrame] = []
    second_parts: list[pd.DataFrame] = []
    second_sink = (_SecondParquetSink(second_output_path, source_sha or "")
                   if second_output_path is not None else None)
    time_unit = None
    last_id, duplicates = -1, 0
    with ZipFile(archive) as zf:
        members = [info for info in zf.infolist() if info.filename.lower().endswith(".csv")]
        # Some Binance archives (e.g. spot 2021-12) carry the same CSV twice
        # under two paths; identical size and CRC means one physical copy.
        if len({(info.file_size, info.CRC) for info in members}) == 1:
            members = members[:1]
        elif len(members) > 1:
            # Differing copies (e.g. spot ETH 2018-01: the top-level CSV repeats
            # every trade 4x). Read the top-level member; id de-duplication
            # below removes repeats and kline validation checks the result.
            top = [info for info in members if "/" not in info.filename]
            if len(top) == 1:
                print(f"WARN {archive.name}: {len(members)} differing CSV members; using {top[0].filename}", flush=True)
                members = top
        if len(members) != 1:
            raise ValueError(f"Expected one CSV member in {archive}, found {len(members)}")
        member_info = members[0]
        with zf.open(member_info) as sniff:
            first_line = sniff.readline()
        with zf.open(member_info) as member:
            reader = _csv_reader(member, first_line)
            for batch in reader:
                # aggTrade ids are strictly increasing; a repeated id is a
                # duplicated source row (seen in um 2022-09, spot 2026-02).
                ids = batch.column("agg_trade_id").to_numpy(zero_copy_only=False)
                if len(ids):
                    prior = np.maximum.accumulate(np.r_[last_id, ids[:-1]])
                    keep = ids > prior
                    last_id = max(last_id, int(ids.max()))
                    if not keep.all():
                        duplicates += int((~keep).sum())
                        batch = batch.filter(pa.array(keep))
                minute, second, time_unit = _aggregate_block(batch, time_unit)
                if minute is not None:
                    minute_parts.append(minute)
                    if archive.parent.parent.name == "spot":
                        if second_sink is None:
                            second_parts.append(second)
                        else:
                            second_sink.add(second)
                del minute, second, batch
    if duplicates:
        print(f"WARN {archive.name}: dropped {duplicates} duplicate aggTrade rows", flush=True)
    minute = _combine_partials(minute_parts, seconds=False)
    if not minute.empty and ((minute.last_agg_id - minute.first_agg_id + 1) < minute.buy_n + minute.sell_n).any():
        raise ValueError(f"More trades than aggTrade ids in a minute after de-duplication: {archive}")
    if second_sink is not None:
        second_sink.close()
        second = None
    else:
        second = _combine_partials(second_parts, seconds=True) if second_parts else None
    if minute.empty:
        raise ValueError(f"No trade rows parsed from {archive}")
    return minute, second, time_unit or "ms"


def _is_complete(path: Path, source_sha: str) -> bool:
    if not path.is_file():
        return False
    try:
        metadata = pq.read_schema(path).metadata or {}
    except Exception:
        return False
    return metadata.get(b"msd_complete") == b"1" and metadata.get(b"source_sha256", b"").decode() == source_sha


def _um_audit_complete(path: Path, source_sha: str) -> bool:
    if not _is_complete(path, source_sha):
        return False
    try:
        return {"uncovered_volume", "um_kline_agg_mismatch"}.issubset(pq.read_schema(path).names)
    except Exception:
        return False


def _atomic_parquet(frame: pd.DataFrame, path: Path, source_sha: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata.update({b"msd_complete": b"1", b"source_sha256": source_sha.encode("ascii")})
    pq.write_table(table.replace_schema_metadata(metadata), temporary, compression="zstd")
    os.replace(temporary, path)


def _second_output_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result=frame.copy()
    for column in ("o","h","l","c","volume","buy_vol"):
        result[column]=result[column].to_numpy(dtype=np.float64)
    result["n"]=result.n.to_numpy(dtype=np.int64)
    result["ts"]=pd.to_datetime(result.second.astype(np.int64)*1000,unit="ms",utc=True).astype("datetime64[ns, UTC]")
    result["known_at"]=(result.ts+pd.Timedelta(seconds=1)).astype("datetime64[ns, UTC]")
    return result[["ts","known_at","o","h","l","c","volume","buy_vol","n"]]


class _SecondParquetSink:
    """Stream completed seconds into Parquet, retaining one boundary row."""
    def __init__(self,path:Path,source_sha:str):
        self.path=path;self.source_sha=source_sha;self.writer=None;self.pending=None;self.rows=0

    def _write(self,frame:pd.DataFrame):
        if frame is None or frame.empty:return
        table=pa.Table.from_pandas(_second_output_frame(frame),preserve_index=False)
        if self.writer is None:
            metadata=dict(table.schema.metadata or {})
            metadata.update({b"msd_complete":b"1",b"source_sha256":self.source_sha.encode("ascii")})
            table=table.replace_schema_metadata(metadata)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            self.writer=pq.ParquetWriter(self.path,table.schema,compression="zstd")
        self.writer.write_table(table,row_group_size=max(1,len(frame)))
        self.rows+=len(frame)

    def add(self,frame:pd.DataFrame):
        if frame is None or frame.empty:return
        frame=frame.reset_index(drop=True)
        if self.pending is not None:
            pending_key=int(self.pending.second.iloc[0]);first_key=int(frame.second.iloc[0])
            if first_key<pending_key:raise ValueError("1-second aggregate blocks are not chronological")
            if first_key==pending_key:
                left=self.pending.iloc[0];right=frame.iloc[0]
                self.pending=pd.DataFrame([{"second":pending_key,"o":left.o,"h":max(left.h,right.h),
                    "l":min(left.l,right.l),"c":right.c,"volume":left.volume+right.volume,
                    "buy_vol":left.buy_vol+right.buy_vol,"n":left.n+right.n}])
                frame=frame.iloc[1:].reset_index(drop=True)
                if not frame.empty:
                    self._write(self.pending);self.pending=None
            else:
                self._write(self.pending);self.pending=None
        if frame.empty:return
        if len(frame)>1:self._write(frame.iloc[:-1])
        self.pending=frame.iloc[[-1]].copy()

    def close(self):
        if self.pending is not None:self._write(self.pending)
        if self.writer is None:raise ValueError("Spot archive produced no 1-second rows")
        self.writer.close();self.writer=None


def _kline_path(market: str, symbol: str, month: str) -> Path:
    root = "binance_spot" if market == "spot" else "binance_um"
    return Path("data/bars") / root / symbol / f"{month}.parquet"


def validate_against_klines(minute: pd.DataFrame, market: str, symbol: str, month: str) -> dict:
    path = _kline_path(market, symbol, month)
    if not path.is_file():
        return {"match_rate": float("nan"), "compared": 0, "mismatches": []}
    klines = pd.read_parquet(path, columns=["ts", "bid_o", "bid_h", "bid_l", "bid_c", "volume"])
    klines["ts"] = pd.to_datetime(klines.ts, utc=True)
    compared = minute.merge(klines, on="ts", how="outer", indicator=True, suffixes=("_agg", "_kline"))
    common = compared._merge.eq("both").to_numpy()
    close = np.ones(len(compared), dtype=bool)
    for flow_col, kline_col in (("o", "bid_o"), ("h", "bid_h"), ("l", "bid_l"), ("c", "bid_c"), ("_qty", "volume")):
        if flow_col == "_qty":
            # Reconstruct total traded volume from taker-side quantities.
            left = compared.buy_vol + compared.sell_vol
        else:
            left = compared[flow_col]
        right = compared[kline_col]
        x, y = left.to_numpy(float), right.to_numpy(float)
        tol = np.maximum(np.maximum(np.abs(x), np.abs(y)) * 1e-8, 1e-10)
        close &= np.isfinite(x) & np.isfinite(y) & (np.abs(x-y) <= tol)
    matched = common & close
    mismatch_rows = compared.loc[~matched, ["ts", "_merge", "o", "h", "l", "c", "buy_vol", "sell_vol",
                                              "bid_o", "bid_h", "bid_l", "bid_c", "volume"]].copy()
    return {"match_rate": float(matched.sum()/max(1,len(compared))),
            "compared": int(len(compared)), "mismatches": mismatch_rows}


def add_um_kline_audit(minute: pd.DataFrame, symbol: str, month: str) -> pd.DataFrame:
    """Attach the per-minute UM kline volume residual without changing agg prices."""
    result = minute.copy()
    path = _kline_path("um", symbol, month)
    if not path.is_file():
        result["uncovered_volume"] = np.nan
        result["um_kline_agg_mismatch"] = pd.array([pd.NA] * len(result), dtype="boolean")
        return result

    klines = pd.read_parquet(path, columns=["ts", "bid_o", "bid_h", "bid_l", "bid_c", "volume"])
    klines["ts"] = pd.to_datetime(klines.ts, utc=True)
    audit = result[["ts", "o", "h", "l", "c", "buy_vol", "sell_vol"]].merge(
        klines, on="ts", how="left", indicator=True, sort=False,
    )
    residual = audit.volume - audit.buy_vol - audit.sell_vol
    same = audit._merge.eq("both").to_numpy()
    mismatch = ~same
    for flow_col, kline_col in (("o", "bid_o"), ("h", "bid_h"), ("l", "bid_l"), ("c", "bid_c")):
        x = audit[flow_col].to_numpy(float)
        y = audit[kline_col].to_numpy(float)
        tolerance = np.maximum(np.maximum(np.abs(x), np.abs(y)) * 1e-8, 1e-10)
        mismatch |= same & (~np.isfinite(x) | ~np.isfinite(y) | (np.abs(x-y) > tolerance))
    volume = audit.volume.to_numpy(float)
    delta = residual.to_numpy(float)
    volume_tolerance = np.maximum(np.abs(volume) * 1e-8, 1e-10)
    mismatch |= same & (~np.isfinite(delta) | (np.abs(delta) > volume_tolerance))
    result["uncovered_volume"] = residual.to_numpy(float)
    result["um_kline_agg_mismatch"] = pd.array(mismatch, dtype="boolean")
    return result


def _append_mismatches(mismatches: pd.DataFrame, market: str, symbol: str, month: str) -> None:
    if mismatches.empty:
        return
    MISMATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    frame = mismatches.copy()
    frame.insert(0, "month", month); frame.insert(0, "symbol", symbol); frame.insert(0, "market", market)
    frame.to_csv(MISMATCH_LOG, mode="a", header=not MISMATCH_LOG.exists(), index=False)


def process_archive(archive: Path, *, validate: bool = True, force: bool = False) -> dict | None:
    archive = Path(archive)
    info = _archive_info(archive)
    market, symbol, month = info
    source_sha = _sidecar_sha256(archive)
    if source_sha is None:
        print(f"SKIP incomplete archive {archive}", flush=True)
        return None
    minute_path = MINUTE_ROOT / market / symbol / f"{month}.parquet"
    second_path = SECOND_ROOT / symbol / f"{month}.parquet"
    outputs_complete = (_um_audit_complete(minute_path, source_sha) if market == "um"
                        else _is_complete(minute_path, source_sha))
    if market == "spot":
        outputs_complete &= _is_complete(second_path, source_sha)
    if outputs_complete and not force:
        print(f"SKIP complete {market} {symbol} {month} rows={pq.read_metadata(minute_path).num_rows}", flush=True)
        return {"market": market, "symbol": symbol, "month": month, "skipped": True}
    free = shutil.disk_usage(".").free
    if free < MIN_FREE_BYTES:
        raise OSError(f"Disk guard: {free/1024**3:.1f} GiB free; minimum is {MIN_FREE_BYTES/1024**3:.1f} GiB")
    started = time.perf_counter()
    second_temporary=(second_path.with_name(second_path.name+f".{os.getpid()}.tmp") if market=="spot" else None)
    minute, second, unit = _stream_archive(archive,second_output_path=second_temporary,source_sha=source_sha)
    if market == "um":
        minute = add_um_kline_audit(minute, symbol, month)
    if validate:
        report = validate_against_klines(minute, market, symbol, month)
        print(f"VALIDATE {market} {symbol} {month} unit={unit} compared={report['compared']} "
              f"match_rate={report['match_rate']:.6f} mismatches={len(report['mismatches'])}", flush=True)
        _append_mismatches(report["mismatches"], market, symbol, month)
    _atomic_parquet(minute, minute_path, source_sha)
    if market == "spot":
        if second is not None:
            _atomic_parquet(second, second_path, source_sha)
        elif second_temporary is not None and second_temporary.is_file():
            os.replace(second_temporary,second_path)
        else:
            raise ValueError(f"Spot archive did not produce 1-second bars: {archive}")
        if not _is_complete(second_path,source_sha):
            raise IOError(f"1-second output failed completion verification: {second_path}")
    if not _is_complete(minute_path,source_sha) or pq.read_metadata(minute_path).num_rows!=len(minute):
        raise IOError(f"Minute output failed completion verification: {minute_path}")
    second_rows=(len(second) if second is not None else
                 pq.read_metadata(second_path).num_rows if market=="spot" else 0)
    elapsed = time.perf_counter()-started
    peak_gib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**3 if sys.platform == "darwin" else 1024**2)
    if peak_gib > 1.5:
        # ru_maxrss is a process-lifetime high-water mark, so it cannot fail one
        # month; outputs above are already written and verified.
        print(f"WARN process peak RSS {peak_gib:.2f} GiB above 1.5 GiB target", flush=True)
    print(f"DONE {market} {symbol} {month} minute_rows={len(minute)} second_rows={second_rows} "
          f"minute_bytes={minute_path.stat().st_size} second_bytes={second_path.stat().st_size if market=='spot' else 0} "
          f"elapsed_s={elapsed:.1f} peak_rss_gib={peak_gib:.2f} source_sha256={source_sha}", flush=True)
    return {"market": market, "symbol": symbol, "month": month, "minute_rows": len(minute),
            "second_rows": second_rows,
            "minute_bytes": minute_path.stat().st_size,
            "second_bytes": second_path.stat().st_size if market == "spot" else 0,
            "elapsed_seconds": elapsed, "peak_rss_gib": peak_gib}


def completed_archives(*, symbol: str | None = None, market: str | None = None, newest_first: bool = True) -> list[Path]:
    paths = [path for path in RAW_ROOT.rglob("*.zip") if path.with_suffix(path.suffix+".sha256").is_file()]
    if symbol:
        paths = [path for path in paths if _archive_info(path)[1] == symbol]
    if market:
        paths = [path for path in paths if _archive_info(path)[0] == market]
    paths.sort(key=lambda p: (_archive_info(p)[2], _archive_info(p)[0], _archive_info(p)[1]),
               reverse=newest_first)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=("BTCUSDT", "ETHUSDT"))
    parser.add_argument("--market", choices=("spot", "um"))
    parser.add_argument("--oldest-first", action="store_true")
    parser.add_argument("--limit-months", type=int, default=0, help="test/smoke cap; 0 means all")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    paths = completed_archives(symbol=args.symbol, market=args.market, newest_first=not args.oldest_first)
    if args.limit_months:
        paths = paths[:args.limit_months]
    print(f"START completed_archives={len(paths)} order={'oldest' if args.oldest_first else 'newest'} "
          f"disk_free_gib={shutil.disk_usage('.').free/1024**3:.1f} disk_min_gib={MIN_FREE_BYTES/1024**3:.1f} "
          f"rss_cap_gib=1.5", flush=True)
    done = skipped = failed = 0
    started = time.perf_counter()
    for i, archive in enumerate(paths,1):
        try:
            result = process_archive(archive, force=args.force)
            if result is None or result.get("skipped"):
                skipped += 1
            else:
                done += 1
        except Exception as exc:
            failed += 1
            print(f"FAILED {archive} {type(exc).__name__}: {exc}", flush=True)
        if (i % 5 == 0 or i == len(paths)) and time.perf_counter()>started:
            elapsed=time.perf_counter()-started
            rate=done/(elapsed/3600) if elapsed else 0
            print(f"PROGRESS {i}/{len(paths)} done={done} skipped={skipped} failed={failed} "
                  f"months_per_hour={rate:.1f} elapsed_min={elapsed/60:.1f} "
                  f"disk_free_gib={shutil.disk_usage('.').free/1024**3:.1f}",flush=True)
    elapsed=time.perf_counter()-started
    rate=done/(elapsed/3600) if elapsed else 0
    print(f"SUMMARY done={done} skipped={skipped} failed={failed} months_per_hour={rate:.1f} "
          f"peak_rss_gib={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**3 if sys.platform=='darwin' else 1024**2):.2f}",flush=True)
    return 1 if failed and done == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
