"""Spread-aware minute-bar trade simulator and summary statistics."""
from __future__ import annotations

from collections.abc import Sequence
import numpy as np
import pandas as pd
from msd.processing.timeutil import epoch_ints


def timestamp_ints(values, *, unit: str = "ns"):
    """Backward-compatible alias for the shared resolution-safe helper."""
    return epoch_ints(values,unit=unit)


def _utc_naive_ns(value) -> np.datetime64:
    stamp = pd.Timestamp(value)
    stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
    return np.datetime64(stamp.tz_localize(None), "ns")


def ratchet_stop(side: int, current: float, update: float | None) -> float:
    """Apply the shared no-loosening rule for long and short protective stops."""
    if update is None or not np.isfinite(float(update)):
        return float(current)
    return max(float(current), float(update)) if int(side) > 0 else min(float(current), float(update))


AMBIGUITY_KEYS = ("ambiguous", "resolved_tp", "resolved_sl", "unresolved")


def second_quotes(single_price: pd.DataFrame, spread: float | pd.Series) -> pd.DataFrame:
    """Apply one modeled spread symmetrically to single-price second OHLC."""
    spread_values = np.asarray(spread, dtype=float)
    if not np.isfinite(spread_values).all() or (spread_values < 0).any():
        raise ValueError("spread must be finite and nonnegative")
    out = single_price[["ts"]].copy()
    for field in "ohlc":
        values = pd.to_numeric(single_price[field], errors="raise")
        out[f"bid_{field}"] = values.to_numpy(float) - spread_values / 2
        out[f"ask_{field}"] = values.to_numpy(float) + spread_values / 2
    return out


def _resolve_second(side: int, stop: float, tp: float, seconds: pd.DataFrame | None,
                    minute_ts) -> tuple[str, float] | None:
    if seconds is None or minute_ts is None or len(seconds) != 60:
        return None
    start = pd.Timestamp(minute_ts)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    stamps = pd.to_datetime(seconds.ts, utc=True).astype("datetime64[ns, UTC]")
    expected = pd.date_range(start, periods=60, freq="s")
    # Series.equals also compares the source column name (``ts`` vs None),
    # which incorrectly rejected a complete, correctly ordered minute.
    if not np.array_equal(stamps.to_numpy(), expected.to_numpy()):
        return None
    prefix = "bid" if side > 0 else "ask"
    for second in seconds.itertuples(index=False):
        op = float(getattr(second, f"{prefix}_o"))
        high = float(getattr(second, f"{prefix}_h"))
        low = float(getattr(second, f"{prefix}_l"))
        stop_hit = low <= stop if side > 0 else high >= stop
        tp_hit = high >= tp if side > 0 else low <= tp
        if stop_hit:
            return "stop", min(op, stop) if side > 0 else max(op, stop)
        if tp_hit:
            return "tp", tp
    return None


def evaluate_bar(side: int, stop: float, tp: float | None, bar: dict,
                 *, stop_update: float | None = None, time_exit: bool = False,
                 time_at_open: bool = False, stop_active: bool = True, close_only: bool = False,
                 seconds: pd.DataFrame | None = None,
                 ambiguity_stats: dict[str, int] | None = None) -> tuple[float, str | None, float | None]:
    """Shared single-bar SL/TP/time evaluation used by backtest and live."""
    side = int(side)
    current = ratchet_stop(side, stop, stop_update)
    prefix = "bid" if side > 0 else "ask"
    op = float(bar[f"{prefix}_o"])
    high, low, close = (float(bar[f"{prefix}_{field}"]) for field in ("h", "l", "c"))
    if time_exit and time_at_open:
        return current, "time", op
    sl_hit = stop_active and (close <= current if side > 0 else close >= current) if close_only else stop_active and (low <= current if side > 0 else high >= current)
    tp_hit = tp is not None and (high >= float(tp) if side > 0 else low <= float(tp))
    if sl_hit and tp_hit and not close_only:
        if ambiguity_stats is not None:
            for field in AMBIGUITY_KEYS:
                ambiguity_stats.setdefault(field, 0)
            ambiguity_stats["ambiguous"] = ambiguity_stats.get("ambiguous", 0) + 1
        resolved = _resolve_second(side, current, float(tp), seconds, bar.get("ts"))
        key = "resolved_tp" if resolved and resolved[0] == "tp" else "resolved_sl" if resolved else "unresolved"
        if ambiguity_stats is not None:
            ambiguity_stats[key] = ambiguity_stats.get(key, 0) + 1
        if resolved is not None:
            return current, resolved[0], resolved[1]
    if sl_hit:
        fill = close if close_only else (min(op, current) if side > 0 else max(op, current))
        return current, "stop", fill
    if tp_hit:
        return current, "tp", float(tp)
    if time_exit:
        return current, "time", close
    return current, None, None


def simulate(bars: pd.DataFrame, orders: Sequence[dict], *, seconds: pd.DataFrame | None = None) -> pd.DataFrame:
    """Simulate causal orders using the same per-bar evaluator as the live engine."""
    timestamps = bars.ts.dt.tz_localize(None).to_numpy()
    ts_ns = bars.ts.astype("datetime64[ns, UTC]").astype("int64").to_numpy()
    arrays = {c: bars[c].to_numpy(dtype=float) for c in ("bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c")}
    second_groups = ({stamp: frame for stamp, frame in seconds.groupby(pd.to_datetime(seconds.ts, utc=True).dt.floor("min"))}
                     if seconds is not None and not seconds.empty else {})
    out = []
    for order_id, order in enumerate(orders):
        side = 1 if order["side"] in (1, "long") else -1
        start = int(np.searchsorted(timestamps, _utc_naive_ns(order["decision_ts"]), side="right"))
        exit_ts = order.get("exit_ts")
        exit_index = int(np.searchsorted(timestamps, _utc_naive_ns(exit_ts), side="left")) if exit_ts is not None else len(timestamps)
        if exit_ts is not None and exit_index < start:
            continue
        end = min(exit_index + 1, len(timestamps)) if exit_ts is not None and exit_index < len(timestamps) else len(timestamps)
        if start >= end or start >= len(timestamps):
            continue
        entry = arrays["ask_o" if side == 1 else "bid_o"][start]
        mid_entry = (arrays["bid_o"][start] + arrays["ask_o"][start]) / 2
        stop = float(order["stop"])
        risk = abs(mid_entry - stop)
        if risk <= 0 or side * (entry - stop) <= 0:
            continue
        tp = order.get("tp")
        raw_path = order.get("stop_path")
        if isinstance(raw_path, dict):
            path = {}
            for key, value in raw_path.items():
                if isinstance(key, (int, np.integer)):
                    path[int(key)] = value
                else:
                    path[int(np.searchsorted(ts_ns, _utc_naive_ns(key).astype("int64"), side="left"))] = value
        elif raw_path is not None:
            path = np.asarray(raw_path, dtype=float)
        else:
            path = None
        stop_checks = order.get("stop_checks")
        stats = dict.fromkeys(AMBIGUITY_KEYS, 0)
        exit_i, price, reason = end - 1, None, None
        for i in range(start, end):
            update = None
            if path is not None and i > start:
                update = path.get(i - 1) if isinstance(path, dict) else path[i - 1]
            bar = {f"{prefix}_{field}": arrays[f"{prefix}_{field}"][i]
                   for prefix in ("bid", "ask") for field in ("o", "h", "l", "c")}
            bar["ts"] = bars.ts.iloc[i]
            active = stop_checks is None or i in stop_checks
            at_deadline_open = exit_ts is not None and exit_index < len(timestamps) and i == exit_index
            terminal_close = exit_ts is None or exit_index >= len(timestamps)
            stop, reason, price = evaluate_bar(side, stop, tp, bar, stop_update=update,
                time_exit=at_deadline_open or (terminal_close and i == end - 1),
                time_at_open=at_deadline_open, stop_active=active,
                close_only=stop_checks is not None and active,
                seconds=second_groups.get(bars.ts.iloc[i]), ambiguity_stats=stats if seconds is not None else None)
            if reason is not None:
                exit_i = i
                break
        if reason is None:
            continue
        gross = side * (price - entry)
        exit_open = exit_ts is not None and exit_index < len(timestamps) and exit_i == exit_index
        exit_spread = (arrays["ask_o"][exit_i] - arrays["bid_o"][exit_i]) if exit_open else (arrays["ask_c"][exit_i] - arrays["bid_c"][exit_i])
        spread = (arrays["ask_o"][start] - arrays["bid_o"][start]) / 2 + exit_spread / 2
        record=dict(order_id=order_id, entry_ts=pd.Timestamp(timestamps[start], tz="UTC"), exit_ts=pd.Timestamp(timestamps[exit_i], tz="UTC"), entry_price=entry,
                        exit_price=price, side=side, exit_reason=reason, R=gross / risk, return_pct=100 * gross / entry,
                        spread_paid=spread, initial_risk=risk)
        if seconds is not None: record.update(stats)
        out.append(record)
    return pd.DataFrame(out)


def metrics(trades: pd.DataFrame, exposure: pd.Series | None = None) -> dict:
    if trades.empty:
        return {k: float("nan") for k in ("hit_rate", "avg_R", "profit_factor", "t_stat", "sharpe", "max_drawdown")} | {"trades": 0}
    r = trades.R.to_numpy(float)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    daily = trades.assign(day=trades.exit_ts.dt.floor("D")).groupby("day")["return_pct"].sum() / 100
    daily = daily.reindex(pd.date_range(trades.entry_ts.min().floor("D"), trades.exit_ts.max().floor("D"), freq="B", tz="UTC"), fill_value=0)
    if exposure is not None:
        daily = daily * exposure.reindex(daily.index, fill_value=0)
    equity = (1 + daily).cumprod()
    return dict(trades=len(r), hit_rate=float((r > 0).mean()), avg_R=float(r.mean()), profit_factor=float(wins / losses) if losses else float("inf"),
                t_stat=float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))) if len(r) > 1 and r.std(ddof=1) else float("nan"),
                sharpe=float(np.sqrt(252) * daily.mean() / daily.std(ddof=1)) if daily.std(ddof=1) else float("nan"),
                max_drawdown=float((equity / equity.cummax() - 1).min()))


def yearly(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    return pd.DataFrame({year: metrics(group) for year, group in trades.groupby(trades.entry_ts.dt.year)}).T


def random_percentile(bars: pd.DataFrame, orders: Sequence[dict], real_avg_r: float, seeds: int = 200) -> float:
    """Randomize sides at fixed entry times, preserving initial risk and TP distance."""
    if not orders:
        return float("nan")
    timestamps = bars.ts.dt.tz_localize(None).to_numpy()
    bid = bars.bid_o.to_numpy()
    ask = bars.ask_o.to_numpy()
    flipped = []
    for order in orders:
        side = 1 if order["side"] in (1, "long") else -1
        ix = int(np.searchsorted(timestamps, _utc_naive_ns(order["decision_ts"]), side="right"))
        if ix >= len(bars):
            flipped.append({**order, "stop": float("nan")})
            continue
        old_entry = (ask[ix] + bid[ix]) / 2
        new_entry = old_entry
        new_side = -side
        changed = dict(order, side=new_side, stop=new_entry - new_side * abs(old_entry - order["stop"]))
        if order.get("tp") is not None:
            changed["tp"] = new_entry + new_side * abs(order["tp"] - old_entry)
        if isinstance(order.get("stop_path"), dict):
            changed["stop_path"] = {i: new_entry + old_entry - level for i, level in order["stop_path"].items()}
        elif order.get("stop_path") is not None:
            changed["stop_path"] = new_entry + old_entry - np.asarray(order["stop_path"], dtype=float)
        flipped.append(changed)
    normal = simulate(bars, orders).set_index("order_id").R.reindex(range(len(orders))).to_numpy()
    opposite = simulate(bars, flipped).set_index("order_id").R.reindex(range(len(orders))).to_numpy()
    scores = []
    for seed in range(seeds):
        mask = np.random.default_rng(seed).integers(0, 2, size=len(orders)).astype(bool)
        scores.append(np.nanmean(np.where(mask, normal, opposite)))
    return float(100 * np.mean(np.asarray(scores) < real_avg_r))
