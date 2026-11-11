from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from msd.data.flow_features import build_flow_features, join_by_known_at


def _frames(rows: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ts = pd.date_range("2024-01-01", periods=rows, freq="min", tz="UTC")
    known = ts + pd.Timedelta(minutes=1)
    primary = pd.DataFrame({"ts": ts, "known_at": known, "bid_c": 100 + np.arange(rows) * .01,
                            "ask_c": 100.02 + np.arange(rows) * .01})
    base = np.arange(rows, dtype=float)
    spot = pd.DataFrame({"ts": ts, "known_at": known, "buy_vol": 1 + (base % 3),
                         "sell_vol": 1 + (base % 2), "buy_n": 2 + (base % 5),
                         "sell_n": 1 + (base % 4),
                         "large100k_buy_notional": 10_000 + base,
                         "large100k_sell_notional": 5_000 + base,
                         "large1m_buy_notional": 1_000 + base,
                         "large1m_sell_notional": 500 + base})
    perp = pd.DataFrame({"ts": ts, "known_at": known, "buy_vol": 2 + (base % 2),
                         "sell_vol": 1 + (base % 3), "buy_n": 3 + (base % 3),
                         "sell_n": 2 + (base % 2)})
    return primary, spot, perp


def test_future_flow_perturbation_does_not_change_past_features():
    primary, spot, perp = _frames(1800)
    baseline = build_flow_features(primary, spot=spot, perp=perp)
    cut = 1500
    changed_spot = spot.copy()
    changed_perp = perp.copy()
    changed_primary = primary.copy()
    changed_spot.loc[cut + 1:, ["buy_vol", "sell_vol", "large100k_buy_notional"]] *= 17
    changed_perp.loc[cut + 1:, ["buy_vol", "sell_vol"]] *= 23
    changed_primary.loc[cut + 1:, ["bid_c", "ask_c"]] *= 1.3
    perturbed = build_flow_features(changed_primary, spot=changed_spot, perp=changed_perp)
    before = baseline.loc[:cut]
    after = perturbed.loc[:cut]
    assert_frame_equal(before, after, check_exact=True)
    truncated = build_flow_features(primary.iloc[:cut+1], spot=spot.iloc[:cut+1],
                                    perp=perp.iloc[:cut+1])
    assert_frame_equal(before.reset_index(drop=True), truncated.reset_index(drop=True), check_exact=True)


def test_month_chunk_matches_full_flow_features_with_rolling_warmup():
    rows = 31_000
    primary, spot, perp = _frames(rows)
    full = build_flow_features(primary, spot=spot, perp=perp)
    split = 29_500
    warm_start = split - 20 * 24 * 60
    chunk = build_flow_features(primary.iloc[warm_start:], spot=spot.iloc[warm_start:],
                                perp=perp.iloc[warm_start:])
    full_part = full.iloc[split:].reset_index(drop=True)
    chunk_part = chunk.iloc[split - warm_start:].reset_index(drop=True)
    statistic = "perp_trade_intensity_z20d"
    # pandas' rolling std uses a chunk-origin-dependent compensated sum; this
    # column differs by at most 1.12e-15 here. All other outputs are exact.
    np.testing.assert_allclose(full_part[statistic], chunk_part[statistic], rtol=1e-14, atol=1e-15,
                               equal_nan=True)
    assert_frame_equal(full_part.drop(columns=statistic), chunk_part.drop(columns=statistic),
                       check_exact=True)


def test_asof_join_never_uses_a_later_known_at():
    t = pd.date_range("2024-01-01", periods=3, freq="min", tz="UTC")
    base = pd.DataFrame({"known_at": t, "base": [1, 2, 3]})
    flow = pd.DataFrame({"ts": t - pd.Timedelta(minutes=1), "known_at": t,
                         "flow_value": [10., 20., 30.]})
    joined = join_by_known_at(base, flow)
    assert joined.flow_value.tolist() == [10., 20., 30.]
    earlier = join_by_known_at(base.iloc[:1], flow.iloc[1:])
    assert earlier.flow_value.isna().all()


def test_missing_flow_is_nan_and_marked_uncovered():
    primary, spot, perp = _frames(100)
    partial = spot.iloc[:50].copy()
    out = build_flow_features(primary, spot=partial, perp=perp)
    assert out.spot_flow_coverage.iloc[:50].all()
    assert not out.spot_flow_coverage.iloc[50:].any()
    assert out.spot_delta_1m.iloc[50:].isna().all()
    assert out.flow_coverage.all()  # Perp data still covers the whole interval.


def test_present_hour_without_ticks_is_zero_and_missing_hour_is_nan():
    primary, _, _ = _frames(120)
    tick = pd.DataFrame({"ts": primary.ts.iloc[:1], "known_at": primary.known_at.iloc[:1],
                         "tick_count": [2], "ofi": [3.], "bid_size_sum": [4.],
                         "ask_size_sum": [2.], "size_imbalance": [1/3], "mean_spread": [.2],
                         "max_spread": [.3]})
    out = build_flow_features(primary, ticks=tick,
                              covered_minutes={"ticks": pd.DatetimeIndex(primary.known_at.iloc[:60])})
    assert out.tick_flow_coverage.iloc[10]
    assert out.ticks_tick_count.iloc[10] == 0
    assert out.ticks_ofi.iloc[10] == 0
    assert out.ticks_bid_size_sum.iloc[10] == 0
    assert np.isnan(out.ticks_mean_spread.iloc[10])
    assert not out.tick_flow_coverage.iloc[70]
    assert np.isnan(out.ticks_tick_count.iloc[70])
    assert np.isnan(out.ticks_ofi.iloc[70])


def test_verified_tick_hour_with_twenty_quote_less_minutes_stays_valid():
    primary, _, _ = _frames(60)
    missing = list(range(20, 40))
    sparse_primary = primary.drop(index=missing).reset_index(drop=True)
    tick = pd.DataFrame({"ts": primary.ts.iloc[[0, 59]],
                         "known_at": primary.known_at.iloc[[0, 59]],
                         "tick_count": [2, 1], "ofi": [3., -1.],
                         "bid_size_sum": [4., 2.], "ask_size_sum": [2., 2.],
                         "size_imbalance": [1/3, 0.], "mean_spread": [.2, .3],
                         "max_spread": [.3, .4]})
    covered = pd.DatetimeIndex(primary.known_at)
    out = build_flow_features(sparse_primary, ticks=tick, covered_minutes={"ticks": covered})
    final = out.iloc[-1]
    assert final.ticks_tick_count_60m == 3
    assert final.ticks_ofi_60m == 2
    assert final.tick_flow_coverage
    assert len(out) == 40  # Complete clock is sampled back to primary rows.


def test_complete_crypto_file_without_trades_is_zero_and_time_gap_breaks_60m():
    primary, spot, _ = _frames(120)
    keep = list(range(30)) + list(range(90, 120))
    primary = primary.iloc[keep].reset_index(drop=True)
    spot = spot.iloc[keep[:1]].reset_index(drop=True)
    out = build_flow_features(primary, spot=spot,
                              covered_minutes={"spot": pd.DatetimeIndex(primary.known_at)})
    assert out.spot_flow_coverage.all()
    assert out.spot_delta_1m.iloc[1] == 0
    assert np.isnan(out.spot_delta_60m.iloc[-1])
    assert np.isnan(out.cum_delta_divergence_60m.iloc[-1])


def test_source_outage_inside_clock_window_requires_80_percent_coverage():
    primary, spot, _ = _frames(100)
    no_activity = spot.iloc[:1].copy()
    covered = pd.DatetimeIndex(primary.known_at)
    # At the final minute of a 60-minute window, 48 covered minutes pass;
    # 47 covered minutes fail. No-activity minutes in present files count.
    gap = pd.DatetimeIndex(primary.known_at.iloc[41:53])
    enough = covered.difference(gap)
    passes = build_flow_features(primary, spot=no_activity, covered_minutes={"spot": enough})
    assert passes.spot_flow_coverage.iloc[-1]
    assert passes.spot_delta_60m.iloc[-1] == 0
    fails = build_flow_features(primary, spot=no_activity,
                                covered_minutes={"spot": enough.difference(pd.DatetimeIndex([primary.known_at.iloc[60]]))})
    assert np.isnan(fails.spot_delta_60m.iloc[-1])


def test_us_timestamp_join_and_absent_depth_month(tmp_path):
    base, spot, _ = _frames(2)
    flow = build_flow_features(base, spot=spot)
    flow["known_at"] = flow.known_at.astype("datetime64[us, UTC]")
    joined = join_by_known_at(base[["known_at"]], flow, tmp_path / "missing-depth.parquet")
    assert joined.spot_delta_1m.notna().all()
    assert joined.depth_coverage.isna().all()
    assert joined.depth_imbalance_1pct.isna().all()
    assert joined.depth_imbalance_5pct.isna().all()
    depth_path = tmp_path / "depth.parquet"
    pd.DataFrame({"known_at": base.known_at.astype("datetime64[us, UTC]"),
                  "coverage": [True, True],
                  "depth_imbalance_1pct": [.2, .3],
                  "source_missing_day": [False, False],
                  "staleness_seconds": [0., 0.],
                  "snapshot_ts": base.known_at}).to_parquet(depth_path)
    with_depth = join_by_known_at(base[["known_at"]], flow, depth_path)
    assert with_depth.depth_imbalance_1pct.tolist() == [.2, .3]
    assert with_depth.depth_coverage.tolist() == [True, True]
    assert "source_missing_day" not in with_depth
    assert "staleness_seconds" not in with_depth
    assert "snapshot_ts" not in with_depth
