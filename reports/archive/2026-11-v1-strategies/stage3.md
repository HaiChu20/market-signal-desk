# Stage 3 — walk-forward ML meta-model

Rows: 132955; symbols: USATECHIDXUSD, USA500IDXUSD, BTCUSDT; dates: 2018-01-02..2024-12-31; 2025+ excluded.
Target: label_2r. Features are Stage 2 snapshot columns plus side and fixed one-hot setup/symbol columns.
Purging: training label_end_ts_2r < validation start − 1 day; no training decisions at/after validation start.
Isotonic calibration is fit only on 2021 inner-fold predictions. OOS threshold is selected from IS folds by maximizing pooled validation mean R, then frozen.

## Fixed parameters

| Parameter | Value |
|---|---:|
| Logistic | L2, C=1.0, standard scaled, max_iter=1000 |
| LightGBM | leaves=15, min_data_in_leaf=200, lr=0.03, trees=400 |
| LightGBM sampling | feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1 |
| LightGBM deterministic threads | 4; deterministic=True; force_col_wise=True |
| Seeds | 0 (model, bagging, feature, data, permutations) |
| Threshold candidates | 0, 0.1, 0.2, 0.3 |
| Inner folds | 2019, 2020, 2021; expanding window |
| OOS folds | 2022, 2023, 2024; annual retrain |
| Purge | label end < validation start − 1 day |
| Calibration | isotonic on 2021 inner fold; out-of-bounds clipped |
| Holdout | 2025+ never loaded |

## logistic

Selected IS threshold: 0.0

IS folds: AUC 0.572; logloss 0.592/0.570; Brier 0.190/0.191 (base rate 0.257; n=51941)
OOS: AUC 0.568; logloss 0.577/0.584; Brier 0.195/0.198 (base rate 0.271; n=66184)

| Split | Decile | Mean p | Hit rate | Mean R | n |
|---|---:|---:|---:|---:|---:|
| IS | 1 | 0.140 | 11.7% | -0.143 | 5195 |
| IS | 2 | 0.184 | 19.1% | -0.082 | 5194 |
| IS | 3 | 0.228 | 24.6% | -0.092 | 5194 |
| IS | 4 | 0.248 | 26.0% | -0.125 | 5194 |
| IS | 5 | 0.267 | 28.6% | -0.114 | 5194 |
| IS | 6 | 0.290 | 29.3% | -0.118 | 5194 |
| IS | 7 | 0.294 | 28.6% | -0.163 | 5194 |
| IS | 8 | 0.310 | 28.5% | -0.179 | 5194 |
| IS | 9 | 0.311 | 29.9% | -0.153 | 5194 |
| IS | 10 | 0.372 | 31.1% | -0.112 | 5194 |
| OOS | 1 | 0.156 | 12.6% | -0.105 | 6619 |
| OOS | 2 | 0.195 | 21.0% | -0.052 | 6618 |
| OOS | 3 | 0.246 | 26.4% | -0.069 | 6618 |
| OOS | 4 | 0.265 | 28.0% | -0.117 | 6619 |
| OOS | 5 | 0.287 | 29.1% | -0.129 | 6618 |
| OOS | 6 | 0.294 | 30.1% | -0.123 | 6618 |
| OOS | 7 | 0.297 | 31.0% | -0.111 | 6619 |
| OOS | 8 | 0.310 | 30.9% | -0.129 | 6618 |
| OOS | 9 | 0.311 | 30.4% | -0.133 | 6618 |
| OOS | 10 | 0.318 | 31.6% | -0.113 | 6619 |

### IS filtered vs unfiltered

| Setup | Filter | N | Avg R | t-stat | Daily Sharpe | MDD |
|---|---|---:|---:|---:|---:|---:|
| ALL | unfiltered | 51941 | -0.128 | -22.32 | -4.58 | -100.0% |
| ALL | filtered | 2274 | -0.094 | -3.22 | -0.55 | -40.4% |
| fade | unfiltered | 15169 | -0.151 | -13.75 | -3.34 | -92.5% |
| fade | filtered | 898 | -0.130 | -2.81 | -0.07 | -10.0% |
| breakout | unfiltered | 10616 | -0.130 | -10.12 | -3.00 | -98.0% |
| breakout | filtered | 542 | -0.085 | -1.41 | -0.60 | -22.8% |
| sweep_fvg | unfiltered | 2927 | -0.091 | -4.20 | -2.15 | -83.9% |
| sweep_fvg | filtered | 7 | -0.593 | -1.42 | -1.76 | -6.5% |
| noise_area | unfiltered | 1210 | 0.080 | 2.13 | 1.01 | -12.2% |
| noise_area | filtered | 120 | 0.059 | 0.45 | 0.24 | -3.3% |
| fade_5m | unfiltered | 10063 | -0.143 | -11.11 | -3.03 | -99.0% |
| fade_5m | filtered | 309 | -0.070 | -0.87 | 0.10 | -6.4% |
| breakout_5m | unfiltered | 10125 | -0.121 | -9.26 | -3.07 | -98.2% |
| breakout_5m | filtered | 398 | -0.082 | -1.17 | -0.64 | -15.4% |
| sweep_fvg_5m | unfiltered | 1831 | -0.078 | -3.21 | -1.36 | -61.9% |
| sweep_fvg_5m | filtered | 0 | nan | nan | nan | nan% |

### OOS filtered vs unfiltered

| Setup | Filter | N | Avg R | t-stat | Daily Sharpe | MDD |
|---|---|---:|---:|---:|---:|---:|
| ALL | unfiltered | 66184 | -0.108 | -20.96 | -4.84 | -100.0% |
| ALL | filtered | 566 | -0.208 | -3.68 | -0.61 | -13.9% |
| fade | unfiltered | 19198 | -0.150 | -15.30 | -3.99 | -95.7% |
| fade | filtered | 234 | -0.202 | -2.27 | -1.01 | -6.3% |
| breakout | unfiltered | 13855 | -0.104 | -9.05 | -3.82 | -98.7% |
| breakout | filtered | 151 | -0.201 | -1.84 | -0.59 | -5.4% |
| sweep_fvg | unfiltered | 3932 | -0.059 | -3.03 | -0.47 | -49.5% |
| sweep_fvg | filtered | 0 | nan | nan | nan | nan% |
| noise_area | unfiltered | 1525 | 0.037 | 1.11 | 1.24 | -5.2% |
| noise_area | filtered | 37 | -0.223 | -1.01 | -0.36 | -1.0% |
| fade_5m | unfiltered | 11810 | -0.122 | -10.09 | -3.57 | -98.1% |
| fade_5m | filtered | 43 | -0.160 | -0.75 | 0.37 | -1.2% |
| breakout_5m | unfiltered | 13331 | -0.088 | -7.61 | -3.52 | -98.5% |
| breakout_5m | filtered | 101 | -0.247 | -1.88 | -0.44 | -4.5% |
| sweep_fvg_5m | unfiltered | 2533 | -0.015 | -0.70 | -0.31 | -31.4% |
| sweep_fvg_5m | filtered | 0 | nan | nan | nan | nan% |

### OOS permutation importance (ΔAUC)

| Rank | Feature | ΔAUC |
|---:|---|---:|
| 1 | sl_distance_atr | 0.03786 |
| 2 | minutes_since_open | 0.01282 |
| 3 | distance_orl_atr | 0.00429 |
| 4 | distance_pdh_atr | 0.00234 |
| 5 | ema20_slope_60m | 0.00209 |
| 6 | distance_orh_atr | 0.00206 |
| 7 | distance_onh_atr | 0.00201 |
| 8 | price_vs_vwap_atr | 0.00179 |
| 9 | setup=sweep_fvg_5m | 0.00177 |
| 10 | distance_onl_atr | 0.00173 |
| 11 | position_prior_range | 0.00146 |
| 12 | distance_pdl_atr | 0.00075 |
| 13 | setup=breakout_5m | 0.00071 |
| 14 | setup=breakout | 0.00064 |
| 15 | gap_atr | 0.00050 |
| 16 | distance_swing_high_2_atr | 0.00046 |
| 17 | distance_swing_low_3_atr | 0.00045 |
| 18 | distance_swing_high_atr | 0.00035 |
| 19 | distance_swing_high_1_atr | 0.00034 |
| 20 | setup=sweep_fvg | 0.00033 |

### OOS feature-group ablation (ΔAUC from full)

| Feature group removed | ΔAUC |
|---|---:|
| levels | -0.00959 |
| trend | -0.00012 |
| oscillators | 0.00006 |
| patterns | 0.00047 |
| volatility_volume | 0.00038 |
| time | -0.00455 |
| setup_symbol | 0.00157 |

## lightgbm

Selected IS threshold: 0.3

IS folds: AUC 0.580; logloss 0.576/0.570; Brier 0.188/0.191 (base rate 0.257; n=51941)
OOS: AUC 0.574; logloss 0.572/0.584; Brier 0.193/0.198 (base rate 0.271; n=66184)

| Split | Decile | Mean p | Hit rate | Mean R | n |
|---|---:|---:|---:|---:|---:|
| IS | 1 | 0.128 | 9.8% | -0.127 | 5195 |
| IS | 2 | 0.161 | 17.5% | -0.114 | 5194 |
| IS | 3 | 0.235 | 25.9% | -0.120 | 5194 |
| IS | 4 | 0.258 | 26.4% | -0.147 | 5194 |
| IS | 5 | 0.278 | 27.7% | -0.169 | 5194 |
| IS | 6 | 0.301 | 30.3% | -0.093 | 5194 |
| IS | 7 | 0.301 | 29.6% | -0.136 | 5194 |
| IS | 8 | 0.307 | 29.2% | -0.150 | 5194 |
| IS | 9 | 0.308 | 30.3% | -0.116 | 5194 |
| IS | 10 | 0.331 | 30.7% | -0.107 | 5194 |
| OOS | 1 | 0.137 | 8.9% | -0.106 | 6619 |
| OOS | 2 | 0.189 | 21.1% | -0.084 | 6618 |
| OOS | 3 | 0.260 | 27.7% | -0.093 | 6618 |
| OOS | 4 | 0.284 | 28.6% | -0.137 | 6619 |
| OOS | 5 | 0.301 | 30.3% | -0.127 | 6618 |
| OOS | 6 | 0.301 | 31.1% | -0.104 | 6618 |
| OOS | 7 | 0.302 | 30.8% | -0.108 | 6619 |
| OOS | 8 | 0.306 | 31.7% | -0.091 | 6618 |
| OOS | 9 | 0.308 | 29.6% | -0.140 | 6618 |
| OOS | 10 | 0.308 | 31.5% | -0.092 | 6619 |

### IS filtered vs unfiltered

| Setup | Filter | N | Avg R | t-stat | Daily Sharpe | MDD |
|---|---|---:|---:|---:|---:|---:|
| ALL | unfiltered | 51941 | -0.128 | -22.32 | -4.58 | -100.0% |
| ALL | filtered | 190 | -0.064 | -0.63 | -0.12 | -5.6% |
| fade | unfiltered | 15169 | -0.151 | -13.75 | -3.34 | -92.5% |
| fade | filtered | 54 | 0.338 | 1.67 | 1.01 | -0.8% |
| breakout | unfiltered | 10616 | -0.130 | -10.12 | -3.00 | -98.0% |
| breakout | filtered | 48 | -0.369 | -2.05 | -1.11 | -4.7% |
| sweep_fvg | unfiltered | 2927 | -0.091 | -4.20 | -2.15 | -83.9% |
| sweep_fvg | filtered | 0 | nan | nan | nan | nan% |
| noise_area | unfiltered | 1210 | 0.080 | 2.13 | 1.01 | -12.2% |
| noise_area | filtered | 10 | 0.442 | 0.88 | 1.39 | -0.2% |
| fade_5m | unfiltered | 10063 | -0.143 | -11.11 | -3.03 | -99.0% |
| fade_5m | filtered | 29 | -0.251 | -1.05 | -0.44 | -1.6% |
| breakout_5m | unfiltered | 10125 | -0.121 | -9.26 | -3.07 | -98.2% |
| breakout_5m | filtered | 49 | -0.199 | -1.04 | -0.87 | -3.9% |
| sweep_fvg_5m | unfiltered | 1831 | -0.078 | -3.21 | -1.36 | -61.9% |
| sweep_fvg_5m | filtered | 0 | nan | nan | nan | nan% |

### OOS filtered vs unfiltered

| Setup | Filter | N | Avg R | t-stat | Daily Sharpe | MDD |
|---|---|---:|---:|---:|---:|---:|
| ALL | unfiltered | 66184 | -0.108 | -20.96 | -4.84 | -100.0% |
| ALL | filtered | 2 | -1.038 | -239.73 | -3.11 | -0.1% |
| fade | unfiltered | 19198 | -0.150 | -15.30 | -3.99 | -95.7% |
| fade | filtered | 1 | -1.033 | nan | nan | 0.0% |
| breakout | unfiltered | 13855 | -0.104 | -9.05 | -3.82 | -98.7% |
| breakout | filtered | 0 | nan | nan | nan | nan% |
| sweep_fvg | unfiltered | 3932 | -0.059 | -3.03 | -0.47 | -49.5% |
| sweep_fvg | filtered | 0 | nan | nan | nan | nan% |
| noise_area | unfiltered | 1525 | 0.037 | 1.11 | 1.24 | -5.2% |
| noise_area | filtered | 0 | nan | nan | nan | nan% |
| fade_5m | unfiltered | 11810 | -0.122 | -10.09 | -3.57 | -98.1% |
| fade_5m | filtered | 1 | -1.042 | nan | nan | 0.0% |
| breakout_5m | unfiltered | 13331 | -0.088 | -7.61 | -3.52 | -98.5% |
| breakout_5m | filtered | 0 | nan | nan | nan | nan% |
| sweep_fvg_5m | unfiltered | 2533 | -0.015 | -0.70 | -0.31 | -31.4% |
| sweep_fvg_5m | filtered | 0 | nan | nan | nan | nan% |

### OOS permutation importance (ΔAUC)

| Rank | Feature | ΔAUC |
|---:|---|---:|
| 1 | sl_distance_atr | 0.03755 |
| 2 | minutes_since_open | 0.02122 |
| 3 | position_prior_range | 0.00152 |
| 4 | distance_swing_low_atr | 0.00127 |
| 5 | distance_swing_low_2_atr | 0.00120 |
| 6 | distance_onh_atr | 0.00098 |
| 7 | atr_over_price | 0.00090 |
| 8 | tp_sl_ratio | 0.00090 |
| 9 | setup=sweep_fvg_5m | 0.00086 |
| 10 | distance_orl_atr | 0.00068 |
| 11 | spread_atr | 0.00064 |
| 12 | symbol=BTCUSDT | 0.00047 |
| 13 | volume_vs_20_session_median | 0.00043 |
| 14 | rsi14_5m | 0.00034 |
| 15 | ema20_slope_5m | 0.00031 |
| 16 | distance_onl_atr | 0.00028 |
| 17 | setup=sweep_fvg | 0.00027 |
| 18 | gap_atr | 0.00021 |
| 19 | ema50_slope_60m | 0.00019 |
| 20 | distance_swing_high_atr | 0.00018 |

### OOS feature-group ablation (ΔAUC from full)

| Feature group removed | ΔAUC |
|---|---:|
| levels | -0.01202 |
| trend | 0.00297 |
| oscillators | 0.00063 |
| patterns | 0.00164 |
| volatility_volume | 0.00151 |
| time | -0.00781 |
| setup_symbol | 0.00010 |

Runtime: 36.24 s
