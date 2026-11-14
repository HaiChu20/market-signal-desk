import json
from pathlib import Path

import pandas as pd
import pytest

from msd.research.tiktok import common, run, strategy_a, strategy_b


def _synthetic_trade(market, params):
    exit_price = 100.3 + float(params.get("k", .5)) / 10
    return common.build_trade_record(
        market, "A", params, 1, "2022-06-01T14:30:00Z", "2022-06-01T15:00:00Z",
        100.1, exit_price, 1., gross_entry=100., gross_exit=exit_price - .1,
        entry_spread=.2 if market not in common.CRYPTO_MARKETS else None,
        exit_spread=.2 if market not in common.CRYPTO_MARKETS else None,
        exit_reason="session_close",
    )


def test_dev_runner_freezes_nasdaq_choice_and_writes_crlf_once(monkeypatch, tmp_path: Path):
    bars = pd.DataFrame({"ts": pd.to_datetime(["2022-06-01T14:30Z", "2022-06-01T14:31Z"], utc=True)})
    for field in "ohlc":
        bars[f"bid_{field}"] = 99.9
        bars[f"ask_{field}"] = 100.1
    monkeypatch.setattr(common, "load_1m", lambda market, *args, **kwargs: bars)
    monkeypatch.setattr(common, "session_frames", lambda *args, **kwargs: [])
    monkeypatch.setattr(strategy_a, "simulate", lambda bars, market, params, **kwargs:
                        [_synthetic_trade(market, params)])
    monkeypatch.setattr(strategy_a, "random_exit_factory", lambda *args, **kwargs:
                        (lambda trade, side: float(side)))
    report_dir, ledger = tmp_path / "reports/research/tiktok", tmp_path / "reports/trials.csv"
    result = run.run("A", dev=True, reports=report_dir, ledger=ledger)
    assert result["period"] == "dev"
    assert result["chosen_params"]["k"] == .7
    assert len(result["full_grid_by_market"]["USATECHIDXUSD"]) == 24
    assert result["full_grid_by_market"]["USATECHIDXUSD"][0]["exit_reason_counts"] == {"session_close": 1}
    assert (report_dir / "strategy_A_selection.json").exists()
    assert (report_dir / "strategy_A_dev_equity.csv").exists()
    assert ledger.read_bytes().count(b"\r\n") == 2  # header plus one append-only row
    rerun = run.run("A", dev=True, reports=report_dir, ledger=ledger)
    assert rerun["chosen_params"] == result["chosen_params"]
    rows = common.read_trials(ledger)
    assert len(rows) == 2
    assert rows[0]["run_id"] == "tiktok-A-dev"
    assert rows[1]["run_id"].startswith("tiktok-A-dev-rerun-")


def test_common_hook_exposes_strategy_b_shared_simulator():
    assert common.strategy_simulator("B") is strategy_b.simulate


def test_b_unresolved_count_tracks_only_the_selected_trade_still_open(monkeypatch):
    params = dict(run.B_DEFAULT)
    entry = pd.Timestamp("2022-06-01T14:35Z")
    monkeypatch.setattr(strategy_b, "_validate", lambda bars, market, params: bars)
    monkeypatch.setattr(strategy_b, "_indicator_bars", lambda *args: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(strategy_b, "_complete_sessions", lambda *args: [])
    monkeypatch.setattr(strategy_b, "_entry_candidates", lambda *args: [
        {"entry_ts": entry}, {"entry_ts": entry + pd.Timedelta(minutes=30)}
    ])
    bars = pd.DataFrame({"ts": [entry]})
    assert run._b_unresolved_count(bars, "USATECHIDXUSD", params, []) == 1
    closed = [{"entry_ts": entry.isoformat(), "exit_ts": (entry + pd.Timedelta(hours=1)).isoformat()}]
    assert run._b_unresolved_count(bars, "USATECHIDXUSD", params, closed) == 0


def test_holdout_flag_must_be_explicit_and_loader_guard_precedes_data_call(monkeypatch):
    called = False

    def fake_load(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(common, "load_data", fake_load)
    with pytest.raises(PermissionError):
        common.load_1m("USATECHIDXUSD", common.WARMUP_START,
                       pd.Timestamp("2023-01-02", tz="UTC"))
    assert not called


def test_holdout_refuses_a_changed_selection_after_recorded_holdout(tmp_path: Path):
    reports = tmp_path / "reports/research/tiktok"
    reports.mkdir(parents=True)
    selection_path = reports / run.A_SELECTION
    selection_path.write_text(json.dumps({
        "strategy": "A", "params": run.A_DEFAULT, "spec_commit": run.FROZEN_SPEC_COMMIT,
    }))
    (reports / "strategy_A_holdout.json").write_text(json.dumps({
        "dev_selection_hash": "changed-after-holdout",
    }))
    with pytest.raises(ValueError, match="DEV selection changed"):
        run.run("A", run_holdout_once=True, reports=reports,
                ledger=tmp_path / "reports/trials.csv")
