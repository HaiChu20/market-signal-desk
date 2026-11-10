"""Causal session levels and features for rule candidates."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

NY = "America/New_York"
PIVOT_SIDES = 3
ATR_BARS = 14
EMA_FAST = 20
EMA_SLOW = 50
RSI_BARS = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
REALIZED_VOL_BARS = 30
VOLUME_SESSIONS = 20
OPENING_RANGE_MINUTES = 15
FEATURE_NAMES = (
    "minutes_since_open", "weekday", "price_vs_vwap_atr", "atr_over_price", "realized_vol_30m",
    "ema20_slope_5m", "ema50_slope_5m", "ema20_slope_60m", "ema50_slope_60m",
    "rsi14_5m", "macd_hist_5m", "nr4", "nr7", "inside_day", "gap_atr",
    "position_prior_range", "spread_atr", "sl_distance_atr", "tp_sl_ratio", "volume_vs_20_session_median",
    *(f"distance_{name}_atr" for name in ("pdh", "pdl", "onh", "onl", "orh", "orl", "swing_high", "swing_low")),
    *(f"distance_swing_{kind}_{k}_atr" for k in range(1, 4) for kind in ("high", "low")),
)


def confirmed_swings(high: np.ndarray, low: np.ndarray, sides: int = PIVOT_SIDES) -> tuple[np.ndarray, np.ndarray]:
    """Event at i is the pivot from i-sides, confirmed by bar i's close."""
    h = pd.Series(high)
    l = pd.Series(low)
    width = 2 * sides + 1
    peaks = h.where(h.eq(h.rolling(width, center=True, min_periods=width).max())).shift(sides).to_numpy()
    troughs = l.where(l.eq(l.rolling(width, center=True, min_periods=width).min())).shift(sides).to_numpy()
    return peaks, troughs


def _last_events(events: np.ndarray, count: int = 3) -> list[np.ndarray]:
    where = np.flatnonzero(np.isfinite(events))
    pos = np.searchsorted(where, np.arange(len(events)), side="right") - 1
    out = []
    for k in range(count):
        idx = pos - k
        values = np.full(len(events), np.nan)
        valid = idx >= 0
        values[valid] = events[where[idx[valid]]]
        out.append(values)
    return out


def _resampled(mid_o: np.ndarray, mid_h: np.ndarray, mid_l: np.ndarray, mid_c: np.ndarray, volume: np.ndarray,
               ts: pd.Series, minutes: int) -> pd.DataFrame:
    raw = pd.DataFrame({"o": mid_o, "h": mid_h, "l": mid_l, "c": mid_c, "v": volume}, index=pd.DatetimeIndex(ts))
    bars = raw.resample(f"{minutes}min").agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"})
    count = raw.o.resample(f"{minutes}min").count()
    bars.loc[count < minutes, ["o", "h", "l", "c"]] = np.nan
    bars["decision_ts"] = bars.index + pd.Timedelta(minutes=minutes - 1)
    return bars


@dataclass
class Context:
    bars: pd.DataFrame
    symbol: str
    ts: np.ndarray
    mid_o: np.ndarray
    mid_h: np.ndarray
    mid_l: np.ndarray
    mid_c: np.ndarray
    volume: np.ndarray
    minute: np.ndarray
    weekday: np.ndarray
    session_id: np.ndarray
    session_end: np.ndarray
    session_first: np.ndarray
    session_last: np.ndarray
    levels: dict[str, np.ndarray]
    vwap: np.ndarray
    atr: np.ndarray
    five: pd.DataFrame
    five_pos: np.ndarray
    hour: pd.DataFrame
    hour_pos: np.ndarray
    vol30: np.ndarray
    nr4: np.ndarray
    nr7: np.ndarray
    inside: np.ndarray
    gap: np.ndarray
    volume_grid: np.ndarray
    index_market: bool

    def snapshot(self, i: int, stop: float, tp: float, side: int) -> dict:
        atr = self.atr[i]
        if not np.isfinite(atr) or atr <= 0:
            atr = np.nan
        price = self.mid_c[i]
        d = int(self.session_id[i])
        f = int(self.five_pos[i])
        h = int(self.hour_pos[i])
        value = lambda frame, pos, name: float(frame[name].iat[pos]) if pos >= 0 else np.nan
        features = {
            "minutes_since_open": int(self.minute[i]), "weekday": int(self.weekday[i]),
            "price_vs_vwap_atr": (price - self.vwap[i]) / atr,
            "atr_over_price": atr / price, "realized_vol_30m": self.vol30[i],
            "ema20_slope_5m": value(self.five, f, "ema20_slope"),
            "ema50_slope_5m": value(self.five, f, "ema50_slope"),
            "ema20_slope_60m": value(self.hour, h, "ema20_slope"),
            "ema50_slope_60m": value(self.hour, h, "ema50_slope"),
            "rsi14_5m": value(self.five, f, "rsi"),
            "macd_hist_5m": value(self.five, f, "macd_hist"),
            "nr4": bool(self.nr4[d]), "nr7": bool(self.nr7[d]), "inside_day": bool(self.inside[d]),
            "gap_atr": self.gap[d] / atr,
            "position_prior_range": (price - self.levels["pdl"][i]) / (self.levels["pdh"][i] - self.levels["pdl"][i]),
            "spread_atr": (self.bars.ask_c.iat[i] - self.bars.bid_c.iat[i]) / atr,
            "sl_distance_atr": abs(price - stop) / atr,
            "tp_sl_ratio": abs(tp - price) / abs(price - stop) if price != stop else np.nan,
        }
        values = self.volume_grid[max(0, d - VOLUME_SESSIONS):d, self.minute[i]]
        values = values[np.isfinite(values)]
        features["volume_vs_20_session_median"] = self.volume[i] / np.median(values) if len(values) == VOLUME_SESSIONS and np.median(values) > 0 else np.nan
        for name, level in self.levels.items():
            features[f"distance_{name}_atr"] = (price - level[i]) / atr
        for k in range(1, 4):
            for kind in ("high", "low"):
                features[f"distance_swing_{kind}_{k}_atr"] = (price - value(self.five, f, f"swing_{kind}_{k}")) / atr
        return features


def prepare(bars: pd.DataFrame, symbol: str) -> Context:
    bars = bars.sort_values("ts").reset_index(drop=True)
    n = len(bars)
    index_market = symbol != "BTCUSDT"
    ts = bars.ts.dt.tz_localize(None).to_numpy()
    mid_o = ((bars.bid_o + bars.ask_o) / 2).to_numpy()
    mid_h = ((bars.bid_h + bars.ask_h) / 2).to_numpy()
    mid_l = ((bars.bid_l + bars.ask_l) / 2).to_numpy()
    mid_c = ((bars.bid_c + bars.ask_c) / 2).to_numpy()
    volume = bars.volume.to_numpy(dtype=float)
    local = bars.ts.dt.tz_convert(NY if index_market else "UTC")
    clock_minute = (local.dt.hour * 60 + local.dt.minute).to_numpy(dtype=int)
    weekday = local.dt.day_of_week.to_numpy(dtype=int)
    trade = (clock_minute >= 570) & (clock_minute < 960) & (weekday < 5) if index_market else np.ones(n, dtype=bool)
    trade_idx = np.flatnonzero(trade)
    days = local.dt.date.to_numpy()[trade_idx]
    codes, unique_days = pd.factorize(days, sort=True)
    session_id = np.full(n, -1, dtype=np.int32)
    session_id[trade_idx] = codes
    minute = clock_minute - 570 if index_market else clock_minute
    grid = np.full((len(unique_days), 390 if index_market else 1440), np.nan, dtype=np.float32)
    grid[codes, minute[trade_idx]] = volume[trade_idx]
    fields = ("pdh", "pdl", "onh", "onl", "orh", "orl", "swing_high", "swing_low")
    levels = {name: np.full(n, np.nan) for name in fields}
    vwap = np.full(n, np.nan)
    session_end = np.empty(len(unique_days), dtype="datetime64[ns]")
    session_first = np.empty(len(unique_days), dtype=np.int64)
    session_last = np.empty(len(unique_days), dtype=np.int64)
    day_high = np.full(len(unique_days), np.nan)
    day_low = np.full(len(unique_days), np.nan)
    day_close = np.full(len(unique_days), np.nan)
    day_open = np.full(len(unique_days), np.nan)
    gap = np.full(len(unique_days), np.nan)
    starts = np.r_[0, np.flatnonzero(np.diff(codes)) + 1]
    ends = np.r_[starts[1:], len(trade_idx)]
    for d, (a, b) in enumerate(zip(starts, ends)):
        ix = trade_idx[a:b]
        if not len(ix):
            continue
        day = unique_days[d]
        session_first[d], session_last[d] = ix[0], ix[-1]
        session_end[d] = (pd.Timestamp(f"{day} 16:00", tz=NY).tz_convert("UTC").tz_localize(None).to_datetime64()
                          if index_market else np.datetime64(pd.Timestamp(day) + pd.Timedelta(days=1)))
        day_high[d], day_low[d], day_close[d], day_open[d] = max(mid_h[ix]), min(mid_l[ix]), mid_c[ix[-1]], mid_o[ix[0]]
        cvol = np.cumsum(volume[ix])
        vwap[ix] = np.cumsum(mid_c[ix] * volume[ix]) / np.where(cvol > 0, cvol, np.nan)
        if d:
            levels["pdh"][ix] = day_high[d - 1]
            levels["pdl"][ix] = day_low[d - 1]
            gap[d] = day_open[d] - day_close[d - 1]
            if index_market:
                prev_end = pd.Timestamp(f"{unique_days[d - 1]} 16:00", tz=NY).tz_convert("UTC").tz_localize(None).to_datetime64()
                left = np.searchsorted(ts, prev_end)
                right = np.searchsorted(ts, ts[ix[0]])
                if right > left:
                    levels["onh"][ix] = np.max(mid_h[left:right])
                    levels["onl"][ix] = np.min(mid_l[left:right])
        if index_market:
            opening = ix[minute[ix] < OPENING_RANGE_MINUTES]
            if len(opening) == OPENING_RANGE_MINUTES and minute[opening[0]] == 0:
                ready = ix[minute[ix] >= OPENING_RANGE_MINUTES - 1]
                levels["orh"][ready] = np.max(mid_h[opening])
                levels["orl"][ready] = np.min(mid_l[opening])
    ranges = day_high - day_low
    nr4 = np.zeros(len(unique_days), dtype=bool)
    nr7 = np.zeros(len(unique_days), dtype=bool)
    inside = np.zeros(len(unique_days), dtype=bool)
    for d in range(len(unique_days)):
        if d >= 4:
            nr4[d] = ranges[d - 1] <= min(ranges[d - 4:d])
        if d >= 7:
            nr7[d] = ranges[d - 1] <= min(ranges[d - 7:d])
        if d >= 2:
            inside[d] = day_high[d - 1] < day_high[d - 2] and day_low[d - 1] > day_low[d - 2]
    five = _resampled(mid_o, mid_h, mid_l, mid_c, volume, bars.ts, 5)
    prev = five.c.shift(1)
    tr = pd.concat([five.h - five.l, (five.h - prev).abs(), (five.l - prev).abs()], axis=1).max(axis=1)
    five["atr"] = tr.rolling(ATR_BARS, min_periods=ATR_BARS).mean()
    peaks, troughs = confirmed_swings(five.h.to_numpy(), five.l.to_numpy())
    for kind, events in (("high", peaks), ("low", troughs)):
        for k, values in enumerate(_last_events(events), 1):
            five[f"swing_{kind}_{k}"] = values
    delta = five.c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / RSI_BARS, adjust=False, min_periods=RSI_BARS).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / RSI_BARS, adjust=False, min_periods=RSI_BARS).mean()
    five["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    macd = five.c.ewm(span=MACD_FAST, adjust=False).mean() - five.c.ewm(span=MACD_SLOW, adjust=False).mean()
    five["macd_hist"] = macd - macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
    hour = _resampled(mid_o, mid_h, mid_l, mid_c, volume, bars.ts, 60)
    for frame in (five, hour):
        for span in (EMA_FAST, EMA_SLOW):
            ema = frame.c.ewm(span=span, adjust=False, min_periods=span).mean()
            frame[f"ema{span}_slope"] = ema.diff() / frame.c
    five_pos = np.searchsorted(five.decision_ts.dt.tz_localize(None).to_numpy(), ts, side="right") - 1
    hour_pos = np.searchsorted(hour.decision_ts.dt.tz_localize(None).to_numpy(), ts, side="right") - 1
    valid = five_pos >= 0
    atr = np.full(n, np.nan)
    atr[valid] = five.atr.to_numpy()[five_pos[valid]]
    for name in ("swing_high", "swing_low"):
        kind = name.split("_")[1]
        levels[name][valid] = five[f"swing_{kind}_1"].to_numpy()[five_pos[valid]]
    vol30 = pd.Series(mid_c).pct_change(fill_method=None).rolling(REALIZED_VOL_BARS).std().to_numpy()
    return Context(bars, symbol, ts, mid_o, mid_h, mid_l, mid_c, volume, minute, weekday, session_id, session_end, session_first, session_last,
                   levels, vwap, atr, five, five_pos, hour, hour_pos, vol30, nr4, nr7, inside, gap, grid, index_market)
