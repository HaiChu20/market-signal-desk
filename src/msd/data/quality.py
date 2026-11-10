"""Yearly quality checks for New York cash-session CFD minute bars."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from msd.data import load
from msd.data.dukascopy import PRICE_BANDS, SCALES

MIN_OPEN_COVERAGE = 0.95
MIN_MEDIAN_BARS = 380
MAX_ZERO_SPREAD = 0.05
GAP_MISSING_FREQUENCY = 0.20
MIN_GAP_WINDOW_MINUTES = 5
NY = "America/New_York"
QUALITY_COLUMNS = ["year", "sessions", "median_bars", "open_coverage", "median_spread", "zero_spread", "ask_below_bid", "usable", "median_full_day_bars", "missing_in_hours", "longest_in_hours_gap", "typical_weekday_gap_windows"]


def _empty_quality() -> pd.DataFrame:
    return pd.DataFrame(columns=QUALITY_COLUMNS)


def analyze(bars: pd.DataFrame, hours: str = "cme_equity") -> pd.DataFrame:
    if bars.empty or not {"ts", "bid_o", "ask_o"}.issubset(bars.columns):
        return _empty_quality()
    full_source = bars.copy()
    bars = bars[["ts", "bid_o", "ask_o"]].copy()
    bars["ts"] = pd.to_datetime(bars.ts, utc=True, errors="coerce")
    bars = bars.dropna(subset=["ts"])
    if bars.empty:
        return _empty_quality()
    local = bars.ts.dt.tz_convert(NY)
    minute = local.dt.hour * 60 + local.dt.minute
    cash = bars.loc[(local.dt.day_of_week < 5) & (minute >= 570) & (minute < 960), ["ts", "bid_o", "ask_o"]].copy()
    times = cash.ts.dt.tz_convert(NY)
    cash["day"] = times.dt.date
    cash["year"] = times.dt.year
    cash["at_open"] = (times.dt.hour == 9) & (times.dt.minute == 30)
    cash["spread"] = cash.ask_o - cash.bid_o
    sessions = cash.groupby(["year", "day"], sort=True).agg(bars=("ts", "size"), open=("at_open", "max"))
    rows = []
    for year, group in cash.groupby("year", sort=True):
        day_group = sessions.loc[year]
        spread = group.spread.to_numpy(float)
        row = dict(year=int(year), sessions=len(day_group), median_bars=float(day_group.bars.median()),
                   open_coverage=float(day_group.open.mean()), median_spread=float(np.median(spread)),
                   zero_spread=float(np.mean(np.isclose(spread, 0, atol=1e-9))),
                   ask_below_bid=float(np.mean(spread < 0)))
        row["usable"] = (row["open_coverage"] >= MIN_OPEN_COVERAGE and row["median_bars"] >= MIN_MEDIAN_BARS
                         and row["zero_spread"] <= MAX_ZERO_SPREAD)
        rows.append(row)
    quality = pd.DataFrame(rows, columns=QUALITY_COLUMNS[:8])
    full_rows = []
    if {"ts", "volume"}.issubset(full_source.columns):
        all_bars = full_source[["ts"]].copy()
        all_bars["ts"] = pd.to_datetime(all_bars.ts, utc=True, errors="coerce")
        all_bars = all_bars.dropna().sort_values("ts")
        if not all_bars.empty:
            full_tz = "UTC" if hours == "24x7" else NY
            local_all = all_bars.ts.dt.tz_convert(full_tz)
            all_bars["year"] = local_all.dt.year
            all_bars["day"] = local_all.dt.date
            all_bars["minute"] = local_all.dt.hour * 60 + local_all.dt.minute
            first_day, last_day = all_bars.day.min(), all_bars.day.max()
            observed_by_day = {day: rows.minute.to_numpy(int) for day, rows in all_bars.groupby("day", sort=True)}
            for year in range(first_day.year, last_day.year + 1):
                year_start = max(first_day, pd.Timestamp(f"{year}-01-01").date())
                year_end = min(last_day, pd.Timestamp(f"{year}-12-31").date())
                day_counts, expected, observed = [], 0, 0
                longest = 0
                run = 0
                for day_ts in pd.date_range(year_start, year_end, freq="D"):
                    day = day_ts.date()
                    weekday = day.weekday()
                    if hours == "24x7":
                        exp = 1440
                        eligible = np.ones(1440, dtype=bool)
                    elif hours == "cme_equity":
                        exp = 360 if weekday == 6 else 1020 if weekday == 4 else 1380 if weekday < 5 else 0
                        eligible = np.zeros(1440, dtype=bool)
                        if weekday == 6:
                            eligible[18*60:] = True
                        elif weekday < 5:
                            eligible[:17*60] = True
                            if weekday < 4:
                                eligible[18*60:] = True
                    else:
                        raise ValueError("hours must be cme_equity or 24x7")
                    if not exp:
                        continue
                    seen = np.zeros(1440, dtype=bool)
                    mins = observed_by_day.get(day, np.array([], dtype=int))
                    mins = mins[(mins >= 0) & (mins < 1440)]
                    seen[mins] = True
                    missing = eligible & ~seen
                    expected += exp
                    observed += int((eligible & seen).sum())
                    day_counts.append(int((eligible & seen).sum()))
                    for eligible_minute, miss in zip(eligible, missing):
                        if not eligible_minute:
                            run = 0
                            continue
                        run = run + 1 if miss else 0
                        longest = max(longest, run)
                hist_expected = np.zeros(1440, dtype=np.int32)
                hist_missing = np.zeros(1440, dtype=np.int32)
                for day_ts in pd.date_range(year_start, year_end, freq="D"):
                    day = day_ts.date()
                    weekday = day.weekday()
                    if weekday >= 5:
                        continue
                    eligible = np.ones(1440, dtype=bool) if hours == "24x7" else np.r_[np.ones(17*60, dtype=bool), np.zeros(60, dtype=bool), np.ones(6*60, dtype=bool)] if weekday < 4 else np.r_[np.ones(17*60, dtype=bool), np.zeros(7*60, dtype=bool)]
                    seen = np.zeros(1440, dtype=bool)
                    mins = observed_by_day.get(day, np.array([], dtype=int))
                    mins = mins[(mins >= 0) & (mins < 1440)]
                    seen[mins] = True
                    hist_expected += eligible
                    hist_missing += eligible & ~seen
                frequency = np.divide(hist_missing, hist_expected, out=np.zeros(1440, dtype=float), where=hist_expected > 0)
                gap_mask = (hist_expected > 0) & (frequency >= GAP_MISSING_FREQUENCY)
                gap_windows = []
                index = 0
                while index < 1440:
                    if not gap_mask[index]:
                        index += 1
                        continue
                    finish = index + 1
                    while finish < 1440 and gap_mask[finish]:
                        finish += 1
                    if finish - index >= MIN_GAP_WINDOW_MINUTES:
                        start_label = f"{index//60:02d}:{index%60:02d}"
                        end_label = f"{finish//60:02d}:{finish%60:02d}"
                        gap_windows.append(f"{start_label}-{end_label} ({frequency[index:finish].mean():.0%})")
                    index = finish
                full_rows.append({"year": int(year), "median_full_day_bars": float(np.median(day_counts)) if day_counts else float("nan"),
                                  "missing_in_hours": 1 - observed / expected if expected else float("nan"),
                                  "longest_in_hours_gap": longest, "typical_weekday_gap_windows": "; ".join(gap_windows) if gap_windows else "none"})
    if full_rows:
        quality = quality.merge(pd.DataFrame(full_rows), on="year", how="outer")
    if "usable" in quality:
        quality["usable"] = quality["usable"].fillna(False).astype(bool)
    for col in QUALITY_COLUMNS:
        if col not in quality:
            quality[col] = np.nan
    return quality[QUALITY_COLUMNS]


def contiguous_usable_years(quality: pd.DataFrame) -> list[int]:
    """Use the longest consecutive usable run; prefer the later run on ties."""
    years = sorted(quality.loc[quality.usable.fillna(False).astype(bool), "year"].astype(int)) if not quality.empty else []
    runs: list[list[int]] = []
    for year in years:
        if not runs or year != runs[-1][-1] + 1:
            runs.append([year])
        else:
            runs[-1].append(year)
    return max(runs, key=lambda run: (len(run), run[-1]), default=[])


def write_report(symbol: str, bars: pd.DataFrame | None = None, hours: str | None = None) -> str:
    if bars is None:
        bars = load(symbol, "1900-01-01", "2100-01-01")
    if hours is None:
        hours = "24x7" if symbol in {"BTCUSDT", "BTCUSD", "NSXUSD", "SPXUSD"} else "cme_equity"
    if symbol in {"NSXUSD", "SPXUSD", "GRXEUR", "WTIUSD"}:
        if bars.empty:
            years = []
            ny = pd.Series([], dtype="datetime64[ns, America/New_York]")
        else:
            ny = pd.to_datetime(bars.ts, utc=True).dt.tz_convert(NY)
            years = sorted(ny.dt.year.unique())
        lines = [f"# Data quality — {symbol}", "", "Source wall times use the New York clock, but the DST switch dates follow the EU calendar (last Sunday in March/October). Relative to a New York-zone conversion, +60 minutes is applied in the U.S./EU transition windows. Ambiguous fall-back rows use chronological fold order; nonexistent spring-forward rows are dropped and counted below. HistData volume is unavailable and stored as NaN; no volume-dependent features should use it.", "",
                 "## Full-day weekday coverage by NY hour", "", "Counts are observed minute bars / expected weekday minutes in each calendar year.", "",
                 "| Year | Median weekday bars | " + " | ".join(f"{hour:02d}" for hour in range(24)) + " |",
                 "|---:|---:|" + "---:|" * 24]
        if years:
            details = pd.DataFrame({"year": ny.dt.year, "weekday": ny.dt.day_of_week, "hour": ny.dt.hour, "day": ny.dt.date})
            details = details[details.weekday < 5]
            hourly = details.groupby(["year", "hour"]).size()
            daily = details.groupby(["year", "day"]).size().groupby("year").median()
            for year in years:
                weekdays = len(pd.bdate_range(f"{year}-01-01", f"{year}-12-31"))
                vals = [f"{int(hourly.get((year, hour), 0))}/{weekdays * 60}" for hour in range(24)]
                lines.append(f"| {year} | {daily.get(year, float('nan')):.0f} | " + " | ".join(vals) + " |")
        from msd.data.histdata import gap_report_summary
        gaps = gap_report_summary(symbol)
        lines += ["", "## Retained ZIP gap-report summary", ""]
        lines.extend(f"- {item}" for item in gaps) if gaps else lines.append("No gap-report text files found in retained archives.")
        text = "\n".join(lines) + "\n"
        path = Path(f"reports/data/data_quality_{symbol}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return text
    quality = analyze(bars, hours=hours)
    years = contiguous_usable_years(quality)
    lines = [f"# Data quality — {symbol}", "", f"Usable contiguous years: {years[0]}–{years[-1]}" if years else "Usable contiguous years: none",
             "", f"Thresholds: 09:30 coverage ≥ {MIN_OPEN_COVERAGE:.0%}; median cash bars ≥ {MIN_MEDIAN_BARS}; zero-spread minutes ≤ {MAX_ZERO_SPREAD:.0%}.", "",
             f"Full-day hours: {hours}; weekday gap-window clock: {'UTC' if hours == '24x7' else 'America/New_York'}.", "",
             "| Year | NY sessions | Median cash bars | 09:30 present | Median spread | Zero spread | Ask < bid | Usable | Median full-day bars | Missing in-hours | Longest gap (min) | Typical weekday gap windows |",
             "|---:|---:|---:|---:|---:|---:|---:|:---:|---:|---:|---:|---|"]
    for row in quality.itertuples(index=False):
        lines.append(f"| {row.year} | {row.sessions} | {row.median_bars:.0f} | {row.open_coverage:.1%} | {row.median_spread:.3f} | {row.zero_spread:.1%} | {row.ask_below_bid:.2%} | {'yes' if row.usable else 'no'} | {row.median_full_day_bars:.0f} | {row.missing_in_hours:.1%} | {row.longest_in_hours_gap:.0f} | {row.typical_weekday_gap_windows} |")
    if symbol in {"NSXUSD", "SPXUSD"} and not bars.empty:
        stamps = pd.to_datetime(bars.ts, utc=True).dt.tz_convert(NY)
        hourly = pd.DataFrame({"year": stamps.dt.year, "weekday": stamps.dt.dayofweek,
                               "hour": stamps.dt.hour}).query("weekday < 5")
        counts = hourly.groupby(["year", "hour"]).size()
        hourly_rows = []
        for year in sorted(hourly.year.unique()):
            weekdays = len(pd.bdate_range(f"{year}-01-01", f"{year}-12-31"))
            pieces = [f"{hour:02d}:00 {int(counts.get((year, hour), 0))}/{weekdays * 60}" for hour in range(24)]
            hourly_rows.append(f"| {year} | " + " | ".join(pieces) + " |")
        lines += ["", "## HistData full-day NY-hour coverage (observed bars / expected weekday minutes)", "",
                  "| Year | " + " | ".join(f"{hour:02d}" for hour in range(24)) + " |",
                  "|---:|" + "---:|" * 24]
        lines.extend(hourly_rows)
        from msd.data.histdata import gap_report_summary
        gap_lines = gap_report_summary(symbol)
        lines += ["", "## HistData ZIP gap-report summary", ""]
        lines.extend(f"- {entry}" for entry in gap_lines) if gap_lines else lines.append("No gap-report text files found in retained archives.")
    text = "\n".join(lines) + "\n"
    path = Path(f"reports/data/data_quality_{symbol}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True, choices=(*SCALES, *PRICE_BANDS, "BTCUSDT", "ETHUSDT", "NSXUSD", "SPXUSD", "GRXEUR", "WTIUSD"))
    parser.add_argument("--hours", choices=("cme_equity", "24x7"))
    args = parser.parse_args()
    print(write_report(args.symbol, hours=args.hours))


if __name__ == "__main__":
    main()
