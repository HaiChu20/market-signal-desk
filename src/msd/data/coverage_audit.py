"""Audit Dukascopy minute coverage against a DST-aware recent local schedule."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from msd.data.dukascopy import PRICE_BANDS, SCALES
from msd.data.stage8_download import DUKASCOPY_START

ROOT = Path("/Users/bfhach/Projects/market-signal-desk")
REPORTS = Path("reports/data")
ZONES = {
    "USA30IDXUSD": "America/New_York", "USA500IDXUSD": "America/New_York",
    "USATECHIDXUSD": "America/New_York", "DEUIDXEUR": "Europe/Berlin",
    "GBRIDXGBP": "Europe/London", "JPNIDXJPY": "Asia/Tokyo",
    "LIGHTCMDUSD": "America/New_York", "BRENTCMDUSD": "Europe/London",
    "BTCUSD": "UTC", "ETHUSD": "UTC", "XAUUSD": "UTC", "XAGUSD": "UTC",
    "EURUSD": "UTC", "USDJPY": "UTC", "GBPUSD": "UTC",
}
COLUMNS = ["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]


def calendar_hours(month: str, zone: str) -> pd.DataFrame:
    year, number = map(int, month.split("-"))
    start = pd.Timestamp(year, number, 1, tz="UTC")
    end = start + pd.offsets.MonthBegin(1)
    utc = pd.date_range(start, end, freq="h", inclusive="left")
    local = utc.tz_convert(zone)
    result = pd.DataFrame({"day": local.strftime("%Y-%m-%d"), "hour": local.hour,
                           "how": local.day_of_week * 24 + local.hour})
    return result.drop_duplicates(["day", "hour"])


def observed_hours(ts: pd.Series, zone: str) -> pd.DataFrame:
    local = ts.dt.tz_convert(zone)
    result = pd.DataFrame({"day": local.dt.strftime("%Y-%m-%d"), "hour": local.dt.hour,
                           "how": local.dt.day_of_week * 24 + local.dt.hour})
    return result.groupby(["day", "hour", "how"], as_index=False).size()


def schedule_profile(month_ts: dict[str, pd.Series], zone: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    recent = sorted(month_ts)[-24:]
    observed = np.zeros(168, dtype=float)
    possible = np.zeros(168, dtype=float)
    occupied = np.zeros(168, dtype=float)
    for month in recent:
        obs = observed_hours(month_ts[month], zone)
        cal = calendar_hours(month, zone)
        observed += np.bincount(obs.how, weights=obs["size"], minlength=168)
        occupied += np.bincount(obs.how, minlength=168)
        possible += np.bincount(cal.how, minlength=168)
    minutes_per_calendar_hour = np.divide(observed, possible, out=np.zeros(168), where=possible > 0)
    occupancy = np.divide(occupied, possible, out=np.zeros(168), where=possible > 0)
    return minutes_per_calendar_hour, occupancy, recent


def recommend_start(months: list[dict], blocked_years: set[int] | None = None) -> tuple[str | None, str]:
    """Drop persistent hour-of-week gaps, rather than seasonal holiday dips."""
    if not months:
        return None, "no complete months"
    last_regime_end = -1
    for index in range(2, len(months)):
        common = set(months[index - 2]["missing_profile_slots"])
        common.intersection_update(months[index - 1]["missing_profile_slots"])
        common.intersection_update(months[index]["missing_profile_slots"])
        if len(common) >= 6:
            last_regime_end = index
    first = max(0, last_regime_end + 1)
    blocked_years = blocked_years or set()
    if blocked_years:
        latest_bad_year = max(blocked_years)
        first = max(first, next((i for i, row in enumerate(months)
                                 if int(row["month"][:4]) > latest_bad_year), len(months)))
    while first < len(months):
        years: dict[str, list[dict]] = defaultdict(list)
        for row in months[first:]:
            years[row["month"][:4]].append(row)
        yearly_rates = [sum(row["observed_minutes"] for row in rows) /
                        sum(row["expected_minutes"] for row in rows)
                        for rows in years.values() if sum(row["expected_minutes"] for row in rows)]
        if yearly_rates and min(yearly_rates) >= 0.98:
            break
        next_year = str(int(months[first]["month"][:4]) + 1)
        first = next((i for i, row in enumerate(months) if row["month"].startswith(next_year)), len(months))
    if first == len(months):
        return None, "no era has at least 98% recent-schedule minute coverage in every later calendar year"
    return months[first]["month"] + "-01", (
        f"First month after the last persistent (3-month) gap in at least six identical local hour-of-week slots; "
        f"years with nonpositive spreads or price-band hits are excluded; each subsequent calendar year or partial year covers at least 98% of the recent schedule, and all later complete months combined cover "
        f"{sum(row['observed_minutes'] for row in months[first:]) / sum(row['expected_minutes'] for row in months[first:]):.2%} "
        f"of the DST-aware recent schedule. Isolated holiday dips remain visible in the monthly table.")


def _log_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def audit_symbol(symbol: str, root: Path = ROOT) -> dict:
    if symbol not in ZONES:
        raise ValueError(f"no native-market timezone configured for {symbol}")
    zone = ZONES[symbol]
    source = root / "data/bars/dukascopy" / symbol
    paths = sorted(source.glob("????-??.parquet"))
    complete = [path for path in paths if (pq.read_metadata(path).metadata or {}).get(b"msd_complete") == b"1"]
    if not complete:
        raise ValueError(f"no complete Dukascopy months for {symbol}")
    month_ts: dict[str, pd.Series] = {}
    flat = Counter(); stale_runs = Counter(); max_stale = 0
    nonpositive = Counter(); bad_ticks = Counter(); band_hits_year = Counter(); year_spreads: dict[int, list[np.ndarray]] = defaultdict(list)
    low_price = float("inf"); high_price = float("-inf"); band_hits = 0
    scale_info_path = root / "data/aux/point_scales.json"
    scale_info = json.loads(scale_info_path.read_text()).get(symbol, {}) if scale_info_path.exists() else {}
    band = scale_info.get("price_band", PRICE_BANDS.get(symbol))
    sample_day = scale_info.get("sample_day")
    sample_reference = scale_info.get("median_price")
    sample_bar_median = None
    for path in complete:
        table = pq.read_table(path)
        columns = [column for column in COLUMNS + ["bad_tick"] if column in table.column_names]
        frame = table.select(columns).to_pandas().sort_values("ts")
        ts = pd.to_datetime(frame.ts, utc=True)
        month_ts[path.stem] = ts
        if frame.empty:
            continue
        year = int(path.stem[:4])
        bid = frame.bid_c.to_numpy(dtype=float); ask = frame.ask_c.to_numpy(dtype=float)
        spread = ask - bid
        year_spreads[year].append(spread[np.isfinite(spread)])
        nonpositive[year] += int(np.sum(spread <= 0))
        if "bad_tick" in frame:
            bad_ticks[year] += int(frame.bad_tick.fillna(False).sum())
        flat[year] += int(((frame.bid_o == frame.bid_h) & (frame.bid_h == frame.bid_l) &
                           (frame.bid_l == frame.bid_c) & (frame.ask_o == frame.ask_h) &
                           (frame.ask_h == frame.ask_l) & (frame.ask_l == frame.ask_c)).sum())
        unchanged = (np.r_[False, (bid[1:] == bid[:-1]) & (ask[1:] == ask[:-1])] &
                     ts.diff().eq(pd.Timedelta(minutes=1)).to_numpy())
        run = 0
        for item in unchanged:
            run = run + 1 if item else 0
            max_stale = max(max_stale, run + 1 if run else 0)
            if run == 4:
                stale_runs[year] += 1
        low_price = min(low_price, float(np.nanmin(frame[["bid_l", "ask_l"]].to_numpy())))
        high_price = max(high_price, float(np.nanmax(frame[["bid_h", "ask_h"]].to_numpy())))
        if band:
            hits = int(((frame.bid_l <= band[0]) | (frame.ask_h >= band[1])).sum())
            band_hits += hits
            band_hits_year[year] += hits
        if sample_day and path.stem == sample_day[:7]:
            selected = frame.loc[ts.dt.strftime("%Y-%m-%d").eq(sample_day), "bid_c"]
            if len(selected):
                sample_bar_median = float(selected.median())
    profile, recent_occupancy, recent = schedule_profile(month_ts, zone)
    monthly = []
    year_occupied: dict[int, np.ndarray] = defaultdict(lambda: np.zeros(168))
    year_possible: dict[int, np.ndarray] = defaultdict(lambda: np.zeros(168))
    for month, ts in sorted(month_ts.items()):
        cal = calendar_hours(month, zone)
        obs = observed_hours(ts, zone)
        expected = float(profile[cal.how.to_numpy()].sum())
        actual = len(ts)
        present = np.bincount(obs.how, minlength=168)
        possible_slots = np.bincount(cal.how, minlength=168)
        month_occ = np.divide(present, possible_slots, out=np.zeros(168, dtype=float), where=possible_slots > 0)
        missing_slots = np.flatnonzero((recent_occupancy >= 0.7) & (recent_occupancy - month_occ >= 0.25))
        monthly.append({"month": month, "observed_minutes": actual, "expected_minutes": round(expected, 1),
                        "coverage": round(actual / expected, 4) if expected else 0.0,
                        "observed_hours": len(obs), "missing_profile_slots": missing_slots.tolist()})
        year = int(month[:4])
        year_occupied[year] += np.bincount(obs.how, minlength=168)
        year_possible[year] += np.bincount(cal.how, minlength=168)
    era = []
    active = recent_occupancy >= 0.7
    for year in sorted(year_possible):
        occ = np.divide(year_occupied[year], year_possible[year], out=np.zeros(168), where=year_possible[year] > 0)
        missing = np.flatnonzero(active & (recent_occupancy - occ >= 0.2))
        era.append({"year": year, "missing_hour_count": len(missing),
                    "missing_hours_of_week": [f"{i // 24}:{i % 24:02d}" for i in missing],
                    "top_missing": [f"{i // 24}:{i % 24:02d}" for i in missing[:20]]})
    spreads = {}
    for year, parts in sorted(year_spreads.items()):
        values = np.concatenate(parts)
        spreads[str(year)] = {"count": len(values), "p50": float(np.percentile(values, 50)),
                              "p95": float(np.percentile(values, 95)), "p99": float(np.percentile(values, 99)),
                              "nonpositive": nonpositive[year], "flat_bars": flat[year],
                              "stale_runs_ge_5": stale_runs[year], "bad_tick_bars": bad_ticks[year],
                              "price_band_hits": band_hits_year[year]}
    blocked_years = {year for year in year_spreads if nonpositive[year] or band_hits_year[year]}
    start, reason = recommend_start(monthly, blocked_years)
    scale = scale_info.get("scale", SCALES.get(symbol))
    scale_relative_error = (abs(sample_bar_median / sample_reference - 1)
                            if sample_bar_median and sample_reference else None)
    return {"symbol": symbol, "timezone": zone, "timezone_basis": "underlying market; UTC for global/24h markets",
            "latest_complete_month": complete[-1].stem, "incomplete_months": [p.stem for p in paths if p not in complete],
            "recent_profile_months": [recent[0], recent[-1]],
            "recent_minutes_per_calendar_hour_of_week": [round(x, 2) for x in profile],
            "monthly_coverage": monthly, "missing_hours_by_era": era, "spread_by_year": spreads,
            "stale_max_consecutive_minutes": max_stale, "quarantine_rows": _log_count(root / f"data/logs/quarantine_{symbol}.csv"),
            "missing_day_rows": _log_count(root / f"data/logs/missing_{symbol}.csv"),
            "point_scale": scale, "scale_sample_day": sample_day,
            "scale_sample_bar_median": sample_bar_median, "scale_sample_reference": sample_reference,
            "scale_relative_error": scale_relative_error, "price_band": band,
            "price_min": low_price, "price_max": high_price, "price_band_hits": band_hits,
            "recommended_start": start, "recommendation_evidence": reason}


def write_report(result: dict, out: Path = REPORTS) -> None:
    out.mkdir(parents=True, exist_ok=True)
    symbol = result["symbol"]
    (out / f"dukascopy_coverage_{symbol}.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [f"# Dukascopy coverage: {symbol}", "",
             f"Analysis timezone: `{result['timezone']}` (DST-aware). Latest complete month: {result['latest_complete_month']}.",
             f"Recent profile: {result['recent_profile_months'][0]} to {result['recent_profile_months'][1]}.", "",
             f"**Recommended clean-era start: {result['recommended_start'] or 'none established'}.** {result['recommendation_evidence']}", "",
             "Coverage is observed 1-minute rows divided by the expected minutes from the recent local hour-of-week profile. The profile includes normal holiday and maintenance-hour frequency; isolated dips remain visible below.", "",
             f"Point scale: {result['point_scale']}; calibration sample relative error vs stored 1m median: {result['scale_relative_error']}; price band: {result['price_band']}; observed price range: {result['price_min']:.3f}–{result['price_max']:.3f}; band hits: {result['price_band_hits']}.",
             f"Quarantine rows: {result['quarantine_rows']}; missing-day rows: {result['missing_day_rows']}; maximum consecutive unchanged close run: {result['stale_max_consecutive_minutes']} minutes.", "",
             "## Missing recent-profile hours by year", "", "| Year | Missing hour-of-week slots | First slots (weekday:hour, Monday=0) |", "|---|---:|---|"]
    for row in result["missing_hours_by_era"]:
        lines.append(f"| {row['year']} | {row['missing_hour_count']} | {', '.join(row['top_missing'])} |")
    lines += ["", "## Spread and flatness by year", "", "| Year | p50 | p95 | p99 | Nonpositive spread | Flat bars | Stale runs ≥5m | Bad-tick bars | Price-band hits |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for year, row in result["spread_by_year"].items():
        lines.append(f"| {year} | {row['p50']:.6g} | {row['p95']:.6g} | {row['p99']:.6g} | {row['nonpositive']} | {row['flat_bars']} | {row['stale_runs_ge_5']} | {row['bad_tick_bars']} | {row['price_band_hits']} |")
    lines += ["", "## Minute coverage by month", "", "| Month | Observed | Expected | Coverage |", "|---|---:|---:|---:|"]
    for row in result["monthly_coverage"]:
        lines.append(f"| {row['month']} | {row['observed_minutes']} | {row['expected_minutes']:.0f} | {row['coverage']:.2%} |")
    (out / f"dukascopy_coverage_{symbol}.md").write_text("\n".join(lines) + "\n")


def completed_symbols(root: Path = ROOT) -> list[str]:
    """Campaigns with every planned month complete through the prior UTC month."""
    now = datetime.now(timezone.utc)
    through = now.year * 12 + now.month - 1
    result = []
    for symbol, start in DUKASCOPY_START.items():
        source = root / "data/bars/dukascopy" / symbol
        first = start.year * 12 + start.month
        expected = {f"{(number - 1) // 12:04d}-{(number - 1) % 12 + 1:02d}"
                    for number in range(first, through + 1)}
        complete = {path.stem for path in source.glob("????-??.parquet")
                    if (pq.read_metadata(path).metadata or {}).get(b"msd_complete") == b"1"}
        if expected and expected <= complete:
            result.append(symbol)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", help="Repeat for each instrument; defaults to all with completed months")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=REPORTS)
    args = parser.parse_args()
    symbols = args.symbol or completed_symbols(args.root)
    for symbol in symbols:
        try:
            result = audit_symbol(symbol, args.root)
        except ValueError as error:
            print(f"SKIP {symbol}: {error}", flush=True)
            continue
        write_report(result, args.out)
        print(f"{symbol}: recommended={result['recommended_start']} latest_complete={result['latest_complete_month']}", flush=True)


if __name__ == "__main__":
    main()
