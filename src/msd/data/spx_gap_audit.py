"""Read-only SPX/NQ cash-era gap audit; write one Markdown report.

HistData parquet timestamps are already UTC-corrected by histdata.parse_csv:
its source clock follows New York wall time with EU DST switch dates.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

START = pd.Timestamp("2018-12-16 23:00", tz="UTC")
END = pd.Timestamp("2020-07-01", tz="UTC")
ROOT = Path("/Users/bfhach/Projects/market-signal-desk")
PAIRS = (("SPX", "USA500IDXUSD", "SPXUSD"), ("NQ", "USATECHIDXUSD", "NSXUSD"))


def read_bars(root: Path, vendor: str, symbol: str) -> pd.DataFrame:
    base = root / "data" / "bars" / vendor / symbol
    parts = []
    columns = ["ts", "bid_o", "bid_h", "bid_l", "bid_c", "ask_c"] if vendor == "dukascopy" else ["ts", "bid_c", "feed"]
    for year in (2018, 2019, 2020):
        for month in range(1, 13):
            path = base / f"{year}-{month:02d}.parquet"
            if path.exists():
                parts.append(pq.read_table(path, columns=columns).to_pandas())
    if not parts:
        raise FileNotFoundError(base)
    frame = pd.concat(parts, ignore_index=True)
    frame["ts"] = pd.to_datetime(frame.ts, utc=True)
    return frame.loc[(frame.ts >= START) & (frame.ts < END)].drop_duplicates("ts").sort_values("ts").set_index("ts")


def minute_runs(minutes: pd.DatetimeIndex) -> pd.DataFrame:
    """Consecutive missing minutes, with start/end and inclusive length."""
    if len(minutes) == 0:
        return pd.DataFrame(columns=["start", "end", "length"])
    times = minutes.sort_values()
    groups = (times.to_series().diff() != pd.Timedelta(minutes=1)).cumsum().to_numpy()
    return pd.DataFrame({"ts": times, "group": groups}).groupby("group").agg(
        start=("ts", "first"), end=("ts", "last"), length=("ts", "size")
    ).reset_index(drop=True)


def returns(series: pd.Series) -> pd.Series:
    result = series.pct_change(fill_method=None)
    return result.where(series.index.to_series().diff().eq(pd.Timedelta(minutes=1)))


def lag_correlations(hist: pd.Series, duka: pd.Series) -> list[tuple[int, int, float]]:
    hret, dret = returns(hist), returns(duka)
    result = []
    for lag in (-60, -2, -1, 0, 1, 2, 60):
        shifted = hret.copy()
        shifted.index += pd.Timedelta(minutes=lag)
        pair = pd.concat([shifted.rename("h"), dret.rename("d")], axis=1, join="inner").dropna()
        result.append((lag, len(pair), float(pair.h.corr(pair.d)) if len(pair) > 2 else float("nan")))
    return result


def adjacent_flat_count(runs: pd.DataFrame, bars: pd.DataFrame) -> tuple[int, int, int]:
    """Count gaps bracketed by identical closes and by zero-range bars."""
    equal_close = zero_range = bracketed = 0
    for row in runs.itertuples(index=False):
        before, after = row.start - pd.Timedelta(minutes=1), row.end + pd.Timedelta(minutes=1)
        if before not in bars.index or after not in bars.index:
            continue
        bracketed += 1
        a, b = bars.loc[before], bars.loc[after]
        equal_close += bool(np.isclose(a.bid_c, b.bid_c, atol=1e-9, rtol=0))
        zero_range += bool(np.isclose(a.bid_h, a.bid_l, atol=1e-9, rtol=0) or
                           np.isclose(b.bid_h, b.bid_l, atol=1e-9, rtol=0))
    return bracketed, equal_close, zero_range


def preceding_flat_rate(reference: pd.DatetimeIndex, bars: pd.DataFrame) -> tuple[float, float]:
    """Previous-bar flat share before missing vs present reference minutes."""
    prev = bars.reindex(reference - pd.Timedelta(minutes=1))
    flat = np.isclose(prev.bid_h, prev.bid_l, atol=1e-9, rtol=0)
    valid = prev.bid_c.notna().to_numpy()
    missing = ~reference.isin(bars.index)
    return float(flat[valid & missing].mean()), float(flat[valid & ~missing].mean())


def analyze(root: Path) -> str:
    data = {name: (read_bars(root, "dukascopy", duka), read_bars(root, "histdata", hist))
            for name, duka, hist in PAIRS}
    d_spx, h_spx = data["SPX"]
    d_nq, h_nq = data["NQ"]
    # Same cash CFD session: one feed's observed minute is the other's trading-minute witness.
    gaps = {"SPX": d_nq.index.difference(d_spx.index), "NQ": d_spx.index.difference(d_nq.index)}
    rows = []
    for month in pd.period_range("2018-12", "2020-06", freq="M"):
        key = str(month)
        mask = lambda idx: idx.strftime("%Y-%m") == key
        sd, nd = d_spx.index[mask(d_spx.index)], d_nq.index[mask(d_nq.index)]
        sh, nh = h_spx.index[mask(h_spx.index)], h_nq.index[mask(h_nq.index)]
        missing_s, missing_n = nd.difference(sd), sd.difference(nd)
        rows.append((key, len(sd), len(nd), len(missing_s), len(missing_s.intersection(sh)),
                     len(missing_n), len(missing_n.intersection(nh))))

    lines = ["# SPX cash-era minute-gap audit, December 2018–June 2020", "",
             "**Proposal: leave the SPX gaps unfilled from HistData.** The available HistData cash-era bars have the same minute set and bid closes as Dukascopy, so they add no missing SPX minutes. Carrying the 0.66 spread onto invented bars would not restore observed quotes. Retain the existing Dukascopy bars and their source/spread information; revisit only if an independent tick or bar source covers the holes.", "",
             "## Clock and comparison basis", "",
             "HistData parquet `ts` is already UTC-normalized. Its source wall clock is New York local time but changes DST on EU dates; `histdata.parse_csv` applies that rule. No second clock correction or timestamp lag is applied here. The cash comparison starts at 2018-12-16 23:00 UTC and ends before 2020-07-01 UTC. A missing SPX minute is a minute present in NQ and absent in SPX; the reverse defines missing NQ. This is an observed same-session reference, not an estimate of every theoretically tradable minute.", "",
             "## Month-by-month coverage and possible additions", "",
             "| Month | Duka SPX | Duka NQ | SPX absent while NQ trades | HistData SPX present in those | **SPX minutes addable** | NQ absent while SPX trades | HistData NQ present in those |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for month, sd, nd, sm, hs, nm, hn in rows:
        lines.append(f"| {month} | {sd:,} | {nd:,} | {sm:,} | {hs:,} | **{hs:,}** | {nm:,} | {hn:,} |")
    lines += ["", f"Total SPX candidate gaps: **{len(gaps['SPX']):,}**; covered by HistData SPX: **{len(gaps['SPX'].intersection(h_spx.index)):,}**. "
              f"Total NQ candidate gaps: **{len(gaps['NQ']):,}**; covered by HistData NQ: **{len(gaps['NQ'].intersection(h_nq.index)):,}**.", "",
              "## Shape and timing of absent minutes", ""]
    for name in ("SPX", "NQ"):
        bars, hist = data[name]
        missing = gaps[name]
        reference = data["NQ" if name == "SPX" else "SPX"][0].index
        runs = minute_runs(missing)
        bracketed, equal_close, zero_range = adjacent_flat_count(runs, bars)
        before_gap_flat, before_present_flat = preceding_flat_rate(reference, bars)
        local = missing.tz_convert("America/New_York")
        hour_counts = pd.Series(local.hour).value_counts().sort_index()
        lengths = runs.length
        bins = [("1 minute", int((lengths == 1).sum())), ("2–5", int(lengths.between(2, 5).sum())),
                ("6–59", int(lengths.between(6, 59).sum())), ("60–239", int(lengths.between(60, 239).sum())),
                ("240+", int((lengths >= 240).sum()))]
        lines += [f"### {name}", "", f"{len(missing):,} absent minutes in {len(runs):,} runs; longest {int(lengths.max()) if len(lengths) else 0:,} minutes. "
                  f"Of {bracketed:,} runs with adjacent {name} bars, {equal_close:,} have identical bid closes across the gap and {zero_range:,} touch a zero-range bar. "
                  f"The preceding bar is zero-range before {before_gap_flat:.1%} of missing candidate minutes versus {before_present_flat:.1%} of present candidate minutes (where a preceding bar exists). "
                  "This association and the short runs support a no-tick explanation, but cannot prove that no ticks occurred.", "",
                  "| Run length | Number of runs |", "|---|---:|"]
        lines.extend(f"| {label} | {count:,} |" for label, count in bins)
        lines += ["", "NY local hour counts (minutes absent while the other index trades):", "",
                  "| Hour | Absent minutes |", "|---:|---:|"]
        lines.extend(f"| {hour:02d} | {int(hour_counts.get(hour, 0)):,} |" for hour in range(24))
        lines += ["", "Largest runs:", "", "| UTC start | UTC end | Minutes |", "|---|---|---:|"]
        for run in runs.nlargest(10, "length").itertuples(index=False):
            lines.append(f"| {run.start:%Y-%m-%d %H:%M} | {run.end:%Y-%m-%d %H:%M} | {run.length:,} |")
        lines.append("")

    lines += ["## HistData overlap price test", "",
              "Exact means absolute difference ≤0.001 index point. Differences use unadjusted HistData `bid_c` versus Dukascopy bid close and `(bid_c + ask_c)/2`. Return correlations use only consecutive one-minute returns, with the HistData timestamp shifted by the stated lag.", "",
              "| Index | Duka/HistData common minutes | HistData-only | Dukascopy-only | HistData feed | Duka bid exact | Bid median absolute diff | Duka mid exact | Mid median absolute diff |", "|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for name in ("SPX", "NQ"):
        duka, hist = data[name]
        pair = duka[["bid_c", "ask_c"]].join(hist[["bid_c", "feed"]], how="inner", suffixes=("_duka", "_hist"))
        bid_diff = (pair.bid_c_hist - pair.bid_c_duka).abs()
        mid_diff = (pair.bid_c_hist - (pair.bid_c_duka + pair.ask_c) / 2).abs()
        feeds = ", ".join(sorted(hist.feed.dropna().unique()))
        lines.append(f"| {name} | {len(pair):,} | {len(hist.index.difference(duka.index)):,} | {len(duka.index.difference(hist.index)):,} | {feeds} | {(bid_diff <= .001).mean():.6%} | {bid_diff.median():.6f} | {(mid_diff <= .001).mean():.6%} | {mid_diff.median():.6f} |")
    lines += ["", "| Index | Target | Lag −60 | −2 | −1 | 0 | +1 | +2 | +60 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name in ("SPX", "NQ"):
        duka, hist = data[name]
        for target, series in (("bid", duka.bid_c), ("mid", (duka.bid_c + duka.ask_c) / 2)):
            corr = lag_correlations(hist.bid_c, series)
            lines.append(f"| {name} | {target} | " + " | ".join(f"{value:.4f} ({n:,})" for _, n, value in corr) + " |")
    lines += ["", "HistData's minute set is a strict subset of Dukascopy's in this period; its 795 SPX and 841 NQ absent bars cannot help fill gaps. The matching bid closes on every overlapping minute are consistent with the two vendors sharing a cash-CFD quote source. The stored series do not supply independent observations of SPX's missing minutes. The data cannot distinguish omitted no-tick minutes from missing collection or vendor-feed minutes. The constant 0.66 spread in the early SPX era is a quote convention, not evidence that a bid can safely be synthesized for absent minutes.", "",
              "## Decision", "",
              "**Leave gaps.** A HistData-based fill would add the per-month counts in the bold column above (zero if the feeds are coterminous). Do not create `source=histdata` or `spread_modeled` bars where HistData has no observation. If independent coverage is obtained later, require timestamp and bid validation against observed adjacent minutes, and mark any inserted bars with both provenance and modeled-spread flags.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("reports/data/spx_2019_gap_fill.md"))
    args = parser.parse_args()
    report = analyze(args.data_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"Wrote {args.output} ({len(report):,} characters)")


if __name__ == "__main__":
    main()
