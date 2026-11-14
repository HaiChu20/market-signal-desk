"""Strategy B: first session candle versus fast EMA, managed by hourly EMA."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from msd.processing.timeframes import build_timeframe

PARAM_KEYS = {
    "fast_ema",
    "slow_ema",
    "stop_atr",
    "exit_mode",
    "overlap",
    "time_stop_days",
}
CRYPTO = {"BTCUSDT", "ETHUSDT"}
US_INDICES = {"USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD"}
SESSION = {
    "DEUIDXEUR": ("Europe/Berlin", time(9, 0), time(17, 30)),
    "GBRIDXGBP": ("Europe/London", time(8, 0), time(16, 30)),
    "JPNIDXJPY": ("Asia/Tokyo", time(9, 0), time(15, 0)),
}
NY_SESSION = ("America/New_York", time(9, 30), time(16, 0))
DEV_START = pd.Timestamp("2019-01-01", tz="UTC")
HOLDOUT_START = pd.Timestamp("2023-01-01", tz="UTC")


def _validate(bars: pd.DataFrame, market: str, params: dict) -> pd.DataFrame:
    if set(params) != PARAM_KEYS:
        raise ValueError(f"Strategy B params must be exactly {sorted(PARAM_KEYS)}")
    if params["exit_mode"] not in {"close", "touch"}:
        raise ValueError("exit_mode must be close or touch")
    if params["overlap"] not in {"single", "daily"}:
        raise ValueError("overlap must be single or daily")
    if params["time_stop_days"] not in {None, 10}:
        raise ValueError("time_stop_days must be None or 10")
    if int(params["fast_ema"]) <= 0 or int(params["slow_ema"]) <= 0:
        raise ValueError("EMA periods must be positive")
    if float(params["stop_atr"]) <= 0:
        raise ValueError("stop_atr must be positive")
    required = {"ts", *(f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc")}
    missing = required - set(bars)
    if missing:
        raise ValueError(f"bars_1m missing columns: {sorted(missing)}")
    result = bars.copy()
    result["ts"] = pd.to_datetime(result.ts, utc=True).astype("datetime64[ns, UTC]")
    result = result.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    quote_columns = [f"{side}_{field}" for side in ("bid", "ask") for field in "ohlc"]
    if not np.isfinite(result[quote_columns].to_numpy(float)).all():
        raise ValueError("bars_1m contains non-finite quotes")
    if market not in CRYPTO:
        for field in "ohlc":
            if not (result[f"ask_{field}"] > result[f"bid_{field}"]).all():
                raise ValueError(f"{market} requires positive executable bid/ask spreads")
    return result


def _session_rule(market: str) -> tuple[ZoneInfo, time, time]:
    name, opened, closed = SESSION.get(market, NY_SESSION)
    return ZoneInfo(name), opened, closed


def _session_bounds(day, zone: ZoneInfo, opened: time, closed: time) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(datetime.combine(day, opened), tz=zone).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(day, closed), tz=zone).tz_convert("UTC")
    return start, end


def _complete_sessions(
    bars: pd.DataFrame, market: str
) -> list[tuple[object, pd.Timestamp, pd.Timestamp]]:
    zone, opened, closed = _session_rule(market)
    local = pd.to_datetime(bars.ts, utc=True).dt.tz_convert(zone)
    minute = local.dt.hour * 60 + local.dt.minute
    opened_minute = opened.hour * 60 + opened.minute
    closed_minute = closed.hour * 60 + closed.minute
    active = bars.loc[(minute >= opened_minute) & (minute < closed_minute)].copy()
    active["_day"] = local.loc[active.index].dt.date.to_numpy()
    sessions = []
    for day, current in active.groupby("_day", sort=True):
        start, end = _session_bounds(day, zone, opened, closed)
        if current.empty or current.ts.iloc[0] != start:
            continue
        if current.ts.iloc[-1] < end - pd.Timedelta(minutes=1):
            continue
        gaps = current.ts.diff().dropna().dt.total_seconds().div(60).sub(1)
        if len(gaps) and gaps.max() > 5:
            continue
        required = pd.date_range(start, periods=6, freq="min")
        if not required.isin(current.ts).all():
            continue
        sessions.append((day, start, end))
    return sessions


def _indicator_bars(bars: pd.DataFrame, market: str, fast: int, slow: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    five = build_timeframe(bars, market, "5m")
    five["mid_close"] = (five.bid_c.to_numpy(float) + five.ask_c.to_numpy(float)) / 2
    five["fast_ema"] = five.mid_close.ewm(
        span=fast, adjust=False, min_periods=fast
    ).mean()

    hourly = build_timeframe(bars, market, "1h")
    hourly["mid_close"] = (hourly.bid_c.to_numpy(float) + hourly.ask_c.to_numpy(float)) / 2
    hourly["mid_high"] = (hourly.bid_h.to_numpy(float) + hourly.ask_h.to_numpy(float)) / 2
    hourly["mid_low"] = (hourly.bid_l.to_numpy(float) + hourly.ask_l.to_numpy(float)) / 2
    previous = hourly.mid_close.shift(1)
    true_range = pd.concat(
        [
            hourly.mid_high - hourly.mid_low,
            (hourly.mid_high - previous).abs(),
            (hourly.mid_low - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    hourly["atr14"] = true_range.rolling(14, min_periods=14).mean()
    hourly["slow_ema"] = hourly.mid_close.ewm(
        span=slow, adjust=False, min_periods=slow
    ).mean()
    hourly["known_at"] = pd.to_datetime(hourly.known_at, utc=True).astype(
        "datetime64[ns, UTC]"
    )
    return five, hourly


def _entry_candidates(
    bars: pd.DataFrame,
    market: str,
    params: dict,
    five: pd.DataFrame,
    hourly: pd.DataFrame,
    sessions: list[tuple[object, pd.Timestamp, pd.Timestamp]],
) -> list[dict]:
    five_by_open = five.drop_duplicates("ts", keep="last").set_index("ts")
    hourly_known = hourly.sort_values("known_at")
    hourly_times = hourly_known.known_at.to_numpy(dtype="datetime64[ns]")
    minute_times = bars.ts.to_numpy(dtype="datetime64[ns]")
    candidates = []
    for session_index, (day, start, end) in enumerate(sessions):
        if start not in five_by_open.index:
            continue
        signal = five_by_open.loc[start]
        if not np.isfinite(signal.fast_ema) or signal.mid_close == signal.fast_ema:
            continue
        entry_ts = start + pd.Timedelta(minutes=5)
        if entry_ts < DEV_START:
            continue
        minute_i = int(np.searchsorted(minute_times, entry_ts.to_datetime64()))
        if minute_i >= len(bars) or bars.ts.iloc[minute_i] != entry_ts:
            continue
        pos = int(np.searchsorted(hourly_times, entry_ts.to_datetime64(), side="right") - 1)
        if pos < 0:
            continue
        atr = float(hourly_known.atr14.iloc[pos])
        if not np.isfinite(atr) or atr <= 0:
            continue
        side = 1 if signal.mid_close > signal.fast_ema else -1
        entry_price = float(
            bars.ask_o.iloc[minute_i] if side > 0 else bars.bid_o.iloc[minute_i]
        )
        risk = float(params["stop_atr"]) * atr
        deadline = None
        if params["time_stop_days"] == 10 and session_index + 9 < len(sessions):
            deadline = sessions[session_index + 9][2]
        candidates.append(
            {
                "day": day,
                "entry_ts": entry_ts,
                "entry_i": minute_i,
                "entry_price": entry_price,
                "side": side,
                "risk": risk,
                "initial_stop": entry_price - side * risk,
                "initial_slow": float(hourly_known.slow_ema.iloc[pos]),
                "time_deadline": deadline,
            }
        )
    return candidates


def _stop_fill(row, side: int, stop: float) -> float | None:
    if side > 0:
        if float(row.bid_o) <= stop:
            return float(row.bid_o)
        if float(row.bid_l) <= stop:
            return stop
    else:
        if float(row.ask_o) >= stop:
            return float(row.ask_o)
        if float(row.ask_h) >= stop:
            return stop
    return None


def _fill_record(
    bars: pd.DataFrame,
    market: str,
    params: dict,
    candidate: dict,
    exit_i: int,
    exit_price: float,
    reason: str,
) -> dict:
    side = candidate["side"]
    entry_i = candidate["entry_i"]
    risk = candidate["risk"]
    entry = candidate["entry_price"]
    exit_row = bars.iloc[exit_i]
    entry_row = bars.iloc[entry_i]
    if market in CRYPTO:
        gross = side * (exit_price - entry) / risk
        net = gross - 0.0005 * (abs(entry) + abs(exit_price)) / risk
        net15 = gross - 0.00075 * (abs(entry) + abs(exit_price)) / risk
    else:
        entry_half = (float(entry_row.ask_o) - float(entry_row.bid_o)) / 2
        exit_half = (float(exit_row.ask_o) - float(exit_row.bid_o)) / 2
        mid_entry = entry - side * entry_half
        mid_exit = exit_price + side * exit_half
        gross = side * (mid_exit - mid_entry) / risk
        net = side * (exit_price - entry) / risk
        entry15 = mid_entry + side * 1.5 * entry_half
        exit15 = mid_exit - side * 1.5 * exit_half
        net15 = side * (exit15 - entry15) / risk
    return {
        "market": market,
        "strategy": "B",
        "params": dict(params),
        "period": "holdout" if candidate["entry_ts"] >= HOLDOUT_START else "dev",
        "side": side,
        "entry_ts": candidate["entry_ts"],
        "exit_ts": pd.Timestamp(exit_row.ts),
        "entry_price": entry,
        "exit_price": float(exit_price),
        "risk_points": risk,
        "gross_R": float(gross),
        "net_R": float(net),
        "net_R_cost15": float(net15),
        "exit_reason": reason,
    }


def _simulate_candidate(
    bars: pd.DataFrame,
    hourly: pd.DataFrame,
    market: str,
    params: dict,
    candidate: dict,
) -> dict | None:
    side = candidate["side"]
    initial_stop = candidate["initial_stop"]
    initial_slow = candidate.get("initial_slow", np.nan)
    active = bool(
        np.isfinite(initial_slow)
        and side * (float(initial_slow) - candidate["entry_price"]) > 0
    )
    trail = float(initial_slow) if active else None
    if trail is not None:
        trail = max(trail, initial_stop) if side > 0 else min(trail, initial_stop)
    hourly_times = hourly.known_at.to_numpy(dtype="datetime64[ns]")
    decision_i = int(
        np.searchsorted(hourly_times, candidate["entry_ts"].to_datetime64(), side="right")
    )
    for minute_i in range(candidate["entry_i"], len(bars)):
        minute = bars.iloc[minute_i]
        now = pd.Timestamp(minute.ts)
        close_exit = False
        while (
            decision_i < len(hourly)
            and hourly_times[decision_i] <= now.to_datetime64()
        ):
            hour = hourly.iloc[decision_i]
            decision_i += 1
            slow = float(hour.slow_ema)
            close = float(hour.mid_close)
            if not np.isfinite(slow):
                continue
            if not active and (
                side * (close - candidate["entry_price"]) >= candidate["risk"]
                or side * (slow - candidate["entry_price"]) > 0
            ):
                active = True
            if active:
                trail = slow if trail is None else (
                    max(trail, slow) if side > 0 else min(trail, slow)
                )
                trail = max(trail, initial_stop) if side > 0 else min(trail, initial_stop)
                if params["exit_mode"] == "close" and side * (close - trail) <= 0:
                    close_exit = True

        stop = initial_stop
        reason = "stop"
        if active and params["exit_mode"] == "touch" and trail is not None:
            stop = trail
            reason = "slow_ema_touch"
        stop_price = _stop_fill(minute, side, stop)
        if stop_price is not None:
            return _fill_record(
                bars, market, params, candidate, minute_i, stop_price, reason
            )
        if close_exit:
            price = float(minute.bid_o if side > 0 else minute.ask_o)
            return _fill_record(
                bars, market, params, candidate, minute_i, price, "slow_ema_close"
            )
        deadline = candidate["time_deadline"]
        if deadline is not None and now >= deadline:
            price = float(minute.bid_o if side > 0 else minute.ask_o)
            return _fill_record(
                bars, market, params, candidate, minute_i, price, "time_stop"
            )
    return None


def simulate(bars_1m: pd.DataFrame, market: str, params: dict) -> list[dict]:
    """Simulate Strategy B and return one shared-schema dictionary per closed trade."""
    bars = _validate(bars_1m, market, params)
    if bars.empty:
        return []
    five, hourly = _indicator_bars(
        bars, market, int(params["fast_ema"]), int(params["slow_ema"])
    )
    sessions = _complete_sessions(bars, market)
    candidates = _entry_candidates(bars, market, params, five, hourly, sessions)
    if params["overlap"] == "daily":
        completed = []
        for candidate in candidates:
            trade = _simulate_candidate(bars, hourly, market, params, candidate)
            if trade is not None:
                completed.append(trade)
        completed.sort(key=lambda trade: (trade["entry_ts"], trade["exit_ts"]))
        return completed
    selected = []
    next_entry = pd.Timestamp.min.tz_localize("UTC")
    for candidate in candidates:
        if candidate["entry_ts"] < next_entry:
            continue
        trade = _simulate_candidate(bars, hourly, market, params, candidate)
        if trade is None:
            break
        selected.append(trade)
        next_entry = trade["exit_ts"]
    return selected
