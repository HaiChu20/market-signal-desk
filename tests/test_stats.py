import numpy as np

from statistics import NormalDist

from msd.stats import EULER_GAMMA, expected_max_sharpe, probabilistic_sharpe_ratio


def test_psr_matches_hand_computed_non_normal_example():
    # [-1, 0, 1, 2] gives SR=.387298, skew=0, Pearson kurtosis=1.64.
    # Bailey–López de Prado variance gives z=.662913, hence PSR=.746307.
    assert np.isclose(probabilistic_sharpe_ratio(0.3872983346207417, 4, 0.0, 1.64),
                      0.746306736608969, atol=1e-12)


def test_expected_max_sharpe_matches_hand_computed_null_sr0():
    # V[SR_n] = 0.01 daily² and N=10: SR0 is sqrt(V) times the BLP
    # weighted expected-maximum quantiles, with no trial-mean term.
    a = NormalDist().inv_cdf(0.9)
    b = NormalDist().inv_cdf(1 - 1 / (10 * np.e))
    expected = 0.1 * ((1 - EULER_GAMMA) * a + EULER_GAMMA * b)
    trials = np.array([-np.sqrt(0.005), np.sqrt(0.005)])
    assert np.isclose(expected_max_sharpe(trials, 10), expected)
    assert expected_max_sharpe(np.array([0.2, 0.3]), 1) == 0
