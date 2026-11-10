# Stage 2 — USA500IDXUSD

Bars: 2265192; range: 2018-01-02..2024-12-31; usable years: [2018, 2019, 2020, 2021, 2022, 2023, 2024]

Minimum risk filter: planned risk ≥ 5 × entry spread; dropped by setup: {'fade': 11830, 'breakout': 2143, 'sweep_fvg': 323, 'noise_area': 726, 'fade_5m': 3555, 'breakout_5m': 1725, 'sweep_fvg_5m': 66}.

sweep_fvg_5m stage counts: {'sweeps': 128005, 'returns': 18404, 'fvgs': 10742, 'retraces': 10692, 'orders': 9246}

| Setup | Split | TP | Candidates | Hit rate | Avg R | Gross avg R | Mean cost R | Median cost R | PF | t-stat | Random percentile | Time exits |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fade | IS | next-level | 8689 | 24.3% | -0.185 | -0.024 | 0.161 | 0.061 | 0.758 | -10.76 | 2.5 | 4.3% |
| fade | IS | 2R | 8689 | 27.9% | -0.176 | -0.018 | 0.158 | 0.061 | 0.760 | -12.20 | 4.0 | 3.3% |
| fade | OOS | next-level | 7697 | 25.1% | -0.146 | -0.011 | 0.135 | 0.068 | 0.810 | -7.57 | 3.5 | 3.2% |
| fade | OOS | 2R | 7697 | 29.3% | -0.156 | -0.017 | 0.139 | 0.068 | 0.787 | -10.04 | 1.5 | 2.3% |
| breakout | IS | next-level | 5315 | 24.6% | -0.130 | -0.003 | 0.128 | 0.052 | 0.815 | -6.40 | 11.0 | 9.3% |
| breakout | IS | 2R | 5315 | 26.4% | -0.141 | 0.002 | 0.143 | 0.052 | 0.798 | -7.75 | 7.5 | 8.3% |
| breakout | OOS | next-level | 5506 | 26.8% | -0.081 | 0.041 | 0.122 | 0.060 | 0.886 | -3.77 | 74.0 | 6.8% |
| breakout | OOS | 2R | 5506 | 29.9% | -0.091 | 0.029 | 0.120 | 0.060 | 0.870 | -4.91 | 65.5 | 5.0% |
| sweep_fvg | IS | next-level | 1517 | 4.1% | -0.136 | -0.051 | 0.086 | 0.043 | 0.771 | -3.92 | 33.5 | 42.9% |
| sweep_fvg | IS | 2R | 1517 | 16.8% | -0.103 | -0.019 | 0.084 | 0.039 | 0.818 | -3.48 | 44.0 | 32.9% |
| sweep_fvg | OOS | next-level | 1632 | 5.2% | -0.029 | 0.026 | 0.055 | 0.040 | 0.954 | -0.67 | 54.0 | 38.1% |
| sweep_fvg | OOS | 2R | 1632 | 21.5% | -0.060 | 0.005 | 0.065 | 0.036 | 0.897 | -1.98 | 37.5 | 25.1% |
| noise_area | IS | next-level | 747 | 27.7% | 0.080 | 0.187 | 0.107 | 0.043 | 1.149 | 1.72 | 100.0 | 14.3% |
| noise_area | IS | 2R | 747 | 26.8% | 0.078 | 0.183 | 0.105 | 0.043 | 1.142 | 1.64 | 100.0 | 14.2% |
| noise_area | OOS | next-level | 703 | 26.7% | 0.010 | 0.106 | 0.096 | 0.045 | 1.018 | 0.22 | 96.5 | 12.5% |
| noise_area | OOS | 2R | 703 | 26.5% | 0.036 | 0.137 | 0.101 | 0.045 | 1.063 | 0.73 | 97.0 | 12.7% |
| fade_5m | IS | next-level | 5518 | 25.9% | -0.119 | 0.011 | 0.131 | 0.052 | 0.826 | -6.08 | 51.0 | 10.0% |
| fade_5m | IS | 2R | 5518 | 26.3% | -0.123 | 0.005 | 0.127 | 0.053 | 0.820 | -6.91 | 33.5 | 10.2% |
| fade_5m | OOS | next-level | 4768 | 27.9% | -0.109 | -0.002 | 0.107 | 0.057 | 0.844 | -5.08 | 31.5 | 7.2% |
| fade_5m | OOS | 2R | 4768 | 27.9% | -0.110 | 0.002 | 0.112 | 0.057 | 0.841 | -5.65 | 45.5 | 7.6% |
| breakout_5m | IS | next-level | 5178 | 24.4% | -0.121 | -0.003 | 0.119 | 0.049 | 0.824 | -6.02 | 14.0 | 11.0% |
| breakout_5m | IS | 2R | 5178 | 25.9% | -0.130 | 0.003 | 0.132 | 0.049 | 0.811 | -7.08 | 17.0 | 10.1% |
| breakout_5m | OOS | next-level | 5320 | 26.8% | -0.058 | 0.059 | 0.117 | 0.057 | 0.917 | -2.66 | 82.5 | 8.6% |
| breakout_5m | OOS | 2R | 5320 | 29.9% | -0.065 | 0.045 | 0.109 | 0.056 | 0.905 | -3.45 | 77.0 | 6.6% |
| sweep_fvg_5m | IS | next-level | 924 | 4.4% | -0.046 | 0.013 | 0.060 | 0.037 | 0.904 | -1.21 | 78.0 | 55.5% |
| sweep_fvg_5m | IS | 2R | 924 | 12.7% | -0.060 | 0.002 | 0.062 | 0.034 | 0.874 | -1.75 | 53.0 | 47.5% |
| sweep_fvg_5m | OOS | next-level | 1028 | 5.1% | 0.025 | 0.069 | 0.044 | 0.032 | 1.052 | 0.59 | 95.5 | 54.8% |
| sweep_fvg_5m | OOS | 2R | 1028 | 14.7% | -0.006 | 0.036 | 0.042 | 0.030 | 0.986 | -0.19 | 90.0 | 46.5% |

## Fixed constants

| Constant | Value |
|---|---:|
| pivot sides (5m) | 3 |
| ATR bars (5m) | 14 |
| EMA fast / slow | 20/50 |
| RSI bars (5m) | 14 |
| MACD fast / slow / signal | 12/26/9 |
| realized vol bars (1m) | 30 |
| volume baseline sessions | 20 |
| opening range minutes | 15 |
| buffer ATR multiple | 0.1 |
| buffer spread multiple | 2.0 |
| spread median bars | 20 |
| index barrier minutes | 120 |
| BTC barrier minutes | 240 |
| sweep return minutes | 15 |
| FVG formation minutes | 30 |
| minimum next level R | 1.0 |
| fallback TP R | 2.0 |
| resistance levels | pdh, onh, orh, swing_high |
| support levels | pdl, onl, orl, swing_low |
| sweep levels | pdh, onh, pdl, onl |
| FVG retrace expiry | session end |
| stop mode | hard intrabar |
| minimum risk / spread | 5 |
| candidate timeframes | 1m and 5m; entries on next 1m open |
| 2R label target | 2 × initial risk from entry fill |
| noise area TP | 2R |
| decision timestamp | just-closed bar open timestamp |
| random benchmark seeds | 200 |
| candidate lockout | actual exit |
| IS years | ≤2021 |
| OOS years | 2022–2024 |
| holdout | 2025+ excluded |

Runtime: 43.69 s
