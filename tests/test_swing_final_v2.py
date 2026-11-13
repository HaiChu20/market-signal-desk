from pathlib import Path

import pandas as pd

from msd.research import swing_final_v2 as final


def test_each_rule_is_scored_and_kept_separately(monkeypatch, tmp_path: Path):
    calls = []

    def fake_rule(root, setup):
        calls.append(setup)
        return {"rule": f"{setup};SL=2ATR;TP=3R", "verdict": "KEEP" if setup == "S1" else "DROP",
                "pooled_traded": {"trades": 3, "net_R": .1 if setup == "S1" else 0.,
                                  "t_stat": 1., "no_carry_R": .2, "double_cost_R": -.1},
                "per_market": {}, "per_year": {}, "evidence_market_average_R": -.2,
                "random_direction_95pct_R": .01, "unresolved_at_end_total": 1}

    monkeypatch.setattr(final, "_rule", fake_rule)
    ledger = tmp_path / "trials.csv"
    result = final.run(tmp_path, tmp_path / "reports", ledger)
    assert calls == ["S1", "S2"]
    assert result["S1"]["verdict"] == "KEEP"
    assert result["S2"]["verdict"] == "DROP"
    assert ledger.read_bytes().count(b"\r\n") == 2
    assert "S1" in (tmp_path / "reports/final_s1_s2.md").read_text()
    assert "S2" in (tmp_path / "reports/final_s1_s2.json").read_text()


def test_run_once_guard_blocks_second_invocation(tmp_path: Path):
    import pytest
    out = tmp_path / "reports"
    out.mkdir()
    (out / "final_s1_s2.json").write_text("{}")
    with pytest.raises(FileExistsError):
        final.run(tmp_path, out, tmp_path / "trials.csv")
