import pandas as pd

from msd.research.silence_diagnostic import _finite_mean, _conclusion


def test_finite_mean_ignores_nonfinite():
    assert _finite_mean([1, float("nan"), 3]) == 2


def test_conclusion_counts_economics_and_incremental_skill():
    costs = {"best_fixed": {"BTC": {"mean_net_R": -1}, "NQ": {"mean_net_R": 1}}}
    skills = [{"brier_skill_vs_cell_base_rate": 0.1}, {"brier_skill_vs_cell_base_rate": -0.1}]
    text = _conclusion(costs, skills)
    assert "1/4 markets" in text
    assert "1/5 frozen models" in text
