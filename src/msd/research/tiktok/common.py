"""Shared sessions, execution costs, trade records, metrics, and report helpers."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import json
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from msd.data import load as load_data
from msd.research.ledger import FIELDS as TRIAL_FIELDS
from msd.research.ledger import read_trials

DEV_START = pd.Timestamp("2019-01-01", tz="UTC")
DEV_END_EXCLUSIVE = pd.Timestamp("2023-01-01", tz="UTC")
HOLDOUT_START = DEV_END_EXCLUSIVE
WARMUP_START = pd.Timestamp("2018-01-01", tz="UTC")
CRYPTO_MARKETS = frozenset({"BTCUSDT", "ETHUSDT"})


@dataclass(frozen=True)
class MarketSession:
    timezone: str
    open_time: time
    close_time: time
    full_day_local: bool = False


# Frozen market and RTH definitions from the TikTok test plan.
MARKETS = (
    "USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD", "DEUIDXEUR", "GBRIDXGBP",
    "JPNIDXJPY", "XAUUSD", "XAGUSD", "LIGHTCMDUSD", "BRENTCMDUSD", "EURUSD",
    "GBPUSD", "USDJPY", "BTCUSDT", "ETHUSDT",
)
MARKET_SESSIONS = {
    "USATECHIDXUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "USA500IDXUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "USA30IDXUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "DEUIDXEUR": MarketSession("Europe/Berlin", time(9), time(17, 30), True),
    "GBRIDXGBP": MarketSession("Europe/London", time(8), time(16, 30), True),
    "JPNIDXJPY": MarketSession("Asia/Tokyo", time(9), time(15), True),
    "XAUUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "XAGUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "LIGHTCMDUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "BRENTCMDUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "EURUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "GBPUSD": MarketSession("America/New_York", time(9, 30), time(16)),
    "USDJPY": MarketSession("America/New_York", time(9, 30), time(16)),
    "BTCUSDT": MarketSession("America/New_York", time(9, 30), time(16)),
    "ETHUSDT": MarketSession("America/New_York", time(9, 30), time(16)),
}
SOURCE = {market: ("binance_spot" if market in CRYPTO_MARKETS else "dukascopy")
          for market in MARKETS}
MARKET_TIER = {
    "USATECHIDXUSD": 1,
    "USA500IDXUSD": 2, "USA30IDXUSD": 2, "DEUIDXEUR": 2,
    "GBRIDXGBP": 2, "JPNIDXJPY": 2,
    "XAUUSD": 3, "XAGUSD": 3, "LIGHTCMDUSD": 3, "BRENTCMDUSD": 3,
    "EURUSD": 3, "GBPUSD": 3, "USDJPY": 3, "BTCUSDT": 3, "ETHUSDT": 3,
}
TRADE_KEYS = (
    "market", "strategy", "params", "period", "side", "entry_ts", "exit_ts",
    "entry_price", "exit_price", "risk_points", "gross_R", "net_R",
    "net_R_cost15", "exit_reason",
)


@dataclass(frozen=True)
class SessionFrame:
    session_id: date
    start: pd.Timestamp
    end: pd.Timestamp
    bars: pd.DataFrame
    complete: bool


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def period_for_entry(entry_ts) -> str:
    return "dev" if _utc(entry_ts) < HOLDOUT_START else "holdout"


def assert_holdout_allowed(records: Iterable[dict], *, allow_holdout: bool = False) -> None:
    if not allow_holdout and any(record.get("period") == "holdout" for record in records):
        raise PermissionError("holdout metrics require an explicit holdout run")


def load_1m(market: str, start= WARMUP_START, end=DEV_END_EXCLUSIVE,
            *, allow_holdout: bool = False) -> pd.DataFrame:
    """Load local raw bid/ask minutes and enforce the holdout read boundary."""
    start_ts, end_ts = _utc(start), _utc(end)
    if end_ts > HOLDOUT_START and not allow_holdout:
        raise PermissionError("loading holdout bars requires an explicit holdout run")
    if market not in SOURCE:
        raise ValueError(f"unsupported TikTok test market: {market}")
    last_day = end_ts.normalize() - pd.Timedelta(days=1)
    frame = load_data(market, start_ts, last_day,
                      source=SOURCE[market], raw=True)
    if frame.empty:
        raise FileNotFoundError(f"no local minute bars for {market} in requested range")
    frame = frame.copy()
    frame["ts"] = pd.to_datetime(frame.ts, utc=True)
    if frame.ts.min() < start_ts or frame.ts.max() >= end_ts:
        frame = frame[(frame.ts >= start_ts) & (frame.ts < end_ts)].copy()
    if not frame.ts.is_monotonic_increasing:
        frame = frame.sort_values("ts")
    frame = frame.drop_duplicates("ts", keep="last").reset_index(drop=True)
    required = [f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc"]
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{market} minute bars missing columns: {', '.join(sorted(missing))}")
    if market not in CRYPTO_MARKETS:
        for field in "ohlc":
            spread = frame[f"ask_{field}"].to_numpy(float) - frame[f"bid_{field}"].to_numpy(float)
            if not np.isfinite(spread).all() or np.any(spread <= 0):
                raise ValueError(f"{market} has missing or non-positive {field} bid/ask spreads")
    return frame[["ts", *required]].reset_index(drop=True)


def resample_closed_bars(bars_1m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Resample minute OHLC into complete, right-labelled closed bars only."""
    if minutes not in (5, 60):
        raise ValueError("only frozen 5-minute and 1-hour bars are supported")
    bars = bars_1m.copy()
    bars["ts"] = pd.to_datetime(bars.ts, utc=True)
    bars = bars.sort_values("ts").drop_duplicates("ts").set_index("ts")
    rule = f"{minutes}min"
    agg = {}
    for side in ("bid", "ask"):
        agg[f"{side}_o"] = (f"{side}_o", "first")
        agg[f"{side}_h"] = (f"{side}_h", "max")
        agg[f"{side}_l"] = (f"{side}_l", "min")
        agg[f"{side}_c"] = (f"{side}_c", "last")
    grouped = bars.resample(rule, closed="left", label="right", origin="epoch")
    result = grouped.agg(**agg)
    counts = bars.bid_o.resample(rule, closed="left", label="right", origin="epoch").count()
    result = result[counts == minutes].dropna().reset_index()
    return result


def _local_stamp(day: date, at: time, timezone: str) -> pd.Timestamp:
    naive = datetime.combine(day, at)
    return pd.Timestamp(naive, tz=ZoneInfo(timezone)).tz_convert("UTC")


def session_bounds(market: str, session_id: date, kind: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if kind not in {"rth", "full_day"}:
        raise ValueError("session kind must be 'rth' or 'full_day'")
    spec = MARKET_SESSIONS[market]
    if kind == "rth":
        return (_local_stamp(session_id, spec.open_time, spec.timezone),
                _local_stamp(session_id, spec.close_time, spec.timezone))
    if spec.full_day_local:
        start = _local_stamp(session_id, time(0), spec.timezone)
        end = _local_stamp(session_id + timedelta(days=1), time(0), spec.timezone)
    else:
        start = _local_stamp(session_id - timedelta(days=1), time(18), spec.timezone)
        end = _local_stamp(session_id, time(17), spec.timezone)
    return start, end


def session_frames(bars_1m: pd.DataFrame, market: str, kind: str) -> list[SessionFrame]:
    """Return weekday sessions with complete status; timestamps are minute opens."""
    if market not in MARKET_SESSIONS:
        raise ValueError(f"unsupported TikTok test market: {market}")
    bars = bars_1m.copy()
    bars["ts"] = pd.to_datetime(bars.ts, utc=True)
    bars = bars.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    spec = MARKET_SESSIONS[market]
    local = bars.ts.dt.tz_convert(spec.timezone)
    local_dates = local.dt.date
    if kind == "full_day" and not spec.full_day_local:
        keys = [day + timedelta(days=int(hour >= 18))
                for day, hour in zip(local_dates, local.dt.hour)]
    else:
        keys = list(local_dates)
    grouped = {day: part.reset_index(drop=True)
               for day, part in bars.groupby(pd.Series(keys, index=bars.index), sort=True)}
    rth_complete = None
    if kind == "full_day":
        rth_complete = {item.session_id: item.complete
                        for item in session_frames(bars, market, "rth")}
    first_day, last_day = min(keys), max(keys)
    window_start = bars.ts.min()
    window_end = bars.ts.max() + pd.Timedelta(minutes=1)
    rows = []
    day = first_day - timedelta(days=1)
    final = last_day + timedelta(days=1)
    while day <= final:
        if day.weekday() < 5 or market in CRYPTO_MARKETS:
            start, end = session_bounds(market, day, kind)
            if end <= window_start or start >= window_end:
                day += timedelta(days=1)
                continue
            part = grouped.get(day, bars.iloc[:0].copy()).copy()
            if not part.empty:
                part = part[(part.ts >= start) & (part.ts < end)].reset_index(drop=True)
            if part.empty:
                rows.append(SessionFrame(day, start, end, part, False))
            elif kind == "full_day":
                # A full-day window may contain the market's scheduled daily
                # pause. Its quality is anchored to the unchanged RTH rule.
                complete = (rth_complete.get(day, False) and
                            part.ts.iloc[0] <= start + pd.Timedelta(hours=3))
                rows.append(SessionFrame(day, start, end, part, bool(complete)))
            else:
                ts = pd.DatetimeIndex(part.ts)
                expected_last = end - pd.Timedelta(minutes=1)
                complete = (ts[0] == start and ts[-1] == expected_last and
                            pd.date_range(start, periods=6, freq="min").isin(ts).all() and
                            (len(ts) < 2 or (ts[1:] - ts[:-1]).max() <= pd.Timedelta(minutes=6)))
                rows.append(SessionFrame(day, start, end, part, bool(complete)))
        day += timedelta(days=1)
    return rows


def session_quality(bars_1m: pd.DataFrame, market: str, kind: str) -> dict:
    sessions = session_frames(bars_1m, market, kind)
    return {"sessions_with_data": sum(bool(len(item.bars)) for item in sessions),
            "complete_sessions": sum(item.complete for item in sessions),
            "skipped_incomplete": sum(not item.complete for item in sessions)}


def midpoint(row: pd.Series | dict, field: str) -> float:
    return (float(row[f"bid_{field}"]) + float(row[f"ask_{field}"])) / 2.


def spread_at(row: pd.Series | dict, field: str = "o") -> float:
    spread = float(row[f"ask_{field}"]) - float(row[f"bid_{field}"])
    if not np.isfinite(spread) or spread <= 0:
        raise ValueError("Dukascopy execution requires a positive observed spread")
    return spread


def build_trade_record(market: str, strategy: str, params: dict, side: int,
                       entry_ts, exit_ts, entry_price: float, exit_price: float,
                       risk_points: float, *, gross_entry: float | None = None,
                       gross_exit: float | None = None,
                       entry_spread: float | None = None,
                       exit_spread: float | None = None,
                       exit_reason: str, allow_holdout: bool = False) -> dict:
    """Build the exact shared trade schema and calculate 1x/1.5x-cost R."""
    if side not in (-1, 1) or not np.isfinite(risk_points) or risk_points <= 0:
        raise ValueError("side must be ±1 and initial stop distance must be positive")
    entry_ts, exit_ts = _utc(entry_ts), _utc(exit_ts)
    period = period_for_entry(entry_ts)
    if entry_ts < DEV_START:
        raise ValueError("warm-up entries are not tradable report rows")
    if period == "holdout" and not allow_holdout:
        raise PermissionError("building holdout trades requires an explicit holdout run")
    gross_entry = float(entry_price) if gross_entry is None else float(gross_entry)
    gross_exit = float(exit_price) if gross_exit is None else float(gross_exit)
    gross_r = side * (gross_exit - gross_entry) / risk_points
    if market in CRYPTO_MARKETS:
        net_r = gross_r - .0005 * (abs(entry_price) + abs(exit_price)) / risk_points
        net15 = gross_r - .00075 * (abs(entry_price) + abs(exit_price)) / risk_points
    else:
        if entry_spread is None or exit_spread is None or entry_spread <= 0 or exit_spread <= 0:
            raise ValueError("Dukascopy trades require positive entry and exit spreads")
        net_r = side * (float(exit_price) - float(entry_price)) / risk_points
        entry_wide = gross_entry + side * .75 * float(entry_spread)
        exit_wide = gross_exit - side * .75 * float(exit_spread)
        net15 = side * (exit_wide - entry_wide) / risk_points
    record = {
        "market": market, "strategy": strategy, "params": dict(params), "period": period,
        "side": int(side), "entry_ts": entry_ts.isoformat(), "exit_ts": exit_ts.isoformat(),
        "entry_price": float(entry_price), "exit_price": float(exit_price),
        "risk_points": float(risk_points), "gross_R": float(gross_r), "net_R": float(net_r),
        "net_R_cost15": float(net15), "exit_reason": str(exit_reason),
    }
    assert tuple(record) == TRADE_KEYS
    return record


def metrics(trades: Iterable[dict], *, allow_holdout: bool = False) -> dict:
    rows = sorted(trades, key=lambda row: (row["entry_ts"], row["market"]))
    assert_holdout_allowed(rows, allow_holdout=allow_holdout)
    if not rows:
        return {"trades": 0, "win_rate": None, "avg_win_R": None, "avg_loss_R": None,
                "net_avg_R": None, "net_avg_R_cost15": None,
                "profit_factor": None, "t": None, "max_drawdown_R": None,
                "longest_losing_streak": 0, "exit_reason_counts": {}}
    values = np.asarray([row["net_R"] for row in rows], dtype=float)
    wins, losses = values[values > 0], values[values < 0]
    sd = float(values.std(ddof=1)) if len(values) > 1 else 0.
    equity = np.r_[0., np.cumsum(values)]
    peaks = np.maximum.accumulate(equity)
    streak = longest = 0
    for value in values:
        streak = streak + 1 if value < 0 else 0
        longest = max(longest, streak)
    return {
        "trades": len(rows), "win_rate": float(np.mean(values > 0)),
        "avg_win_R": float(wins.mean()) if len(wins) else None,
        "avg_loss_R": float(losses.mean()) if len(losses) else None,
        "net_avg_R": float(values.mean()),
        "net_avg_R_cost15": float(np.mean([row["net_R_cost15"] for row in rows])),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) else None,
        "t": float(values.mean() / sd * np.sqrt(len(values))) if sd > 0 else None,
        "max_drawdown_R": float((peaks - equity).max()),
        "longest_losing_streak": int(longest),
        "exit_reason_counts": {str(reason): int(count) for reason, count in
                               pd.Series([row["exit_reason"] for row in rows]).value_counts().items()},
    }


def metrics_by(trades: Iterable[dict], key: Callable[[dict], object], *,
               allow_holdout: bool = False) -> dict:
    rows = list(trades)
    assert_holdout_allowed(rows, allow_holdout=allow_holdout)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        label = key(row)
        groups.setdefault(str(label), []).append(row)
    return {label: metrics(group, allow_holdout=allow_holdout)
            for label, group in sorted(groups.items())}


def required_outputs(trades: Iterable[dict], *, allow_holdout: bool = False) -> dict:
    rows = list(trades)
    assert_holdout_allowed(rows, allow_holdout=allow_holdout)
    by_side = {"long": metrics([row for row in rows if row["side"] > 0], allow_holdout=allow_holdout),
               "short": metrics([row for row in rows if row["side"] < 0], allow_holdout=allow_holdout)}
    by_year = metrics_by(rows, lambda row: _utc(row["entry_ts"]).year,
                         allow_holdout=allow_holdout)
    return {"overall": metrics(rows, allow_holdout=allow_holdout),
            "by_year": by_year, "long_vs_short": by_side}


def equal_weight_tiers(market_results: dict[str, dict], *, allow_holdout: bool = False) -> dict:
    """Pool market summaries with equal market weight, as frozen by the plan."""
    pooled = {}
    for tier in (1, 2, 3):
        names = [market for market in MARKETS if MARKET_TIER[market] == tier and market in market_results]
        for scope in ("chosen", "default"):
            summaries = [market_results[market][scope]["overall"] for market in names]
            usable = [item for item in summaries if item["net_avg_R"] is not None]
            returns = np.asarray([item["net_avg_R"] for item in usable], dtype=float)
            sd = float(returns.std(ddof=1)) if len(returns) > 1 else 0.
            random_values = [market_results[market]["random"][scope]["random_percentile"]
                             for market in names
                             if market_results[market]["random"][scope]["random_percentile"] is not None]
            pooled[f"tier_{tier}_{scope}"] = {
                "markets": len(usable), "trades": int(sum(item["trades"] for item in summaries)),
                "net_avg_R": float(returns.mean()) if len(returns) else None,
                "net_avg_R_cost15": float(np.mean([item["net_avg_R_cost15"] for item in usable])) if usable else None,
                "t_equal_weight_markets": (float(returns.mean() / sd * np.sqrt(len(returns)))
                                            if sd > 0 else None),
                "random_percentile_equal_weight_markets": float(np.mean(random_values)) if random_values else None,
            }
    return pooled


def random_entry_benchmark(trades: Iterable[dict], simulate_exit: Callable[[dict, int], dict | float],
                           *, seeds: int = 1000, seed: int = 0,
                           allow_holdout: bool = False) -> dict:
    """Randomize direction at fixed entry times; callback replays each side's exit."""
    rows = list(trades)
    assert_holdout_allowed(rows, allow_holdout=allow_holdout)
    if not rows:
        return {"seeds": seeds, "actual_avg_R": None, "random_percentile": None,
                "random_mean_R": None, "random_p05_R": None, "random_p95_R": None}
    outcomes = np.full((len(rows), 2), np.nan, dtype=float)
    unresolved = 0
    for i, row in enumerate(rows):
        for j, side in enumerate((1, -1)):
            value = simulate_exit(row, side)
            if value is None:
                unresolved += 1
            else:
                outcomes[i, j] = float(value["net_R"] if isinstance(value, dict) else value)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, 2, size=(seeds, len(rows)))
    sampled = outcomes[np.arange(len(rows))[None, :], draws]
    valid_count = np.isfinite(sampled).sum(axis=1)
    random_means = np.divide(np.nansum(sampled, axis=1), valid_count,
                              out=np.full(seeds, np.nan), where=valid_count > 0)
    random_means = random_means[np.isfinite(random_means)]
    if not len(random_means):
        return {"seeds": seeds, "actual_avg_R": None, "random_percentile": None,
                "random_mean_R": None, "random_p05_R": None, "random_p95_R": None,
                "unresolved_side_outcomes": unresolved}
    actual = float(np.mean([row["net_R"] for row in rows]))
    return {"seeds": seeds, "actual_avg_R": actual,
            "random_percentile": float(np.mean(random_means <= actual) * 100.),
            "random_mean_R": float(random_means.mean()),
            "random_p05_R": float(np.percentile(random_means, 5)),
            "random_p95_R": float(np.percentile(random_means, 95)),
            "unresolved_side_outcomes": unresolved}


def grid_table(rows: list[dict], *, allow_holdout: bool = False) -> pd.DataFrame:
    """Tabular full grid with parameter columns followed by the required stats."""
    columns = list(dict.fromkeys(key for row in rows for key in row.get("params", {})))
    expanded = []
    exit_reasons = sorted({str(reason) for row in rows
                           for reason in (row.get("exit_reason_counts") or
                                          row.get("summary", {}).get("overall", {}).get("exit_reason_counts", {}))})
    stats = ("trades", "unresolved_at_end", "win_rate", "avg_win_R", "avg_loss_R", "net_avg_R", "profit_factor",
             "net_avg_R_cost15", "t", "max_drawdown_R", "longest_losing_streak")
    for row in rows:
        summary = (row["summary"]["overall"] if "summary" in row else
                   metrics(row.get("trades", []), allow_holdout=allow_holdout))
        expanded.append({**row.get("params", {}), **summary,
                         "unresolved_at_end": row.get("unresolved_at_end", 0),
                         **{f"exit_{reason}": (row.get("exit_reason_counts") or
                                               summary["exit_reason_counts"]).get(reason, 0)
                            for reason in exit_reasons}})
    return pd.DataFrame(expanded, columns=[*columns, *stats, *(f"exit_{x}" for x in exit_reasons)])


def equity_curve(trades: Iterable[dict], *, allow_holdout: bool = False) -> pd.DataFrame:
    rows = list(trades)
    assert_holdout_allowed(rows, allow_holdout=allow_holdout)
    ordered = sorted(rows, key=lambda row: (row["entry_ts"], row["market"]))
    out = pd.DataFrame([{"entry_ts": row["entry_ts"], "market": row["market"],
                         "period": row["period"], "net_R": row["net_R"]} for row in ordered])
    if out.empty:
        return pd.DataFrame(columns=["entry_ts", "market", "period", "net_R", "equity_R"])
    out["equity_R"] = out.net_R.cumsum()
    return out


def write_report(output_dir: Path, name: str, report: dict,
                 grid: list[dict], trades: Iterable[dict], *, allow_holdout: bool = False) -> None:
    rows = list(trades)
    assert_holdout_allowed(rows, allow_holdout=allow_holdout)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{name}.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    grid_table(grid, allow_holdout=allow_holdout).to_csv(output_dir / f"{name}_grid.csv", index=False)
    equity_curve(rows, allow_holdout=allow_holdout).to_csv(
        output_dir / f"{name}_equity.csv", index=False
    )
    lines = [f"# {name.replace('_', ' ')}", "",
             "| Scope | Trades | Win rate | Avg win R | Avg loss R | Net avg R | 1.5x-cost R | PF | t | Max DD R | Longest loss streak |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for scope, values in report.get("scopes", {}).items():
        m = values["overall"]
        fields = [m.get(k) for k in ("trades", "win_rate", "avg_win_R", "avg_loss_R", "net_avg_R",
                                     "net_avg_R_cost15", "profit_factor", "t", "max_drawdown_R",
                                     "longest_losing_streak")]
        lines.append(f"| {scope} | " + " | ".join("" if value is None else str(value) for value in fields) + " |")
    lines += ["", "Full parameter grid is in the paired CSV. Equity is cumulative net R; period labels separate dev and holdout.", ""]
    (output_dir / f"{name}.md").write_text("\n".join(lines))


def append_trial_once(path: Path, row: dict[str, str], *, run_id: str) -> None:
    """Append one CRLF ledger row after checking this run identifier is unused."""
    existing = read_trials(path) if path.exists() else []
    if any(item["run_id"] == run_id for item in existing):
        raise FileExistsError(f"TikTok run already recorded: {run_id}")
    if set(row) != set(TRIAL_FIELDS):
        raise ValueError("TikTok ledger row must match the existing trials.csv schema")
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIAL_FIELDS, lineterminator="\r\n")
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def config_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def strategy_simulator(strategy: str):
    """Simple shared hook for A or worker B: simulate(bars_1m, market, params)."""
    if strategy == "A":
        from .strategy_a import simulate
    elif strategy == "B":
        from . import strategy_b
        simulate = strategy_b.simulate
    else:
        raise ValueError(f"unknown TikTok strategy: {strategy}")
    return simulate


def validate_trade_records(records: Iterable[dict]) -> list[dict]:
    rows = list(records)
    for row in rows:
        if tuple(row) != TRADE_KEYS:
            raise ValueError("simulator trade does not match the shared record schema")
    return rows
