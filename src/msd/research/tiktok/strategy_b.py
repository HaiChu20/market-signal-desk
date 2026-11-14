"""Strategy B: first session candle versus fast EMA, managed by hourly EMA."""
from __future__ import annotations

import numpy as np
import pandas as pd

from msd.research.tiktok import common

PARAM_KEYS = {
    "fast_ema",
    "slow_ema",
    "stop_atr",
    "exit_mode",
    "overlap",
    "time_stop_days",
}
CRYPTO = common.CRYPTO_MARKETS
DEV_START = common.DEV_START
HOLDOUT_START = common.HOLDOUT_START


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


def _complete_sessions(
    bars: pd.DataFrame, market: str
) -> list[tuple[object, pd.Timestamp, pd.Timestamp]]:
    return [
        (session.session_id, session.start, session.end)
        for session in common.session_frames(bars, market, "rth")
        if session.complete
    ]


def _indicator_bars(bars: pd.DataFrame, market: str, fast: int, slow: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    del market  # All frozen markets use the same UTC-anchored closed-bar construction.
    five = common.resample_closed_bars(bars, 5)
    five["known_at"] = five.ts
    five["mid_close"] = (five.bid_c.to_numpy(float) + five.ask_c.to_numpy(float)) / 2
    five["fast_ema"] = five.mid_close.ewm(
        span=fast, adjust=False, min_periods=fast
    ).mean()

    hourly = common.resample_closed_bars(bars, 60)
    hourly["known_at"] = hourly.ts
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
    return five, hourly


def _entry_candidates(
    bars: pd.DataFrame,
    market: str,
    params: dict,
    five: pd.DataFrame,
    hourly: pd.DataFrame,
    sessions: list[tuple[object, pd.Timestamp, pd.Timestamp]],
) -> list[dict]:
    five_by_close = five.drop_duplicates("known_at", keep="last").set_index("known_at")
    hourly_known = hourly.sort_values("known_at")
    hourly_times = hourly_known.known_at.to_numpy(dtype="datetime64[ns]")
    minute_times = bars.ts.to_numpy(dtype="datetime64[ns]")
    candidates = []
    for session_index, (day, start, end) in enumerate(sessions):
        entry_ts = start + pd.Timedelta(minutes=5)
        if entry_ts not in five_by_close.index:
            continue
        signal = five_by_close.loc[entry_ts]
        if not np.isfinite(signal.fast_ema) or signal.mid_close == signal.fast_ema:
            continue
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


def _minute_arrays(bars: pd.DataFrame) -> dict[str, np.ndarray]:
    cached = bars.attrs.get("_strategy_b_minute_arrays")
    if cached is None or len(cached["ts"]) != len(bars):
        cached = {
            "ts": bars.ts.to_numpy(dtype="datetime64[ns]"),
            "bid_o": bars.bid_o.to_numpy(float, copy=False),
            "bid_l": bars.bid_l.to_numpy(float, copy=False),
            "ask_o": bars.ask_o.to_numpy(float, copy=False),
            "ask_h": bars.ask_h.to_numpy(float, copy=False),
        }
        bars.attrs["_strategy_b_minute_arrays"] = cached
    return cached


def _hourly_arrays(hourly: pd.DataFrame) -> dict[str, np.ndarray]:
    cached = hourly.attrs.get("_strategy_b_hourly_arrays")
    if cached is None or len(cached["known_at"]) != len(hourly):
        cached = {
            "known_at": hourly.known_at.to_numpy(dtype="datetime64[ns]"),
            "mid_close": hourly.mid_close.to_numpy(float, copy=False),
            "slow_ema": hourly.slow_ema.to_numpy(float, copy=False),
        }
        hourly.attrs["_strategy_b_hourly_arrays"] = cached
    return cached


def _utc_timestamp(value: np.datetime64) -> pd.Timestamp:
    return pd.Timestamp(value).tz_localize("UTC")


def _stop_fill_arrays(
    minute: dict[str, np.ndarray], index: int, side: int, stop: float
) -> float | None:
    if side > 0:
        if minute["bid_o"][index] <= stop:
            return float(minute["bid_o"][index])
        if minute["bid_l"][index] <= stop:
            return stop
    else:
        if minute["ask_o"][index] >= stop:
            return float(minute["ask_o"][index])
        if minute["ask_h"][index] >= stop:
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
    minute = _minute_arrays(bars)
    side = candidate["side"]
    entry_i = candidate["entry_i"]
    risk = candidate["risk"]
    entry = candidate["entry_price"]
    if market in CRYPTO:
        gross = side * (exit_price - entry) / risk
        net = gross - 0.0005 * (abs(entry) + abs(exit_price)) / risk
        net15 = gross - 0.00075 * (abs(entry) + abs(exit_price)) / risk
    else:
        entry_half = (minute["ask_o"][entry_i] - minute["bid_o"][entry_i]) / 2
        exit_half = (minute["ask_o"][exit_i] - minute["bid_o"][exit_i]) / 2
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
        "exit_ts": _utc_timestamp(minute["ts"][exit_i]),
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
    minute = _minute_arrays(bars)
    hour = _hourly_arrays(hourly)
    side = candidate["side"]
    initial_slow_key = candidate.get("initial_slow", np.nan)
    if not np.isfinite(initial_slow_key):
        initial_slow_key = None
    deadline_key = candidate.get("time_deadline")
    cache_key = (
        id(bars), market, tuple(sorted(params.items())), candidate["entry_i"], side,
        float(candidate["entry_price"]), float(candidate["risk"]),
        float(candidate["initial_stop"]), initial_slow_key, deadline_key,
    )
    outcome_cache = hourly.attrs.setdefault("_strategy_b_outcome_cache", {})
    if cache_key in outcome_cache:
        cached = outcome_cache[cache_key]
        return None if cached is None else dict(cached)

    def finish(record: dict | None) -> dict | None:
        outcome_cache[cache_key] = record
        return None if record is None else dict(record)

    initial_stop = candidate["initial_stop"]
    initial_slow = candidate.get("initial_slow", np.nan)
    active = bool(
        np.isfinite(initial_slow)
        and side * (float(initial_slow) - candidate["entry_price"]) > 0
    )
    trail = float(initial_slow) if active else None
    if trail is not None:
        trail = max(trail, initial_stop) if side > 0 else min(trail, initial_stop)
    hourly_times = hour["known_at"]
    decision_i = int(
        np.searchsorted(hourly_times, candidate["entry_ts"].to_datetime64(), side="right")
    )
    for minute_i in range(candidate["entry_i"], len(bars)):
        now = minute["ts"][minute_i]
        close_exit = False
        while (
            decision_i < len(hourly)
            and hourly_times[decision_i] <= now
        ):
            slow = float(hour["slow_ema"][decision_i])
            close = float(hour["mid_close"][decision_i])
            decision_i += 1
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
        stop_price = _stop_fill_arrays(minute, minute_i, side, stop)
        if stop_price is not None:
            return finish(
                _fill_record(
                    bars, market, params, candidate, minute_i, stop_price, reason
                )
            )
        if close_exit:
            price = float(
                minute["bid_o"][minute_i] if side > 0 else minute["ask_o"][minute_i]
            )
            return finish(
                _fill_record(
                    bars, market, params, candidate, minute_i, price, "slow_ema_close"
                )
            )
        deadline = candidate["time_deadline"]
        if deadline is not None and now >= deadline.to_datetime64():
            price = float(
                minute["bid_o"][minute_i] if side > 0 else minute["ask_o"][minute_i]
            )
            return finish(
                _fill_record(
                    bars, market, params, candidate, minute_i, price, "time_stop"
                )
            )
    return finish(None)


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
