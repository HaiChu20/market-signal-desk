# Wide-v1 Family 1 pure-rules DEV retest

**Development only. Test and Final were not loaded. No ML was used.**

Each CPCV training split selects one fixed SL/TP cell by mean net R; the test events receive only that fold-trained cell, followed by the shared one-position-per-symbol gate.

| Rank | Unit | Events | OOF trades | Trades/yr | Hit | Net avg R | t | PF | Sharpe | MDD | DSR | In-sample best SL/TP-R | Result |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | funding_extreme_fade | 183 | 172 | 58.1694 | 0.4942 | 0.2425 | 2.3729 | 1.4935 | 1.3596 | -0.0391 | 0.7421 | 1.5/2 | OOF > 0, t > 2 |
| 2 | donchian_atr_breakout | 1,996 | 1,084 | 72.3184 | 0.3515 | 0.1356 | 2.7455 | 1.2217 | 0.6569 | -0.0879 | 0.0759 | 3/3 | OOF > 0, t > 2 |
| 3 | fib_pullback | 14,340 | 2,541 | 169.8239 | 0.4065 | 0.0450 | 1.7438 | 1.0932 | 0.4317 | -0.1592 | 0.0114 | 4/3 | does not pass |
| 4 | market_structure_pullback | 2,250 | 1,326 | 88.7601 | 0.3424 | 0.0325 | 0.7970 | 1.0552 | 0.2060 | -0.2116 | 0.0009 | 4/3 | does not pass |
| 5 | ote_zone | 12,539 | 2,529 | 169.0358 | 0.3503 | 0.0281 | 0.9953 | 1.0507 | 0.2413 | -0.2088 | 0.0014 | 4/3 | does not pass |
| 6 | volume_profile_poc_vah_val | 39,675 | 2,954 | 196.9980 | 0.4100 | 0.0241 | 1.0639 | 1.0518 | 0.2653 | -0.2076 | 0.0018 | 4/3 | does not pass |
| 7 | chart_patterns | 12,594 | 2,614 | 174.3441 | 0.3776 | 0.0224 | 0.8598 | 1.0433 | 0.2190 | -0.1805 | 0.0010 | 4/3 | does not pass |
| 8 | trend_following | 4,860 | 1,512 | 102.8413 | 0.3843 | 0.0144 | 0.4304 | 1.0287 | 0.1070 | -0.1803 | 0.0003 | 4/3 | does not pass |
| 9 | price_action_h2l2 | 40,574 | 3,068 | 205.0412 | 0.4074 | 0.0135 | 0.6244 | 1.0299 | 0.1528 | -0.3113 | 0.0004 | 4/3 | does not pass |
| 10 | range_breakout_nr4_nr7 | 2,235 | 1,110 | 74.2325 | 0.4036 | 0.0108 | 0.2800 | 1.0192 | 0.0712 | -0.2262 | 0.0001 | 4/2 | does not pass |
| 11 | candlestick_at_level | 3,901 | 1,959 | 130.6517 | 0.3430 | 0.0101 | 0.3005 | 1.0167 | 0.0734 | -0.3493 | 0.0001 | 4/3 | does not pass |
| 12 | ma_cross | 3,513 | 1,912 | 127.8390 | 0.3311 | -0.0048 | -0.1383 | 0.9924 | -0.0338 | -0.3455 | 0.0000 | 3/3 | does not pass |
| 13 | trendline_channel | 20,744 | 2,729 | 181.9952 | 0.3921 | -0.0112 | -0.4825 | 0.9764 | -0.1216 | -0.3181 | 0.0000 | 4/3 | does not pass |
| 14 | fvg_retrace | 28,870 | 2,762 | 184.2195 | 0.3827 | -0.0141 | -0.6101 | 0.9706 | -0.1517 | -0.4151 | 0.0000 | 4/3 | does not pass |
| 15 | macd_signal | 10,139 | 2,892 | 192.8865 | 0.3624 | -0.0145 | -0.5699 | 0.9741 | -0.1422 | -0.3332 | 0.0000 | 4/3 | does not pass |
| 16 | ichimoku_cloud | 39,040 | 3,023 | 201.5882 | 0.4148 | -0.0179 | -0.8388 | 0.9614 | -0.2078 | -0.4352 | 0.0000 | 4/3 | does not pass |
| 17 | liquidity_sweep | 90,867 | 3,466 | 231.1547 | 0.3840 | -0.0182 | -0.8442 | 0.9642 | -0.2158 | -0.4532 | 0.0000 | 4/3 | does not pass |
| 18 | wyckoff_spring_upthrust | 10,592 | 2,872 | 191.5498 | 0.3931 | -0.0206 | -0.8849 | 0.9612 | -0.2196 | -0.4828 | 0.0000 | 4/2 | does not pass |
| 19 | intraday_momentum | 11,275 | 442 | 110.6725 | 0.2670 | -0.0218 | -0.2739 | 0.9704 | -0.3520 | -0.2263 | 0.0121 | 4/3 | does not pass |
| 20 | btc_order_flow | 5,859 | 1,146 | 381.9954 | 0.4520 | -0.0224 | -0.8391 | 0.9366 | -0.4941 | -0.1715 | 0.0051 | 4/3 | does not pass |
| 21 | vwap_reclaim_reject | 23,822 | 3,077 | 205.2073 | 0.3715 | -0.0332 | -1.4141 | 0.9391 | -0.3607 | -0.4987 | 0.0000 | 4/3 | does not pass |
| 22 | order_block_retest | 9,200 | 2,158 | 143.9288 | 0.3336 | -0.0372 | -1.2821 | 0.9329 | -0.3117 | -0.4535 | 0.0000 | 4/3 | does not pass |
| 23 | supply_demand_zone_retest | 3,856 | 1,359 | 90.9430 | 0.4297 | -0.0486 | -1.4927 | 0.9043 | -0.3754 | -0.4366 | 0.0000 | 4/3 | does not pass |
| 24 | round_number_reaction | 13,762 | 1,973 | 131.5963 | 0.3624 | -0.0505 | -1.7342 | 0.9063 | -0.4258 | -0.4680 | 0.0000 | 4/3 | does not pass |
| 25 | bollinger:band_reversion | 8,346 | 3,330 | 222.1842 | 0.3474 | -0.0641 | -2.6739 | 0.8960 | -0.6537 | -0.7358 | 0.0000 | 4/2 | does not pass |
| 26 | stochastic | 12,533 | 3,336 | 222.4829 | 0.4844 | -0.0653 | -3.6332 | 0.8545 | -0.8878 | -0.6935 | 0.0000 | 4/3 | does not pass |
| 27 | session_level_reaction | 8,780 | 2,558 | 170.6338 | 0.3448 | -0.0693 | -2.5300 | 0.8850 | -0.6410 | -0.6682 | 0.0000 | 4/3 | does not pass |
| 28 | sr_touch | 102,120 | 3,073 | 204.9470 | 0.3482 | -0.0713 | -2.9622 | 0.8754 | -0.6808 | -0.7822 | 0.0000 | 4/3 | does not pass |
| 29 | vix_spike_dip_buy | 124 | 121 | 31.9942 | 0.6612 | -0.0816 | -1.0827 | 0.7849 | -0.4214 | -0.0736 | 0.0006 | 4/3 | does not pass |
| 30 | bollinger:squeeze_breakout | 1,144 | 976 | 65.1335 | 0.4211 | -0.1095 | -2.9343 | 0.8016 | -0.7407 | -0.4508 | 0.0000 | 4/3 | does not pass |
| 31 | dow_trend_confirmation | 203 | 203 | 14.8714 | 0.3596 | -0.1250 | -1.3955 | 0.8140 | -0.3807 | -0.1593 | 0.0000 | 1.5/1 | does not pass |
| 32 | rsi2_mean_reversion | 92 | 75 | 29.2369 | 0.2400 | -0.2677 | -1.6692 | 0.6565 | -0.7295 | -0.1125 | 0.0013 | 2/1 | does not pass |
| 33 | post_macro_event_reaction:follow | 0 | 0 | NA | NA | NA | NA | NA | NA | NA | NA | NA | does not pass |
| 34 | post_macro_event_reaction:fade | 0 | 0 | NA | NA | NA | NA | NA | NA | NA | NA | NA | does not pass |

## Time exits by geometry

| SL ATR | TP R | Rows | Time exits | Share |
|---:|---:|---:|---:|---:|
| 1 | 0.5 | 540,065 | 146 | 0.0003 |
| 1 | 1 | 540,065 | 718 | 0.0013 |
| 1 | 1.5 | 540,065 | 2,015 | 0.0037 |
| 1 | 2 | 540,065 | 4,174 | 0.0077 |
| 1 | 3 | 540,065 | 10,123 | 0.0187 |
| 1.5 | 0.5 | 540,065 | 1,146 | 0.0021 |
| 1.5 | 1 | 540,065 | 5,388 | 0.0100 |
| 1.5 | 1.5 | 540,065 | 12,026 | 0.0223 |
| 1.5 | 2 | 540,065 | 19,168 | 0.0355 |
| 1.5 | 3 | 540,065 | 30,872 | 0.0572 |
| 2 | 0.5 | 540,065 | 4,690 | 0.0087 |
| 2 | 1 | 540,065 | 16,333 | 0.0302 |
| 2 | 1.5 | 540,065 | 29,094 | 0.0539 |
| 2 | 2 | 540,065 | 39,195 | 0.0726 |
| 2 | 3 | 540,065 | 53,205 | 0.0985 |
| 3 | 0.5 | 540,065 | 20,438 | 0.0378 |
| 3 | 1 | 540,065 | 46,630 | 0.0863 |
| 3 | 1.5 | 540,065 | 64,744 | 0.1199 |
| 3 | 2 | 540,065 | 76,636 | 0.1419 |
| 3 | 3 | 540,065 | 91,513 | 0.1694 |
| 4 | 0.5 | 540,065 | 40,493 | 0.0750 |
| 4 | 1 | 540,065 | 74,617 | 0.1382 |
| 4 | 1.5 | 540,065 | 94,090 | 0.1742 |
| 4 | 2 | 540,065 | 106,803 | 0.1978 |
| 4 | 3 | 540,065 | 125,124 | 0.2317 |

## Per-market OOF metrics

| Unit | Market | Events | OOF n | Net avg R | t | PF | Sharpe | MDD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| funding_extreme_fade | BTCUSDT | 183 | 172 | 0.2425 | 2.3729 | 1.4935 | 1.3596 | -0.0391 |
| funding_extreme_fade | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| donchian_atr_breakout | USATECHIDXUSD | 472 | 196 | 0.1876 | 1.4793 | 1.2755 | 0.8031 | -0.0450 |
| donchian_atr_breakout | USA500IDXUSD | 459 | 160 | 0.3668 | 2.5038 | 1.5766 | 1.2245 | -0.0299 |
| donchian_atr_breakout | XAUUSD | 906 | 586 | 0.0849 | 1.2664 | 1.1336 | 0.2766 | -0.1042 |
| donchian_atr_breakout | BTCUSDT | 159 | 142 | 0.0123 | 0.1436 | 1.0317 | 0.0843 | -0.0546 |
| donchian_atr_breakout | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| fib_pullback | USATECHIDXUSD | 1,892 | 212 | 0.3421 | 2.7046 | 1.5340 | 1.3100 | -0.0587 |
| fib_pullback | USA500IDXUSD | 1,971 | 186 | 0.1789 | 1.3845 | 1.2658 | 0.6025 | -0.0497 |
| fib_pullback | XAUUSD | 7,904 | 1,265 | 0.0035 | 0.0918 | 1.0065 | -0.0188 | -0.1644 |
| fib_pullback | BTCUSDT | 2,573 | 878 | 0.0047 | 0.1569 | 1.0141 | 0.0894 | -0.1040 |
| fib_pullback | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| market_structure_pullback | USATECHIDXUSD | 336 | 164 | 0.1662 | 1.1799 | 1.2377 | 0.5308 | -0.0806 |
| market_structure_pullback | USA500IDXUSD | 321 | 156 | 0.0062 | 0.0453 | 1.0084 | -0.0689 | -0.0850 |
| market_structure_pullback | XAUUSD | 1,227 | 711 | 0.0214 | 0.3701 | 1.0341 | 0.0581 | -0.1669 |
| market_structure_pullback | BTCUSDT | 366 | 295 | -0.0011 | -0.0214 | 0.9968 | -0.0124 | -0.0742 |
| market_structure_pullback | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| ote_zone | USATECHIDXUSD | 1,811 | 296 | 0.2334 | 2.2241 | 1.3526 | 0.9567 | -0.0599 |
| ote_zone | USA500IDXUSD | 1,842 | 248 | 0.2423 | 2.1001 | 1.3639 | 0.9120 | -0.0610 |
| ote_zone | XAUUSD | 7,403 | 1,340 | -0.0214 | -0.5510 | 0.9636 | -0.1553 | -0.2517 |
| ote_zone | BTCUSDT | 1,483 | 645 | -0.0459 | -1.2351 | 0.8825 | -0.7082 | -0.2193 |
| ote_zone | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| volume_profile_poc_vah_val | USATECHIDXUSD | 5,578 | 247 | 0.1487 | 1.3155 | 1.2152 | 0.4789 | -0.1572 |
| volume_profile_poc_vah_val | USA500IDXUSD | 4,848 | 204 | -0.0101 | -0.0874 | 0.9859 | -0.2569 | -0.1216 |
| volume_profile_poc_vah_val | XAUUSD | 22,791 | 1,409 | 0.0162 | 0.4824 | 1.0330 | -0.0035 | -0.2082 |
| volume_profile_poc_vah_val | BTCUSDT | 6,458 | 1,094 | 0.0125 | 0.4565 | 1.0373 | 0.2626 | -0.1696 |
| volume_profile_poc_vah_val | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| chart_patterns | USATECHIDXUSD | 1,820 | 257 | -0.0674 | -0.6498 | 0.9103 | -0.1907 | -0.1182 |
| chart_patterns | USA500IDXUSD | 1,787 | 193 | 0.1553 | 1.2321 | 1.2271 | 0.5684 | -0.1141 |
| chart_patterns | XAUUSD | 6,969 | 1,319 | 0.0263 | 0.6862 | 1.0475 | 0.1833 | -0.1366 |
| chart_patterns | BTCUSDT | 2,018 | 845 | 0.0131 | 0.4015 | 1.0376 | 0.2296 | -0.1817 |
| chart_patterns | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| trend_following | USATECHIDXUSD | 759 | 156 | 0.1557 | 1.1253 | 1.2299 | 0.5070 | -0.0471 |
| trend_following | USA500IDXUSD | 651 | 130 | 0.0066 | 0.0455 | 1.0093 | -0.0993 | -0.0799 |
| trend_following | XAUUSD | 2,709 | 795 | -0.0352 | -0.7435 | 0.9359 | -0.2658 | -0.2205 |
| trend_following | BTCUSDT | 741 | 431 | 0.0572 | 1.3386 | 1.1969 | 0.7728 | -0.0511 |
| trend_following | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| price_action_h2l2 | USATECHIDXUSD | 5,939 | 226 | 0.1731 | 1.4879 | 1.2577 | 0.4483 | -0.0956 |
| price_action_h2l2 | USA500IDXUSD | 5,849 | 239 | 0.0029 | 0.0272 | 1.0041 | -0.1040 | -0.1290 |
| price_action_h2l2 | XAUUSD | 22,435 | 1,425 | 0.0229 | 0.6943 | 1.0480 | 0.1136 | -0.1463 |
| price_action_h2l2 | BTCUSDT | 6,351 | 1,178 | -0.0263 | -1.0627 | 0.9200 | -0.5915 | -0.1875 |
| price_action_h2l2 | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| range_breakout_nr4_nr7 | USATECHIDXUSD | 360 | 163 | 0.0210 | 0.1826 | 1.0325 | 0.2281 | -0.0749 |
| range_breakout_nr4_nr7 | USA500IDXUSD | 308 | 154 | 0.0543 | 0.4713 | 1.0882 | 0.2718 | -0.0446 |
| range_breakout_nr4_nr7 | XAUUSD | 1,103 | 536 | 0.0192 | 0.3467 | 1.0341 | 0.1000 | -0.1559 |
| range_breakout_nr4_nr7 | BTCUSDT | 464 | 257 | -0.0393 | -0.5980 | 0.9157 | -0.3459 | -0.1314 |
| range_breakout_nr4_nr7 | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| candlestick_at_level | USATECHIDXUSD | 780 | 309 | 0.0166 | 0.1661 | 1.0222 | 0.0737 | -0.1214 |
| candlestick_at_level | USA500IDXUSD | 507 | 242 | 0.0513 | 0.4507 | 1.0697 | 0.2557 | -0.1263 |
| candlestick_at_level | XAUUSD | 1,876 | 883 | 0.0153 | 0.2960 | 1.0245 | 0.0555 | -0.2990 |
| candlestick_at_level | BTCUSDT | 738 | 525 | -0.0215 | -0.4826 | 0.9489 | -0.2792 | -0.1242 |
| candlestick_at_level | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| ma_cross | USATECHIDXUSD | 494 | 257 | -0.0718 | -0.6786 | 0.9072 | -0.2862 | -0.2052 |
| ma_cross | USA500IDXUSD | 479 | 225 | 0.2583 | 2.0581 | 1.3714 | 1.0714 | -0.0559 |
| ma_cross | XAUUSD | 1,962 | 973 | -0.0390 | -0.8084 | 0.9400 | -0.1949 | -0.2760 |
| ma_cross | BTCUSDT | 578 | 457 | -0.0237 | -0.4408 | 0.9493 | -0.2534 | -0.1195 |
| ma_cross | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| trendline_channel | USATECHIDXUSD | 2,906 | 213 | 0.0291 | 0.2509 | 1.0407 | 0.0265 | -0.1004 |
| trendline_channel | USA500IDXUSD | 2,690 | 188 | 0.0789 | 0.6331 | 1.1133 | 0.1440 | -0.0793 |
| trendline_channel | XAUUSD | 11,542 | 1,318 | -0.0226 | -0.6478 | 0.9557 | -0.1898 | -0.3340 |
| trendline_channel | BTCUSDT | 3,606 | 1,010 | -0.0215 | -0.8071 | 0.9348 | -0.4598 | -0.1621 |
| trendline_channel | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| fvg_retrace | USATECHIDXUSD | 4,360 | 226 | 0.0729 | 0.6491 | 1.1059 | 0.0792 | -0.0815 |
| fvg_retrace | USA500IDXUSD | 4,592 | 211 | 0.0366 | 0.3201 | 1.0524 | 0.0118 | -0.1432 |
| fvg_retrace | XAUUSD | 17,085 | 1,369 | -0.0119 | -0.3464 | 0.9766 | -0.0933 | -0.2517 |
| fvg_retrace | BTCUSDT | 2,833 | 956 | -0.0490 | -1.8716 | 0.8538 | -1.0580 | -0.2782 |
| fvg_retrace | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| macd_signal | USATECHIDXUSD | 1,463 | 350 | -0.0384 | -0.4253 | 0.9490 | -0.2242 | -0.1728 |
| macd_signal | USA500IDXUSD | 1,393 | 289 | 0.0778 | 0.7521 | 1.1074 | 0.3832 | -0.0904 |
| macd_signal | XAUUSD | 5,627 | 1,385 | -0.0343 | -0.9247 | 0.9414 | -0.1690 | -0.2710 |
| macd_signal | BTCUSDT | 1,656 | 868 | -0.0040 | -0.1175 | 0.9897 | -0.0681 | -0.1394 |
| macd_signal | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| ichimoku_cloud | USATECHIDXUSD | 5,644 | 244 | 0.0026 | 0.0239 | 1.0035 | -0.1729 | -0.1610 |
| ichimoku_cloud | USA500IDXUSD | 5,596 | 221 | -0.0329 | -0.2981 | 0.9545 | -0.2800 | -0.1347 |
| ichimoku_cloud | XAUUSD | 21,678 | 1,407 | -0.0102 | -0.3166 | 0.9788 | -0.0986 | -0.3205 |
| ichimoku_cloud | BTCUSDT | 6,122 | 1,151 | -0.0286 | -1.1593 | 0.9144 | -0.6658 | -0.2167 |
| ichimoku_cloud | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| liquidity_sweep | USATECHIDXUSD | 13,356 | 340 | -0.0886 | -0.9910 | 0.8836 | -0.4020 | -0.1770 |
| liquidity_sweep | USA500IDXUSD | 11,449 | 273 | 0.0781 | 0.7307 | 1.1084 | 0.3572 | -0.1155 |
| liquidity_sweep | XAUUSD | 51,640 | 1,647 | -0.0161 | -0.4975 | 0.9698 | -0.1595 | -0.2955 |
| liquidity_sweep | BTCUSDT | 14,422 | 1,206 | -0.0231 | -0.8869 | 0.9357 | -0.5089 | -0.2383 |
| liquidity_sweep | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| wyckoff_spring_upthrust | USATECHIDXUSD | 1,523 | 364 | -0.0844 | -1.1203 | 0.8786 | -0.5938 | -0.2278 |
| wyckoff_spring_upthrust | USA500IDXUSD | 1,451 | 316 | -0.0184 | -0.2172 | 0.9731 | -0.0983 | -0.1341 |
| wyckoff_spring_upthrust | XAUUSD | 5,832 | 1,375 | -0.0027 | -0.0770 | 0.9951 | -0.0122 | -0.2817 |
| wyckoff_spring_upthrust | BTCUSDT | 1,786 | 817 | -0.0230 | -0.7769 | 0.9333 | -0.4405 | -0.1859 |
| wyckoff_spring_upthrust | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| intraday_momentum | USATECHIDXUSD | 5,636 | 214 | -0.0272 | -0.2361 | 0.9632 | -0.3984 | -0.1454 |
| intraday_momentum | USA500IDXUSD | 5,639 | 228 | -0.0167 | -0.1516 | 0.9772 | -0.1427 | -0.1559 |
| btc_order_flow | BTCUSDT | 5,859 | 1,146 | -0.0224 | -0.8391 | 0.9366 | -0.4941 | -0.1715 |
| btc_order_flow | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| vwap_reclaim_reject | USATECHIDXUSD | 3,565 | 291 | -0.0267 | -0.2692 | 0.9642 | -0.0966 | -0.2088 |
| vwap_reclaim_reject | USA500IDXUSD | 3,581 | 262 | -0.0033 | -0.0313 | 0.9956 | -0.0229 | -0.1752 |
| vwap_reclaim_reject | XAUUSD | 12,975 | 1,474 | -0.0635 | -1.8503 | 0.8895 | -0.4722 | -0.4197 |
| vwap_reclaim_reject | BTCUSDT | 3,701 | 1,050 | 0.0001 | 0.0022 | 1.0002 | 0.0013 | -0.1211 |
| vwap_reclaim_reject | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| order_block_retest | USATECHIDXUSD | 1,473 | 261 | 0.0047 | 0.0452 | 1.0065 | -0.0739 | -0.1300 |
| order_block_retest | USA500IDXUSD | 1,428 | 228 | -0.0151 | -0.1353 | 0.9794 | -0.0057 | -0.1152 |
| order_block_retest | XAUUSD | 5,365 | 1,108 | -0.0400 | -0.9643 | 0.9310 | -0.3217 | -0.3441 |
| order_block_retest | BTCUSDT | 934 | 561 | -0.0599 | -1.6726 | 0.8280 | -0.9533 | -0.1887 |
| order_block_retest | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| supply_demand_zone_retest | USATECHIDXUSD | 198 | 82 | 0.1599 | 0.8128 | 1.2306 | 0.3708 | -0.0773 |
| supply_demand_zone_retest | USA500IDXUSD | 413 | 119 | 0.1430 | 0.8778 | 1.2045 | 0.2543 | -0.0584 |
| supply_demand_zone_retest | XAUUSD | 2,940 | 942 | -0.0785 | -2.1425 | 0.8448 | -0.4575 | -0.3664 |
| supply_demand_zone_retest | BTCUSDT | 305 | 216 | -0.1029 | -1.9694 | 0.6975 | -1.1176 | -0.1308 |
| supply_demand_zone_retest | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| round_number_reaction | USATECHIDXUSD | 3,773 | 253 | -0.1364 | -1.3642 | 0.8205 | -0.7560 | -0.2242 |
| round_number_reaction | USA500IDXUSD | 3,858 | 230 | -0.0647 | -0.5920 | 0.9137 | -0.4774 | -0.2075 |
| round_number_reaction | XAUUSD | 3,024 | 696 | -0.0384 | -0.7120 | 0.9360 | -0.1404 | -0.2281 |
| round_number_reaction | BTCUSDT | 3,107 | 794 | -0.0298 | -0.9398 | 0.9162 | -0.5338 | -0.1818 |
| round_number_reaction | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| bollinger:band_reversion | USATECHIDXUSD | 1,224 | 403 | -0.0137 | -0.1740 | 0.9808 | -0.0356 | -0.1745 |
| bollinger:band_reversion | USA500IDXUSD | 1,167 | 359 | 0.0673 | 0.7924 | 1.0977 | 0.2699 | -0.1028 |
| bollinger:band_reversion | XAUUSD | 4,584 | 1,673 | -0.1048 | -2.9687 | 0.8426 | -0.6707 | -0.5893 |
| bollinger:band_reversion | BTCUSDT | 1,371 | 895 | -0.0637 | -1.8384 | 0.8595 | -1.0404 | -0.2794 |
| bollinger:band_reversion | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| stochastic | USATECHIDXUSD | 2,064 | 490 | -0.0306 | -0.6028 | 0.9358 | -0.3914 | -0.1623 |
| stochastic | USA500IDXUSD | 1,960 | 489 | -0.0692 | -1.4142 | 0.8574 | -0.7623 | -0.2036 |
| stochastic | XAUUSD | 6,777 | 1,426 | -0.0990 | -3.2533 | 0.8061 | -0.7603 | -0.5157 |
| stochastic | BTCUSDT | 1,732 | 931 | -0.0300 | -1.2188 | 0.9068 | -0.6865 | -0.1824 |
| stochastic | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| session_level_reaction | USATECHIDXUSD | 1,889 | 359 | 0.0115 | 0.1240 | 1.0154 | 0.1016 | -0.2484 |
| session_level_reaction | USA500IDXUSD | 1,897 | 308 | -0.0061 | -0.0624 | 0.9918 | -0.1126 | -0.1116 |
| session_level_reaction | XAUUSD | 3,779 | 1,164 | -0.1331 | -3.3234 | 0.7914 | -0.7879 | -0.5523 |
| session_level_reaction | BTCUSDT | 1,215 | 727 | -0.0338 | -0.9081 | 0.9187 | -0.5080 | -0.1885 |
| session_level_reaction | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| sr_touch | USATECHIDXUSD | 21,180 | 336 | -0.0972 | -1.0437 | 0.8746 | -0.5345 | -0.2754 |
| sr_touch | USA500IDXUSD | 18,688 | 320 | -0.1636 | -1.8110 | 0.7910 | -0.9053 | -0.3031 |
| sr_touch | XAUUSD | 45,136 | 1,389 | -0.0634 | -1.6716 | 0.8969 | -0.3617 | -0.3821 |
| sr_touch | BTCUSDT | 17,116 | 1,028 | -0.0450 | -1.5450 | 0.8832 | -0.8503 | -0.3005 |
| sr_touch | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| vix_spike_dip_buy | USATECHIDXUSD | 62 | 61 | -0.1041 | -0.9129 | 0.7512 | -0.4531 | -0.0501 |
| vix_spike_dip_buy | USA500IDXUSD | 62 | 60 | -0.0588 | -0.5921 | 0.8271 | -0.3251 | -0.0354 |
| bollinger:squeeze_breakout | USATECHIDXUSD | 198 | 168 | -0.0452 | -0.4387 | 0.9210 | -0.3022 | -0.0896 |
| bollinger:squeeze_breakout | USA500IDXUSD | 180 | 139 | -0.2210 | -2.1934 | 0.6426 | -1.0521 | -0.1545 |
| bollinger:squeeze_breakout | XAUUSD | 622 | 538 | -0.0885 | -1.7458 | 0.8419 | -0.4044 | -0.2251 |
| bollinger:squeeze_breakout | BTCUSDT | 144 | 131 | -0.1597 | -2.2424 | 0.6221 | -1.2887 | -0.1171 |
| bollinger:squeeze_breakout | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| dow_trend_confirmation | USATECHIDXUSD | 29 | 29 | 0.2701 | 1.0925 | 1.5503 | 0.4603 | -0.0215 |
| dow_trend_confirmation | USA500IDXUSD | 25 | 25 | -0.2794 | -1.1014 | 0.6212 | -0.6814 | -0.0468 |
| dow_trend_confirmation | XAUUSD | 115 | 115 | -0.0404 | -0.3279 | 0.9378 | -0.0973 | -0.0734 |
| dow_trend_confirmation | BTCUSDT | 34 | 34 | -0.6344 | -4.1259 | 0.2578 | -2.0474 | -0.1067 |
| dow_trend_confirmation | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| rsi2_mean_reversion | USATECHIDXUSD | 58 | 41 | -0.3249 | -1.5378 | 0.5923 | -0.8331 | -0.0666 |
| rsi2_mean_reversion | USA500IDXUSD | 34 | 34 | -0.1987 | -0.7999 | 0.7378 | -0.3778 | -0.0495 |
| post_macro_event_reaction:follow | USATECHIDXUSD | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:follow | USA500IDXUSD | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:follow | XAUUSD | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:follow | BTCUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:follow | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:fade | USATECHIDXUSD | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:fade | USA500IDXUSD | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:fade | XAUUSD | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:fade | BTCUSDT | 0 | 0 | NA | NA | NA | NA | NA |
| post_macro_event_reaction:fade | ETHUSDT | 0 | 0 | NA | NA | NA | NA | NA |
