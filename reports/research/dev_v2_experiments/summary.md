# DEV v2 experiments

**DEV only; Test and Final were not loaded.**

## Conclusions

### What was tested

This was a development-only diagnostic using decisions and realized exits strictly before 2023-01-01. Test was not loaded, and Final remains locked. The one-day and three-day outcomes were rebuilt under the corrected timestamp contract; the old wide-v1 artifacts remain unchanged and are not mixed into these results.

### Corrected one-day baseline

Seven of 34 rule units had positive OOF average net R, but only funding extreme fade also had t > 2. Funding fade remained at +0.2425R per trade, t 2.3729 and PF 1.4935. Corrected Donchian fell to +0.0266R, t 0.8748 and PF 1.0549, versus the erroneous wide-v1 result of about +0.136R. Most of the apparent Donchian edge therefore came from the deadline bug allowing unresolved trades to continue beyond the declared one-day hold.

The deadline is economically important: many of the higher-volume rule units ended 53–79% of their corrected one-day trades by time exit. Funding fade was less dependent on it, with a 25.58% time-exit share.

### E1 — longer hold

The three-day hold did not produce a confirmatory rule. Eleven units improved average OOF net R and 21 worsened, but only three remained positive and none combined positive net R with t > 2. Donchian improved from +0.0266R to +0.0651R, but t reached only 1.5893. Funding fade weakened from +0.2425R to +0.0947R and t fell from 2.3729 to 0.7091. The longer hold reduced time exits, but the additional path and financing risk did not create robust evidence.

### E2 — nested rule portfolio

Both train-only portfolio constructions were negative OOF. Equal risk lost 0.0338R/day, with Sharpe -0.2449, PF 0.9704 and an 83.48% account drawdown. Inverse-volatility sizing reduced the loss to 0.0112R/day, but still had Sharpe -0.0765, PF 0.9903 and a 77.13% drawdown. Those drawdowns are fractions of account equity at the stated 0.5% base risk, not R-unit drawdowns. NQ and SPX contributed positively, but XAU dominated the losses; the portfolio is not economically usable as specified.

ETH contributed exactly zero because the frozen Family-1 replay contains no ETH event parquet. ETH was never covered by Family 1; this is a coverage gap to fix, not evidence that ETH rules had zero returns.

### E3 — intraday momentum

The fixed intraday-momentum rule was negative before costs as well as after them. All signals averaged -0.0341R gross and -0.0731R net, with t -4.2156. The train-fold median filter worsened this to -0.0628R gross and -0.0938R net, with t -3.8479. Spread costs hurt, but do not explain the failure because gross expectancy was already negative. The sign and the 10:00, 15:30 and 16:00 New York timestamps were hand-checked across both DST transitions. E3 does not use wide event labels and was unaffected by the deadline-unit bug.

### Research decision

The corrected evidence does not support promoting Donchian, the three-day variants, either rule portfolio sizing, or this unconditional intraday-momentum specification. Funding fade is the only corrected one-day Family-1 rule with positive OOF net R and t > 2, but nothing here changes its frozen configuration or authorizes another Test look. No result unlocks Final. These are OOF DEV diagnostics, not a new protocol grade, and isolated rule t-statistics remain subject to the existing multiplicity controls.

## Wide-v2 corrected one-day baseline

| Rule | OOF n | Net R | t | PF | Time exit |
|---|---:|---:|---:|---:|---:|
| funding_extreme_fade | 172 | 0.2425 | 2.3729 | 1.4935 | 0.2558 |
| rsi2_mean_reversion | 76 | 0.1000 | 0.8077 | 1.2176 | 0.1184 |
| range_breakout_nr4_nr7 | 1294 | 0.0414 | 1.2738 | 1.0909 | 0.5688 |
| donchian_atr_breakout | 1593 | 0.0266 | 0.8748 | 1.0549 | 0.5279 |
| chart_patterns | 5410 | 0.0050 | 0.4057 | 1.0141 | 0.7372 |
| vix_spike_dip_buy | 95 | 0.0035 | 0.0361 | 1.0079 | 0.0737 |
| trend_following | 2961 | 0.0009 | 0.0648 | 1.0031 | 0.7913 |
| fib_pullback | 5386 | -0.0097 | -0.7943 | 0.9731 | 0.7247 |
| macd_signal | 5447 | -0.0211 | -1.6911 | 0.9448 | 0.6708 |
| ichimoku_cloud | 7244 | -0.0214 | -2.2020 | 0.9364 | 0.7608 |
| btc_order_flow | 1146 | -0.0224 | -0.8391 | 0.9366 | 0.7251 |
| wyckoff_spring_upthrust | 5123 | -0.0250 | -1.9010 | 0.9365 | 0.6810 |
| market_structure_pullback | 1846 | -0.0259 | -1.1715 | 0.9340 | 0.6891 |
| trendline_channel | 6340 | -0.0265 | -2.4767 | 0.9238 | 0.7498 |
| ma_cross | 3057 | -0.0274 | -1.1708 | 0.9516 | 0.3840 |
| price_action_h2l2 | 7770 | -0.0278 | -2.6005 | 0.9286 | 0.6824 |
| ote_zone | 4839 | -0.0293 | -1.9988 | 0.9316 | 0.5892 |
| fvg_retrace | 6423 | -0.0301 | -2.7740 | 0.9159 | 0.7180 |
| vwap_reclaim_reject | 6481 | -0.0316 | -2.9890 | 0.9102 | 0.7422 |
| bollinger:squeeze_breakout | 1050 | -0.0326 | -1.0149 | 0.9256 | 0.6152 |
| liquidity_sweep | 7635 | -0.0334 | -3.1996 | 0.9118 | 0.7075 |
| volume_profile_poc_vah_val | 6855 | -0.0340 | -3.3466 | 0.9029 | 0.7469 |
| bollinger:band_reversion | 5006 | -0.0424 | -3.6900 | 0.8777 | 0.7443 |
| round_number_reaction | 3963 | -0.0437 | -3.0728 | 0.8854 | 0.7058 |
| intraday_momentum | 2123 | -0.0467 | -2.5859 | 0.8720 | 0.7433 |
| session_level_reaction | 4784 | -0.0546 | -3.9539 | 0.8690 | 0.6559 |
| supply_demand_zone_retest | 1177 | -0.0551 | -2.3312 | 0.8516 | 0.2846 |
| order_block_retest | 4034 | -0.0575 | -4.2068 | 0.8484 | 0.5672 |
| sr_touch | 6230 | -0.0613 | -4.9522 | 0.8542 | 0.6615 |
| stochastic | 5399 | -0.0620 | -5.4523 | 0.8295 | 0.7311 |
| candlestick_at_level | 3160 | -0.0670 | -4.2484 | 0.8333 | 0.4063 |
| dow_trend_confirmation | 203 | -0.1357 | -1.6691 | 0.7756 | 0.0739 |
| post_macro_event_reaction:follow | 0 | NA | NA | NA | NA |
| post_macro_event_reaction:fade | 0 | NA | NA | NA | NA |

## E1 — three-day hold

| Rule | OOF n | Net R | Δ Net R | t | Δ t | PF | Δ PF | Time exit | Δ Time exit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| funding_extreme_fade | 161 | 0.0947 | -0.1478 | 0.7091 | -1.6638 | 1.1416 | -0.3519 | 0.1366 | -0.1192 |
| donchian_atr_breakout | 1327 | 0.0651 | 0.0385 | 1.5893 | 0.7145 | 1.1069 | 0.0520 | 0.2992 | -0.2288 |
| candlestick_at_level | 2138 | 0.0059 | 0.0729 | 0.1949 | 4.4434 | 1.0097 | 0.1764 | 0.2881 | -0.1182 |
| fib_pullback | 3184 | -0.0082 | 0.0015 | -0.3416 | 0.4527 | 0.9861 | 0.0130 | 0.3116 | -0.4131 |
| btc_order_flow | 812 | -0.0102 | 0.0122 | -0.3372 | 0.5020 | 0.9720 | 0.0354 | 0.1921 | -0.5330 |
| ma_cross | 2182 | -0.0117 | 0.0157 | -0.3727 | 0.7982 | 0.9815 | 0.0299 | 0.2828 | -0.1013 |
| price_action_h2l2 | 3850 | -0.0168 | 0.0110 | -0.7772 | 1.8233 | 0.9714 | 0.0428 | 0.3190 | -0.3634 |
| wyckoff_spring_upthrust | 5685 | -0.0187 | 0.0064 | -2.0029 | -0.1019 | 0.9440 | 0.0074 | 0.0250 | -0.6561 |
| range_breakout_nr4_nr7 | 1266 | -0.0191 | -0.0605 | -0.6397 | -1.9134 | 0.9627 | -0.1282 | 0.0908 | -0.4779 |
| ote_zone | 3178 | -0.0262 | 0.0030 | -1.1730 | 0.8258 | 0.9546 | 0.0230 | 0.2105 | -0.3787 |
| ichimoku_cloud | 7094 | -0.0306 | -0.0092 | -3.7045 | -1.5025 | 0.9088 | -0.0276 | 0.0496 | -0.7111 |
| intraday_momentum | 2440 | -0.0330 | 0.0137 | -2.0794 | 0.5065 | 0.9116 | 0.0397 | 0.0586 | -0.6847 |
| trend_following | 2116 | -0.0339 | -0.0348 | -1.5932 | -1.6580 | 0.9223 | -0.0808 | 0.3308 | -0.4605 |
| bollinger:band_reversion | 3027 | -0.0402 | 0.0022 | -2.0559 | 1.6341 | 0.9202 | 0.0426 | 0.3515 | -0.3928 |
| chart_patterns | 4653 | -0.0419 | -0.0469 | -3.6949 | -4.1006 | 0.8860 | -0.1281 | 0.0860 | -0.6512 |
| fvg_retrace | 8353 | -0.0450 | -0.0149 | -5.4003 | -2.6263 | 0.8824 | -0.0335 | 0.0171 | -0.7009 |
| market_structure_pullback | 1451 | -0.0467 | -0.0208 | -1.3366 | -0.1652 | 0.9210 | -0.0130 | 0.3694 | -0.3197 |
| macd_signal | 4069 | -0.0500 | -0.0289 | -3.1363 | -1.4452 | 0.8890 | -0.0557 | 0.1887 | -0.4821 |
| supply_demand_zone_retest | 1161 | -0.0511 | 0.0039 | -2.2991 | 0.0321 | 0.8661 | 0.0145 | 0.0086 | -0.2760 |
| round_number_reaction | 4096 | -0.0526 | -0.0089 | -4.7483 | -1.6755 | 0.8510 | -0.0344 | 0.0415 | -0.6643 |
| liquidity_sweep | 4664 | -0.0561 | -0.0227 | -3.4566 | -0.2570 | 0.8854 | -0.0264 | 0.2629 | -0.4447 |
| vwap_reclaim_reject | 5272 | -0.0657 | -0.0341 | -5.8622 | -2.8732 | 0.8316 | -0.0786 | 0.0964 | -0.6458 |
| volume_profile_poc_vah_val | 6115 | -0.0661 | -0.0321 | -6.7530 | -3.4065 | 0.8241 | -0.0788 | 0.0957 | -0.6512 |
| stochastic | 6172 | -0.0693 | -0.0073 | -7.0427 | -1.5904 | 0.8211 | -0.0083 | 0.0535 | -0.6776 |
| session_level_reaction | 5225 | -0.0700 | -0.0154 | -6.9274 | -2.9736 | 0.8113 | -0.0576 | 0.0297 | -0.6263 |
| trendline_channel | 3132 | -0.0716 | -0.0451 | -3.2478 | -0.7711 | 0.8715 | -0.0523 | 0.4400 | -0.3099 |
| order_block_retest | 3699 | -0.0726 | -0.0151 | -5.6183 | -1.4115 | 0.8192 | -0.0292 | 0.0584 | -0.5088 |
| bollinger:squeeze_breakout | 1081 | -0.0917 | -0.0590 | -3.3558 | -2.3409 | 0.8081 | -0.1175 | 0.0130 | -0.6023 |
| vix_spike_dip_buy | 97 | -0.0983 | -0.1018 | -1.0738 | -1.1098 | 0.7734 | -0.2345 | 0.0309 | -0.0428 |
| sr_touch | 3319 | -0.0993 | -0.0379 | -4.2659 | 0.6863 | 0.8401 | -0.0141 | 0.3465 | -0.3150 |
| dow_trend_confirmation | 203 | -0.1459 | -0.0102 | -1.6264 | 0.0426 | 0.7875 | 0.0119 | 0.0099 | -0.0640 |
| rsi2_mean_reversion | 75 | -0.2517 | -0.3517 | -1.7609 | -2.5686 | 0.6544 | -0.5632 | 0.0400 | -0.0784 |
| post_macro_event_reaction:follow | 0 | NA | NA | NA | NA | NA | NA | NA | NA |
| post_macro_event_reaction:fade | 0 | NA | NA | NA | NA | NA | NA | NA | NA |

## E2 — nested rule portfolio

MDD is the fraction of account equity at 0.5% base risk per accepted trade.

| Sizing | Trades | Trades/day | Net R/day | Sharpe | Account MDD | PF | Contribution |
|---|---:|---:|---:|---:|---:|---:|---|
| equal_risk | 10821 | 1.9757 | -0.0338 | -0.2449 | -0.8348 | 0.9704 | {"BTCUSDT": -11.963495667461878, "ETHUSDT": 0.0, "USA500IDXUSD": 9.636298858740522, "USATECHIDXUSD": 35.301564232582464, "XAUUSD": -218.24694479292336} |
| inverse_volatility | 10821 | 1.9757 | -0.0112 | -0.0765 | -0.7713 | 0.9903 | {"BTCUSDT": 6.288968416203332, "ETHUSDT": 0.0, "USA500IDXUSD": 20.51250498991122, "USATECHIDXUSD": 59.532515229003415, "XAUUSD": -147.51397745206287} |

## E3 — intraday momentum

| Variant | n | Gross R/trade | Net R/trade | Hit | t | Sharpe | MDD | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all_nonzero | 1999 | -0.0341 | -0.0731 | 0.4742 | -4.2156 | -1.6225 | -0.5377 | 0.7811 |
| above_train_median | 966 | -0.0628 | -0.0938 | 0.4762 | -3.8479 | -1.4324 | -0.3886 | 0.7249 |

### E3 all_nonzero by market/year

| Scope | n | Gross R/trade | Net R/trade | Hit | t |
|---|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 1000 | -0.0311 | -0.0628 | 0.4800 | -2.7763 |
| USA500IDXUSD | 999 | -0.0370 | -0.0834 | 0.4685 | -3.1715 |
| year 2019 | 495 | -0.0186 | -0.0772 | 0.4990 | -2.4072 |
| year 2020 | 502 | 0.0012 | -0.0347 | 0.4821 | -0.9081 |
| year 2021 | 502 | -0.0980 | -0.1381 | 0.4343 | -3.8704 |
| year 2022 | 500 | -0.0206 | -0.0422 | 0.4820 | -1.3146 |

### E3 above_train_median by market/year

| Scope | n | Gross R/trade | Net R/trade | Hit | t |
|---|---:|---:|---:|---:|---:|
| USATECHIDXUSD | 539 | -0.0632 | -0.0904 | 0.4694 | -2.9330 |
| USA500IDXUSD | 427 | -0.0623 | -0.0982 | 0.4848 | -2.5074 |
| year 2019 | 203 | -0.0510 | -0.0998 | 0.4828 | -2.0838 |
| year 2020 | 277 | -0.0139 | -0.0435 | 0.4801 | -0.8652 |
| year 2021 | 165 | -0.2563 | -0.2876 | 0.3879 | -4.6600 |
| year 2022 | 321 | -0.0130 | -0.0339 | 0.5140 | -0.8704 |

### E3 hand checks (ET session conversion)

| Market | Session | Prior 16:00 mid | 10:00 mid | Signal | Side | Entry UTC | Entry | Exit | Gross R | Net R |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| USA500IDXUSD | 2019-03-08 | 2749.0000 | 2727.3000 | -0.007894 | -1 | 2019-03-08 20:30:00+00:00 | 2731.1690 | 2743.5300 | -1.5554 | -1.6294 |
| USATECHIDXUSD | 2019-03-08 | 7027.0050 | 6960.9055 | -0.009406 | -1 | 2019-03-08 20:30:00+00:00 | 6983.7690 | 7017.2410 | -1.2872 | -1.3298 |
| USA500IDXUSD | 2019-03-11 | 2743.2000 | 2760.7005 | 0.006380 | 1 | 2019-03-11 19:30:00+00:00 | 2781.2300 | 2782.7700 | 0.3809 | 0.2933 |
| USATECHIDXUSD | 2019-03-11 | 7016.7005 | 7092.5005 | 0.010803 | 1 | 2019-03-11 19:30:00+00:00 | 7163.2300 | 7162.2700 | 0.0108 | -0.0517 |
| USA500IDXUSD | 2019-11-04 | 3066.5000 | 3081.2000 | 0.004794 | 1 | 2019-11-04 20:30:00+00:00 | 3076.2300 | 3078.4690 | 0.7297 | 0.6051 |
| USATECHIDXUSD | 2019-11-04 | 8160.8950 | 8215.6000 | 0.006703 | 1 | 2019-11-04 20:30:00+00:00 | 8207.6410 | 8210.2600 | 0.2632 | 0.1918 |
