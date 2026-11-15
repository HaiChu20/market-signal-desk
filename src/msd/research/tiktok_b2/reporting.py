"""Batch-2 metrics, random-direction replay, DSR, and dev configuration counts."""
from __future__ import annotations

import json
from statistics import NormalDist
from pathlib import Path

import numpy as np
import pandas as pd

from msd.research.tiktok import common
from .execution import replay_fixed_entry


def require_holdout(allow_holdout: bool, selection_path: Path | None = None) -> None:
    if allow_holdout and (selection_path is None or not selection_path.is_file()):
        raise FileNotFoundError("an existing frozen dev selection is required before holdout")


def daily_returns(trades: list[dict], data) -> pd.Series:
    years = {pd.Timestamp(row["entry_ts"]).year for row in trades}
    years = years or {2019, 2020, 2021, 2022}
    allowed = {row.day for row in data.rth_days.itertuples()
               if row.complete and row.day.year in years}
    values = {day: 0. for day in allowed}
    for row in trades:
        local_day = pd.Timestamp(row["entry_ts"]).tz_convert("America/New_York").date()
        if local_day in values:
            values[local_day] += float(row["net_R"])
    return pd.Series(values, dtype=float).sort_index()


def dsr(daily_r: pd.Series, trials: int) -> dict:
    """Deflated Sharpe ratio from Bailey & López de Prado (2014)."""
    x = np.asarray(daily_r, float)
    if len(x) < 3 or trials < 1:
        return {"trials": int(trials), "observations": len(x), "sharpe_annualized": None,
                "expected_max_sharpe_annualized": None, "dsr": None}
    sd = float(x.std(ddof=1))
    sr = float(x.mean() / sd) if sd > 0 else 0.
    if trials == 1:
        z = 0.
    else:
        gamma = .5772156649015329
        z = ((1 - gamma) * NormalDist().inv_cdf(1 - 1 / trials) +
             gamma * NormalDist().inv_cdf(1 - 1 / (trials * np.e)))
    expected = z / np.sqrt(len(x))
    centered = x - x.mean()
    m2 = float(np.mean(centered ** 2))
    s = float(np.mean(centered ** 3) / m2 ** 1.5) if m2 > 0 else 0.
    k = float(np.mean(centered ** 4) / m2 ** 2) if m2 > 0 else 3.
    variance = (1 - s * sr + (k - 1) * sr * sr / 4) / max(len(x) - 1, 1)
    zscore = (sr - expected) / np.sqrt(max(variance, 1e-15))
    return {"trials": int(trials), "observations": len(x),
            "sharpe_annualized": sr * np.sqrt(252),
            "expected_max_sharpe_annualized": expected * np.sqrt(252),
            "dsr": float(NormalDist().cdf(zscore))}


def winning_periods(trades: list[dict], data=None) -> dict:
    grouped = {}
    for row in trades:
        ts = pd.Timestamp(row["entry_ts"]).tz_convert("America/New_York")
        grouped.setdefault(ts.strftime("%Y-%m-%d"), 0.)
        grouped[ts.strftime("%Y-%m-%d")] += row["net_R"]
    output = {}
    frame = pd.Series(grouped, dtype=float)
    if data is not None:
        years = {pd.Timestamp(row["entry_ts"]).year for row in trades}
        years = years or {2019, 2020, 2021, 2022}
        complete_days = sorted({row.day for row in data.rth_days.itertuples()
                                if row.complete and row.day.year in years})
        frame = frame.reindex(pd.Index(complete_days).astype(str), fill_value=0.)
    if frame.empty:
        return {name: 0. for name in ("day", "week", "month")}
    for name, freq in (("day", "D"), ("week", "W"), ("month", "M")):
        sums = frame.copy()
        sums.index = pd.DatetimeIndex(sums.index).to_period(freq)
        totals = sums.groupby(level=0).sum()
        output[name] = float(np.mean(totals.to_numpy() > 0))
    return output


def summarize(trades: list[dict], data, *, diagnostics: dict | None = None,
              allow_holdout: bool = False, selection_path: Path | None = None) -> dict:
    if allow_holdout:
        require_holdout(True, selection_path)
    rows = list(trades)
    common.assert_holdout_allowed(rows, allow_holdout=allow_holdout)
    base = common.required_outputs(rows, allow_holdout=allow_holdout)
    base["by_entry_hour"] = common.metrics_by(rows, lambda row: row.get("entry_hour", "unknown"), allow_holdout=allow_holdout)
    values = np.asarray([row["net_R"] for row in rows], dtype=float)
    daily = daily_returns(rows, data)
    daily_sd = float(daily.std(ddof=1)) if len(daily) > 1 else 0.
    base["daily"] = {"sharpe_annualized": float(daily.mean() / daily_sd * np.sqrt(252)) if daily_sd else None,
                     "max_drawdown_R": float((daily.cumsum().cummax() - daily.cumsum()).max()) if len(daily) else 0.,
        "winning_periods": winning_periods(rows, data)}
    net = np.asarray([row["net_R"] for row in rows], float)
    win_days = sum(value > 0 for value in daily.values)
    base["daily"]["winning_days"] = {"wins": int(win_days), "days": int(len(daily)),
                                     "percent": float(win_days / len(daily) * 100) if len(daily) else None}
    base["costs"] = {"x1_net_avg_R": float(np.mean([r["net_R"] for r in rows])) if rows else None,
                     "x1_5_net_avg_R": float(np.mean([r["net_R_cost15"] for r in rows])) if rows else None,
                     "x2_net_avg_R": float(np.mean([r["net_R_cost2"] for r in rows])) if rows else None,
                     "median_stop_points": float(np.median([r["risk_points"] for r in rows])) if rows else None,
                     "median_cost_R": float(np.median([r["cost_R"] for r in rows])) if rows else None}
    losing_days = {day for day, value in daily.items() if value < 0}
    run = longest = 0
    for value in daily:
        run = run + 1 if value < 0 else 0
        longest = max(longest, run)
    trade_years = {pd.Timestamp(row["entry_ts"]).year for row in rows}
    year_set = {row.day.year for row in data.rth_days.itertuples()
                if row.complete and row.day.year in trade_years}
    base["overall"]["trades_per_year"] = len(rows) / max(len(year_set), 1)
    base["overall"]["total_R"] = float(values.sum()) if len(values) else 0.
    base["overall"]["longest_losing_streak_days"] = longest
    base["overall"]["winning_days"] = base["daily"]["winning_periods"]["day"]
    base["overall"]["winning_weeks"] = base["daily"]["winning_periods"]["week"]
    base["overall"]["winning_months"] = base["daily"]["winning_periods"]["month"]
    base["overall"]["longest_losing_streak_days"] = longest
    if diagnostics is not None:
        base["diagnostics"] = dict(diagnostics)
    return base


def random_direction(trades: list[dict], bars, *, seeds: int = 1000, seed: int = 0,
                     fill_model: str = "trade_through", allow_holdout: bool = False,
                     selection_path: Path | None = None) -> dict:
    if allow_holdout:
        require_holdout(True, selection_path)
    common.assert_holdout_allowed(trades, allow_holdout=allow_holdout)
    if not trades:
        return {"seeds": seeds, "actual_avg_R": None, "random_percentile": None,
                "random_mean_R": None, "random_p05_R": None, "random_p95_R": None}
    outcomes = np.empty((len(trades), 2), dtype=float)
    for i, trade in enumerate(trades):
        for j, side in enumerate((1, -1)):
            outcome = replay_fixed_entry(bars, trade, side, fill_model=fill_model)
            outcomes[i, j] = outcome["net_R"]
            if side == trade["side"]:
                assert outcome["exit_ts"] == trade["exit_ts"], "same-side random replay changed exit timestamp"
                assert np.isclose(outcome["net_R"], trade["net_R"], atol=1e-12), "same-side random replay changed R"
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, 2, size=(seeds, len(trades)))
    means = outcomes[np.arange(len(trades))[None, :], draws].mean(axis=1)
    actual = float(np.mean([r["net_R"] for r in trades]))
    return {"seeds": seeds, "actual_avg_R": actual,
            "random_percentile": float(np.mean(means <= actual) * 100),
            "random_mean_R": float(means.mean()),
            "random_p05_R": float(np.percentile(means, 5)),
            "random_p95_R": float(np.percentile(means, 95))}


def project_configuration_count(root: Path = Path("reports/research")) -> dict:
    """Count dev-grid rows only; never opens or reports holdout grid files."""
    roots = (root / "tiktok", root / "tiktok_b2")
    files = sorted(path for base in roots if base.exists()
                   for path in base.glob("*_dev_grid.csv"))
    counts = {}
    for path in files:
        with path.open("r", newline="") as handle:
            counts[str(path)] = max(sum(1 for _ in handle) - 1, 0)
    return {"tried": int(sum(counts.values())), "by_dev_grid": counts}


def write_b2_report(output_dir: Path, name: str, report: dict, grid: list[dict], trades: list[dict],
                    *, allow_holdout: bool = False, selection_path: Path | None = None) -> None:
    if allow_holdout:
        require_holdout(True, selection_path)
    """Use batch-1 report writer after stripping replay-only fields from public trades."""
    clean = [{k: v for k, v in row.items() if not k.startswith("_")} for row in trades]
    common.write_report(output_dir, name, report, grid, clean, allow_holdout=allow_holdout)
    path = output_dir / f"{name}.md"
    lines = ["", "## Diagnostics", "",
             f"Configurations tried in local dev grids: {report.get('project_configuration_count', {}).get('tried', 0)}.",
             f"DSR: {report.get('dsr', {}).get('dsr')} (trials={report.get('dsr', {}).get('trials')}).", ""]
    for scope, detail in report.get("scopes", {}).items():
        lines += [f"### {scope}", ""]
        for year, values in detail.get("by_year", {}).items():
            lines.append(f"- {year}: {values['trades']} trades, net avg {values['net_avg_R']}R")
        for side, values in detail.get("long_vs_short", {}).items():
            lines.append(f"- {side}: {values['trades']} trades, net avg {values['net_avg_R']}R")
        for hour, values in detail.get("by_entry_hour", {}).items():
            lines.append(f"- Entry hour {hour}: {values['trades']} trades, net avg {values['net_avg_R']}R")
        lines.append("")
    if report.get("random_benchmark"):
        lines += ["## Random-direction benchmark", ""]
        for scope, values in report["random_benchmark"].items():
            lines.append(f"- {scope}: {values.get('random_percentile')} percentile; "
                         f"mean={values.get('random_mean_R')}R; 5–95%={values.get('random_p05_R')}–{values.get('random_p95_R')}R")
        lines.append("")
    if report.get("sensitivity"):
        lines += ["## Cost and fill sensitivity", "", "```json",
                  json.dumps(report["sensitivity"], indent=2, allow_nan=False), "```", ""]
    if report.get("cross_market"):
        lines += ["## ES frozen-cell cross-check", "", "```json",
                  json.dumps(report["cross_market"], indent=2, allow_nan=False), "```", ""]
    table = common.grid_table(grid, allow_holdout=allow_holdout)
    if grid and any(row.get("sensitivity") for row in grid):
        for key, label in (("x1_5", "net_avg_R_x1_5_rerun"),
                           ("x2", "net_avg_R_x2_rerun"),
                           ("touch", "net_avg_R_touch_fill")):
            table[label] = [row.get("sensitivity", {}).get(key, {}).get("net_avg_R") for row in grid]
    columns = list(table.columns)
    lines += ["## Grid heat map", "", "| " + " | ".join(columns) + " |",
              "|" + "|".join("---" for _ in columns) + "|"]
    for row in table.itertuples(index=False, name=None):
        cells = ["" if pd.isna(value) else str(value) for value in row]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    with path.open("a") as handle:
        handle.write("\n".join(lines))


def selection_file(path: Path, strategy: str, params: dict, *, market: str) -> dict:
    selection = {"strategy": strategy, "market": market, "selection_period": "dev",
                 "selection_metric": "highest NQ dev futures net avg R among cells with at least 100 trades",
                 "params": params, "config_hash": common.config_hash(params)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selection, indent=2, allow_nan=False) + "\n")
    return selection
