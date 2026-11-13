from pathlib import Path

import numpy as np
import pandas as pd

from msd.research import swing_final as final
from msd.research import swing_stage1 as stage1


def _bars(times):
    frame = pd.DataFrame({"ts": pd.to_datetime(times, utc=True)})
    for side in ("bid", "ask"):
        for field in "ohlc":
            frame[f"{side}_{field}"] = 100.0
    return frame


def test_period_split_and_warmup_open_trade_state_carry(monkeypatch):
    bars = _bars(["2024-12-31 07:00Z", "2025-01-01 07:00Z",
                  "2025-01-02 07:00Z", "2025-01-03 07:00Z",
                  "2025-01-06 07:00Z"])
    signal = pd.DataFrame({
        "end": pd.to_datetime(["2024-12-30 22:00Z", "2024-12-31 22:00Z",
                               "2025-01-02 22:00Z"], utc=True),
        "c": [100.0] * 3,
        "atr": [1.0] * 3,
        "S1": [0] * 3,
        "S2": [0] * 3,
        "S3": [1] * 3,
    })
    monkeypatch.setattr(stage1, "daily_bars", lambda bars, period: signal)
    monkeypatch.setattr(stage1, "signals", lambda daily, first_year: signal)

    def fake_exit(ts, prices, mask, entry, side, stop, target, cap):
        return (2, 103.0, "tp") if entry == 0 else (4, 103.0, "tp")

    monkeypatch.setattr(stage1, "exit_trade", fake_exit)
    rows, _ = stage1.evaluate_market(
        bars, "USATECHIDXUSD", primary_only=True, period=final.WARMUP_PERIOD,
        setups=("S3",),
    )

    # The 2024-12-31 warm-up entry remains open through the 2025-01-01 entry,
    # blocking it. Only the later flat-state entry is scored.
    assert [row["entry_ts"] for row in rows] == ["2025-01-03T07:00:00+00:00"]
    assert all(pd.Timestamp(row["entry_ts"]) >= final.SCORE_START for row in rows)


def test_dev_period_default_is_unchanged():
    bars = _bars(pd.date_range("2022-01-01", periods=200, freq="D", tz="UTC"))
    implicit = stage1.daily_bars(bars)
    explicit = stage1.daily_bars(bars, period=stage1.DEV_PERIOD)
    pd.testing.assert_frame_equal(implicit, explicit)
    assert stage1.DEV_PERIOD == stage1.Period(end=stage1.CUT)


def test_final_walk_forward_purge_excludes_boundary_and_future_labels():
    exits = np.array(["2024-12-31T23:59:59", "2025-01-01T00:00:00",
                      "2025-12-31T23:59:59", "2026-01-01T00:00:00"],
                     dtype="datetime64[ns]")
    assert final.s2.training_mask(exits, 2025).tolist() == [True, False, False, False]
    assert final.s2.training_mask(exits, 2026).tolist() == [True, True, True, False]


def test_final_trial_append_is_exactly_two_crlf_rows(tmp_path: Path):
    ledger = tmp_path / "trials.csv"
    ledger.write_bytes(b"header\r\n")
    summary = {"pooled_traded": {"net_R": 0.1, "t_stat": 1.0, "trades": 2},
               "unresolved_at_end_total": 0}
    final._append_trials(ledger, {
        "main": {**summary, "verdict": "NOT BROKEN"},
        "stage2": {**summary, "verdict": "REPORTED ONLY"},
    })
    content = ledger.read_bytes()
    assert content.count(b"\r\n") == 3
    assert content.count(final.MAIN_TRIAL_ID.encode()) == 1
    assert content.count(final.MODEL_TRIAL_ID.encode()) == 1
