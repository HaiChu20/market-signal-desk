"""Resumable Stage 8 data-lake download campaign."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import argparse
import os
import pyarrow.parquet as pq

from .binance_lake import download_klines
from .auxiliary import download_cboe, download_funding, download_metrics
from .dukascopy import download as download_dukas
from .histdata import download as download_histdata

DUKASCOPY_START = {
    "USATECHIDXUSD": date(2012, 1, 1), "USA500IDXUSD": date(2012, 1, 1),
    "USA30IDXUSD": date(2014, 1, 1), "DEUIDXEUR": date(2014, 1, 1),
    "XAUUSD": date(2003, 1, 1), "XAGUSD": date(2003, 1, 1), "EURUSD": date(2003, 1, 1),
    "USDJPY": date(2003, 1, 1), "GBPUSD": date(2003, 1, 1),
    "LIGHTCMDUSD": date(2012, 1, 1), "BRENTCMDUSD": date(2012, 1, 1),
    "GBRIDXGBP": date(2014, 1, 1), "JPNIDXJPY": date(2014, 1, 1),
    "BTCUSD": date(2017, 1, 1), "ETHUSD": date(2018, 1, 1),
}
DUKASCOPY_ORDER = (
    "XAUUSD", "USA30IDXUSD", "DEUIDXEUR", "BTCUSD", "ETHUSD", "USATECHIDXUSD", "USA500IDXUSD",
    "XAGUSD", "EURUSD", "USDJPY", "GBPUSD", "LIGHTCMDUSD", "BRENTCMDUSD", "GBRIDXGBP", "JPNIDXJPY",
)


def _nonempty_parquet_count(root: Path) -> int:
    count=0
    if root.is_file():
        try: return int(pq.read_metadata(root).num_rows > 0)
        except Exception: return 0
    if not root.exists(): return count
    for path in root.rglob("*.parquet"):
        try:
            count += int(pq.read_metadata(path).num_rows > 0)
        except Exception:
            continue
    return count


def _verify_task_outputs(task_name: str, symbol: str | None = None) -> list[str]:
    expected: dict[str, tuple[str, ...]] = {
        "dukascopy": ("XAUUSD","USA30IDXUSD","DEUIDXEUR","BTCUSD","ETHUSD","USATECHIDXUSD","USA500IDXUSD","XAGUSD","EURUSD","USDJPY","GBPUSD","LIGHTCMDUSD","BRENTCMDUSD","GBRIDXGBP","JPNIDXJPY"),
        "histdata": ("GRXEUR","WTIUSD"),
        "spot": ("BTCUSDT","ETHUSDT"), "um": ("BTCUSDT","ETHUSDT"),
        "funding": ("BTCUSDT","ETHUSDT"), "metrics": ("BTCUSDT","ETHUSDT"),
        "cboe": ("VIX","VIX3M","VIX9D"),
    }
    if task_name == "edgar":
        import pandas as pd
        path=Path("data/aux/earnings/sec_8k_item_2_02.csv")
        if not path.exists() or path.stat().st_size == 0 or pd.read_csv(path).empty:
            raise RuntimeError("SEC EDGAR has no non-empty verified earnings output")
        return []
    if task_name not in expected: return []
    roots={
        "dukascopy":Path("data/bars/dukascopy"), "histdata":Path("data/bars/histdata"),
        "spot":Path("data/bars/binance_spot"), "um":Path("data/bars/binance_um"),
        "funding":Path("data/aux/funding"), "metrics":Path("data/aux/metrics"),
        "cboe":Path("data/aux/vix"),
    }
    root=roots[task_name]
    symbols=(symbol,) if symbol is not None else expected[task_name]
    if task_name == "cboe":
        empty=[item for item in symbols
               if not (root/f"{item}_History.parquet").exists()
               or _nonempty_parquet_count(root/f"{item}_History.parquet")==0]
    else:
        empty=[item for item in symbols if _nonempty_parquet_count(root/item)==0]
    # For a whole Dukascopy campaign this is a final inventory, not a per-task
    # failure: later symbols are expected to be absent until their turn.
    if empty and not (task_name == "dukascopy" and symbol is None):
        raise RuntimeError(f"No non-empty verified output for {task_name}: {', '.join(empty)}")
    return empty


def _finalize_dukascopy_symbol(symbol: str) -> None:
    """Retry recorded missing sides and refresh manifests after an action error."""
    from . import dukascopy
    start=DUKASCOPY_START[symbol]
    end=datetime.now(timezone.utc).date()
    dukascopy._final_missing_pass(symbol,Path("data/bars/dukascopy"),start,end)
    from .catalog import write_manifest
    for path in sorted((Path("data/bars/dukascopy")/symbol).glob("????-??.parquet")):
        frame=__import__("pandas").read_parquet(path)
        if not frame.empty:
            write_manifest("dukascopy",symbol,frame,"bidask","tick")


def run(task_name: str) -> None:
    if task_name == "dukascopy":
        tasks = [(f"Dukascopy {symbol}", lambda symbol=symbol: download_dukas(
                    symbol, DUKASCOPY_START[symbol], datetime.now(timezone.utc).date(), workers=int(os.environ.get("MSD_DUKA_WORKERS", "4"))))
                 for symbol in DUKASCOPY_ORDER]
    elif task_name == "histdata":
        tasks = [(f"HistData {symbol}", lambda symbol=symbol: download_histdata(symbol, date(2010, 11, 1))) for symbol in ("GRXEUR", "WTIUSD")]
    elif task_name == "funding": tasks = [("Binance funding", download_funding)]
    elif task_name == "metrics": tasks = [("Binance metrics", download_metrics)]
    elif task_name == "cboe": tasks = [("Cboe VIX", download_cboe)]
    elif task_name == "edgar": tasks = [("SEC EDGAR", lambda: print(__import__("msd.data.auxiliary", fromlist=["download_edgar"]).download_edgar(), flush=True))]
    elif task_name == "spot": tasks = [("Binance spot", lambda: download_klines("spot"))]
    elif task_name == "um": tasks = [("Binance USD-M", lambda: download_klines("um"))]
    elif task_name == "all":
        for name in ("dukascopy", "histdata", "spot", "um", "funding", "metrics", "cboe", "edgar"):
            run(name)
        return
    else: raise ValueError(task_name)
    log_dir = Path("data/logs"); log_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    for label, action in tasks:
        try:
            print(f"START {label}", flush=True)
            action()
            if task_name == "dukascopy":
                _verify_task_outputs(task_name,label.rsplit(" ",1)[-1])
            else:
                _verify_task_outputs(task_name)
            print(f"DONE {label}", flush=True)
        except Exception as exc:
            message = f"BLOCKED {label}: {type(exc).__name__}: {exc}"
            failures.append(message)
            print(message, flush=True)
            if task_name == "dukascopy":
                symbol=label.rsplit(" ",1)[-1]
                try:
                    _finalize_dukascopy_symbol(symbol)
                    print(f"Dukascopy exceptional finalization completed for {symbol}",flush=True)
                except Exception as finalize_error:
                    print(f"Dukascopy exceptional finalization failed for {symbol}: {type(finalize_error).__name__}: {finalize_error}",flush=True)
    (log_dir / "stage8_failures.txt").write_text("\n".join(failures) + ("\n" if failures else ""))
    if task_name == "dukascopy":
        incomplete=_verify_task_outputs("dukascopy")
        print("Dukascopy final output audit: "+(", ".join(incomplete) if incomplete else "all symbols have verified data"),flush=True)
        import csv
        missing_summary=[]
        for symbol in DUKASCOPY_ORDER:
            path=log_dir/f"missing_{symbol}.csv"
            if not path.exists():
                continue
            with path.open(newline="") as stream:
                count=sum(1 for _ in csv.DictReader(stream))
            if count:
                missing_summary.append(f"{symbol}={count}")
        print("Dukascopy campaign missing days: "+(", ".join(missing_summary) if missing_summary else "none"),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("all", "dukascopy", "histdata", "spot", "um", "funding", "metrics", "cboe", "edgar"), default="all")
    run(parser.parse_args().task)
