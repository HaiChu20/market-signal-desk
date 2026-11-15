# D USATECHIDXUSD dev

| Scope | Trades | Win rate | Avg win R | Avg loss R | Net avg R | 1.5x-cost R | PF | t | Max DD R | Longest loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| default | 20073 | 0.3403576944153838 | 1.6651319271926464 | -1.037257011292933 | -0.11747814277634472 | -0.16303890485773478 | 0.8283032035737706 | -12.490443668219141 | 2379.3766482875985 | 22 |
| chosen | 7269 | 0.35231806300729124 | 1.6079986855750157 | -1.0073440474356548 | -0.08591156164114032 | -0.12056954659885134 | 0.8683223692875248 | -5.573388848868385 | 658.3319786499119 | 23 |

Full parameter grid is in the paired CSV. Equity is cumulative net R; period labels separate dev and holdout.

## Diagnostics

Configurations tried in local dev grids: 147.
DSR: 5.551115123125783e-17 (trials=147).

### default

- 2019: 3598 trades, net avg -0.1828091480103597R
- 2020: 5461 trades, net avg -0.1163531567570246R
- 2021: 5247 trades, net avg -0.09620704153991114R
- 2022: 5767 trades, net avg -0.09713690123084243R
- long: 10528 trades, net avg -0.11388791854775196R
- short: 9545 trades, net avg -0.12143810932203614R
- Entry hour 0: 606 trades, net avg -0.10310392783312582R
- Entry hour 1: 861 trades, net avg -0.24872760741864403R
- Entry hour 10: 1063 trades, net avg -0.06459857829236117R
- Entry hour 11: 929 trades, net avg -0.10623603570556456R
- Entry hour 12: 939 trades, net avg -0.09899665666146164R
- Entry hour 13: 927 trades, net avg -0.04668565031408039R
- Entry hour 14: 1098 trades, net avg -0.13285372403846743R
- Entry hour 15: 1205 trades, net avg -0.07916884335870857R
- Entry hour 18: 618 trades, net avg -0.08526015559271817R
- Entry hour 19: 503 trades, net avg -0.1990929776308501R
- Entry hour 2: 981 trades, net avg -0.12066137253526436R
- Entry hour 20: 875 trades, net avg -0.09078557937617587R
- Entry hour 21: 775 trades, net avg -0.08802651234237R
- Entry hour 22: 615 trades, net avg -0.1373933194748778R
- Entry hour 23: 529 trades, net avg -0.07821779078702905R
- Entry hour 3: 1158 trades, net avg -0.135442884479789R
- Entry hour 4: 883 trades, net avg -0.15277992787190783R
- Entry hour 5: 825 trades, net avg -0.18377192712060805R
- Entry hour 6: 956 trades, net avg -0.1760460339609896R
- Entry hour 7: 936 trades, net avg -0.15942336325878162R
- Entry hour 8: 1145 trades, net avg -0.06306188538777673R
- Entry hour 9: 1646 trades, net avg -0.09648453600773549R

### chosen

- 2019: 1529 trades, net avg -0.17614690861021062R
- 2020: 1946 trades, net avg -0.07117531198922881R
- 2021: 1801 trades, net avg -0.08383762915858911R
- 2022: 1993 trades, net avg -0.0329472107670741R
- long: 3841 trades, net avg -0.07195973523070559R
- short: 3428 trades, net avg -0.10154428195691621R
- Entry hour 10: 1054 trades, net avg -0.06682625664763449R
- Entry hour 11: 920 trades, net avg -0.10865224593108662R
- Entry hour 12: 943 trades, net avg -0.09609875211221532R
- Entry hour 13: 924 trades, net avg -0.05098420168725929R
- Entry hour 14: 1098 trades, net avg -0.13285372403846743R
- Entry hour 15: 1206 trades, net avg -0.079977596910687R
- Entry hour 18: 3 trades, net avg 1.2725364856330517R
- Entry hour 9: 1121 trades, net avg -0.0694530899141563R

## Random-direction benchmark

- default: 0.0 percentile; mean=-0.07474549057974214R; 5–95%=-0.08899261885426532–-0.06093350958225972R
- chosen: 4.6 percentile; mean=-0.06252017251928386R; 5–95%=-0.08551188693113512–-0.03905815816262494R

## Cost and fill sensitivity

```json
{
  "cost_multipliers": {
    "chosen": {
      "1.0": {
        "summary": {
          "trades": 7269,
          "win_rate": 0.35231806300729124,
          "avg_win_R": 1.6079986855750157,
          "avg_loss_R": -1.0073440474356548,
          "net_avg_R": -0.08591156164114032,
          "net_avg_R_cost15": -0.11034508074822803,
          "profit_factor": 0.8683223692875248,
          "t": -5.573388848868385,
          "max_drawdown_R": 658.3319786499119,
          "longest_losing_streak": 23,
          "exit_reason_counts": {
            "stop": 4375,
            "target": 1855,
            "time": 1039
          },
          "trades_per_year": 1817.25,
          "total_R": -624.4911415694489,
          "longest_losing_streak_days": 10,
          "winning_days": 0.43172690763052207,
          "winning_weeks": 0.36363636363636365,
          "winning_months": 0.2708333333333333
        }
      },
      "1.5": {
        "summary": {
          "trades": 7267,
          "win_rate": 0.34691069217008397,
          "avg_win_R": 1.5959737470216897,
          "avg_loss_R": -1.032370145675418,
          "net_avg_R": -0.12056954659885134,
          "net_avg_R_cost15": -0.15725736141867705,
          "profit_factor": 0.8211744304013042,
          "t": -7.814991591346755,
          "max_drawdown_R": 905.7849910018688,
          "longest_losing_streak": 23,
          "exit_reason_counts": {
            "stop": 4401,
            "target": 1830,
            "time": 1036
          },
          "trades_per_year": 1816.75,
          "total_R": -876.1788951338527,
          "longest_losing_streak_days": 10,
          "winning_days": 0.4046184738955823,
          "winning_weeks": 0.31100478468899523,
          "winning_months": 0.1875
        }
      },
      "2.0": {
        "summary": {
          "trades": 7263,
          "win_rate": 0.3413190141814677,
          "avg_win_R": 1.5843044133236817,
          "avg_loss_R": -1.0578418341855462,
          "net_avg_R": -0.15602708166243243,
          "net_avg_R_cost15": -0.20508182660436464,
          "profit_factor": 0.7760742070722203,
          "t": -10.099507443053257,
          "max_drawdown_R": 1155.2291085962163,
          "longest_losing_streak": 24,
          "exit_reason_counts": {
            "stop": 4428,
            "target": 1806,
            "time": 1029
          },
          "trades_per_year": 1815.75,
          "total_R": -1133.2246941142466,
          "longest_losing_streak_days": 11,
          "winning_days": 0.38052208835341367,
          "winning_weeks": 0.27751196172248804,
          "winning_months": 0.125
        }
      }
    },
    "default": {
      "1.0": {
        "summary": {
          "trades": 20073,
          "win_rate": 0.3403576944153838,
          "avg_win_R": 1.6651319271926464,
          "avg_loss_R": -1.037257011292933,
          "net_avg_R": -0.11747814277634472,
          "net_avg_R_cost15": -0.15099878619315482,
          "profit_factor": 0.8283032035737706,
          "t": -12.490443668219141,
          "max_drawdown_R": 2379.3766482875985,
          "longest_losing_streak": 22,
          "exit_reason_counts": {
            "stop": 12517,
            "target": 5329,
            "time": 2227
          },
          "trades_per_year": 5018.25,
          "total_R": -2358.1387599495674,
          "longest_losing_streak_days": 14,
          "winning_days": 0.3473895582329317,
          "winning_weeks": 0.21052631578947367,
          "winning_months": 0.020833333333333332
        }
      },
      "1.5": {
        "summary": {
          "trades": 20028,
          "win_rate": 0.33458158577990815,
          "avg_win_R": 1.6459488989360833,
          "avg_loss_R": -1.0726230027959336,
          "net_avg_R": -0.16303890485773478,
          "net_avg_R_cost15": -0.21335041360849835,
          "profit_factor": 0.7715720048133027,
          "t": -17.29071931615676,
          "max_drawdown_R": 3282.2794874141177,
          "longest_losing_streak": 22,
          "exit_reason_counts": {
            "stop": 12575,
            "target": 5235,
            "time": 2218
          },
          "trades_per_year": 5007.0,
          "total_R": -3265.3431864907125,
          "longest_losing_streak_days": 15,
          "winning_days": 0.2971887550200803,
          "winning_weeks": 0.11961722488038277,
          "winning_months": 0.020833333333333332
        }
      },
      "2.0": {
        "summary": {
          "trades": 19997,
          "win_rate": 0.32909936490473574,
          "avg_win_R": 1.626251435733116,
          "avg_loss_R": -1.108582614064365,
          "net_avg_R": -0.20855046515616774,
          "net_avg_R_cost15": -0.2756555792178407,
          "profit_factor": 0.7195955532142752,
          "t": -22.057602462386626,
          "max_drawdown_R": 4185.2074978869,
          "longest_losing_streak": 22,
          "exit_reason_counts": {
            "stop": 12647,
            "target": 5152,
            "time": 2198
          },
          "trades_per_year": 4999.25,
          "total_R": -4170.383651727886,
          "longest_losing_streak_days": 18,
          "winning_days": 0.24799196787148595,
          "winning_weeks": 0.0861244019138756,
          "winning_months": 0.020833333333333332
        }
      }
    }
  },
  "cost_models": {
    "chosen": {
      "futures": {
        "summary": {
          "trades": 7269,
          "win_rate": 0.35231806300729124,
          "avg_win_R": 1.6079986855750157,
          "avg_loss_R": -1.0073440474356548,
          "net_avg_R": -0.08591156164114032,
          "net_avg_R_cost15": -0.11034508074822803,
          "profit_factor": 0.8683223692875248,
          "t": -5.573388848868385,
          "max_drawdown_R": 658.3319786499119,
          "longest_losing_streak": 23,
          "exit_reason_counts": {
            "stop": 4375,
            "target": 1855,
            "time": 1039
          },
          "trades_per_year": 1817.25,
          "total_R": -624.4911415694489,
          "longest_losing_streak_days": 10,
          "winning_days": 0.43172690763052207,
          "winning_weeks": 0.36363636363636365,
          "winning_months": 0.2708333333333333
        }
      },
      "dukascopy": {
        "summary": {
          "trades": 7210,
          "win_rate": 0.32968099861303746,
          "avg_win_R": 1.5949171678690115,
          "avg_loss_R": -1.0098026309631905,
          "net_avg_R": -0.15107600657704018,
          "net_avg_R_cost15": -0.17714980759226112,
          "profit_factor": 0.7768085939169226,
          "t": -9.956921267966289,
          "max_drawdown_R": 1112.653829696571,
          "longest_losing_streak": 24,
          "exit_reason_counts": {
            "stop": 4504,
            "target": 1695,
            "time": 1011
          },
          "trades_per_year": 1802.5,
          "total_R": -1089.2580074204598,
          "longest_losing_streak_days": 10,
          "winning_days": 0.3845381526104418,
          "winning_weeks": 0.2727272727272727,
          "winning_months": 0.08333333333333333
        }
      },
      "capital": {
        "summary": {
          "trades": 7157,
          "win_rate": 0.3161939360067067,
          "avg_win_R": 1.5961292079028122,
          "avg_loss_R": -1.0097068976106391,
          "net_avg_R": -0.18575732281995297,
          "net_avg_R_cost15": -0.21266808693126843,
          "profit_factor": 0.7309594931924575,
          "t": -12.330416638698088,
          "max_drawdown_R": 1345.5405300482591,
          "longest_losing_streak": 24,
          "exit_reason_counts": {
            "stop": 4563,
            "target": 1610,
            "time": 984
          },
          "trades_per_year": 1789.25,
          "total_R": -1329.4651594224033,
          "longest_losing_streak_days": 17,
          "winning_days": 0.3453815261044177,
          "winning_weeks": 0.215311004784689,
          "winning_months": 0.0625
        }
      }
    },
    "default": {
      "futures": {
        "summary": {
          "trades": 20073,
          "win_rate": 0.3403576944153838,
          "avg_win_R": 1.6651319271926464,
          "avg_loss_R": -1.037257011292933,
          "net_avg_R": -0.11747814277634472,
          "net_avg_R_cost15": -0.15099878619315482,
          "profit_factor": 0.8283032035737706,
          "t": -12.490443668219141,
          "max_drawdown_R": 2379.3766482875985,
          "longest_losing_streak": 22,
          "exit_reason_counts": {
            "stop": 12517,
            "target": 5329,
            "time": 2227
          },
          "trades_per_year": 5018.25,
          "total_R": -2358.1387599495674,
          "longest_losing_streak_days": 14,
          "winning_days": 0.3473895582329317,
          "winning_weeks": 0.21052631578947367,
          "winning_months": 0.020833333333333332
        }
      },
      "dukascopy": {
        "summary": {
          "trades": 18496,
          "win_rate": 0.26584126297577854,
          "avg_win_R": 1.6403979145185963,
          "avg_loss_R": -1.042910178138428,
          "net_avg_R": -0.3295761658333574,
          "net_avg_R_cost15": -0.36479498113398523,
          "profit_factor": 0.5695537590448521,
          "t": -36.32095331406224,
          "max_drawdown_R": 6101.11672392919,
          "longest_losing_streak": 30,
          "exit_reason_counts": {
            "stop": 12967,
            "target": 3712,
            "time": 1817
          },
          "trades_per_year": 4624.0,
          "total_R": -6095.840763253778,
          "longest_losing_streak_days": 31,
          "winning_days": 0.1395582329317269,
          "winning_weeks": 0.004784688995215311,
          "winning_months": 0.0
        }
      },
      "capital": {
        "summary": {
          "trades": 19426,
          "win_rate": 0.2901266344074951,
          "avg_win_R": 1.653939398788524,
          "avg_loss_R": -1.0416181073009514,
          "net_avg_R": -0.2595650802073508,
          "net_avg_R_cost15": -0.2952207901879746,
          "profit_factor": 0.6489597923287239,
          "t": -28.428921589148146,
          "max_drawdown_R": 5047.145025512894,
          "longest_losing_streak": 35,
          "exit_reason_counts": {
            "stop": 13121,
            "target": 4322,
            "time": 1983
          },
          "trades_per_year": 4856.5,
          "total_R": -5042.311248107997,
          "longest_losing_streak_days": 28,
          "winning_days": 0.18473895582329317,
          "winning_weeks": 0.03349282296650718,
          "winning_months": 0.020833333333333332
        }
      }
    }
  },
  "fill_variants": {
    "chosen": {
      "trade_through": {
        "summary": {
          "trades": 7269,
          "win_rate": 0.35231806300729124,
          "avg_win_R": 1.6079986855750157,
          "avg_loss_R": -1.0073440474356548,
          "net_avg_R": -0.08591156164114032,
          "net_avg_R_cost15": -0.11034508074822803,
          "profit_factor": 0.8683223692875248,
          "t": -5.573388848868385,
          "max_drawdown_R": 658.3319786499119,
          "longest_losing_streak": 23,
          "exit_reason_counts": {
            "stop": 4375,
            "target": 1855,
            "time": 1039
          },
          "trades_per_year": 1817.25,
          "total_R": -624.4911415694489,
          "longest_losing_streak_days": 10,
          "winning_days": 0.43172690763052207,
          "winning_weeks": 0.36363636363636365,
          "winning_months": 0.2708333333333333
        }
      },
      "touch": {
        "summary": {
          "trades": 7339,
          "win_rate": 0.3616296498160512,
          "avg_win_R": 1.6166162878694499,
          "avg_loss_R": -1.0076191342262801,
          "net_avg_R": -0.05861779749892383,
          "net_avg_R_cost15": -0.08304531636999425,
          "profit_factor": 0.9088702072108718,
          "t": -3.78821921273155,
          "max_drawdown_R": 469.9014339136546,
          "longest_losing_streak": 23,
          "exit_reason_counts": {
            "stop": 4357,
            "target": 1946,
            "time": 1036
          },
          "trades_per_year": 1834.75,
          "total_R": -430.196015844602,
          "longest_losing_streak_days": 10,
          "winning_days": 0.4578313253012048,
          "winning_weeks": 0.3875598086124402,
          "winning_months": 0.2916666666666667
        }
      }
    },
    "default": {
      "trade_through": {
        "summary": {
          "trades": 20073,
          "win_rate": 0.3403576944153838,
          "avg_win_R": 1.6651319271926464,
          "avg_loss_R": -1.037257011292933,
          "net_avg_R": -0.11747814277634472,
          "net_avg_R_cost15": -0.15099878619315482,
          "profit_factor": 0.8283032035737706,
          "t": -12.490443668219141,
          "max_drawdown_R": 2379.3766482875985,
          "longest_losing_streak": 22,
          "exit_reason_counts": {
            "stop": 12517,
            "target": 5329,
            "time": 2227
          },
          "trades_per_year": 5018.25,
          "total_R": -2358.1387599495674,
          "longest_losing_streak_days": 14,
          "winning_days": 0.3473895582329317,
          "winning_weeks": 0.21052631578947367,
          "winning_months": 0.020833333333333332
        }
      },
      "touch": {
        "summary": {
          "trades": 20320,
          "win_rate": 0.3498031496062992,
          "avg_win_R": 1.6723723138274114,
          "avg_loss_R": -1.0379018578202157,
          "net_avg_R": -0.08983941628127214,
          "net_avg_R_cost15": -0.12342864993335129,
          "profit_factor": 0.8668731148241315,
          "t": -9.526844670723875,
          "max_drawdown_R": 1855.2759665337383,
          "longest_losing_streak": 18,
          "exit_reason_counts": {
            "stop": 12500,
            "target": 5595,
            "time": 2225
          },
          "trades_per_year": 5080.0,
          "total_R": -1825.5369388354497,
          "longest_losing_streak_days": 14,
          "winning_days": 0.3815261044176707,
          "winning_weeks": 0.24880382775119617,
          "winning_months": 0.0625
        }
      }
    }
  }
}
```

## ES frozen-cell cross-check

```json
{
  "chosen": {
    "overall": {
      "trades": 7003,
      "win_rate": 0.30901042410395546,
      "avg_win_R": 1.5798983961610733,
      "avg_loss_R": -1.088745413660402,
      "net_avg_R": -0.26410665820507256,
      "net_avg_R_cost15": -0.3220109863280854,
      "profit_factor": 0.6489398648244631,
      "t": -17.062497119797044,
      "max_drawdown_R": 1852.0595714577353,
      "longest_losing_streak": 22,
      "exit_reason_counts": {
        "stop": 4518,
        "target": 1547,
        "time": 938
      },
      "trades_per_year": 1750.75,
      "total_R": -1849.538927410123,
      "longest_losing_streak_days": 17,
      "winning_days": 0.32595573440643866,
      "winning_weeks": 0.1339712918660287,
      "winning_months": 0.0
    },
    "by_year": {
      "2019": {
        "trades": 1476,
        "win_rate": 0.29471544715447157,
        "avg_win_R": 1.460254335880021,
        "avg_loss_R": -1.1490890843349346,
        "net_avg_R": -0.3800752714667059,
        "net_avg_R_cost15": -0.46902917041117553,
        "profit_factor": 0.5310230010290545,
        "t": -11.583004377100032,
        "max_drawdown_R": 562.606302833956,
        "longest_losing_streak": 22,
        "exit_reason_counts": {
          "stop": 963,
          "target": 279,
          "time": 234
        }
      },
      "2020": {
        "trades": 1874,
        "win_rate": 0.31323372465314836,
        "avg_win_R": 1.5709588457637667,
        "avg_loss_R": -1.0851792872635067,
        "net_avg_R": -0.2531872466621143,
        "net_avg_R_cost15": -0.3056170822924968,
        "profit_factor": 0.6602719785726036,
        "t": -8.478307786057556,
        "max_drawdown_R": 480.935620730529,
        "longest_losing_streak": 16,
        "exit_reason_counts": {
          "stop": 1218,
          "target": 411,
          "time": 245
        }
      },
      "2021": {
        "trades": 1764,
        "win_rate": 0.29365079365079366,
        "avg_win_R": 1.5885058391071047,
        "avg_loss_R": -1.099655898923993,
        "net_avg_R": -0.31027507108946445,
        "net_avg_R_cost15": -0.3740868266039417,
        "profit_factor": 0.6005424684117923,
        "t": -10.132122167086768,
        "max_drawdown_R": 552.4548581082161,
        "longest_losing_streak": 15,
        "exit_reason_counts": {
          "stop": 1158,
          "target": 381,
          "time": 225
        }
      },
      "2022": {
        "trades": 1889,
        "win_rate": 0.33033350979354154,
        "avg_win_R": 1.6645683109999072,
        "avg_loss_R": -1.0319686380573834,
        "net_avg_R": -0.14121212338732012,
        "net_avg_R_cost15": -0.17476988215097639,
        "profit_factor": 0.7956630452327742,
        "t": -4.638502317898036,
        "max_drawdown_R": 272.3698186750883,
        "longest_losing_streak": 18,
        "exit_reason_counts": {
          "stop": 1179,
          "target": 476,
          "time": 234
        }
      }
    },
    "long_vs_short": {
      "long": {
        "trades": 3801,
        "win_rate": 0.31596948171533806,
        "avg_win_R": 1.5424984115036648,
        "avg_loss_R": -1.092250703810733,
        "net_avg_R": -0.2597503913948972,
        "net_avg_R_cost15": -0.31672922085903377,
        "profit_factor": 0.6523370595274959,
        "t": -12.416670300128306,
        "max_drawdown_R": 991.4500800581219,
        "longest_losing_streak": 18,
        "exit_reason_counts": {
          "stop": 2452,
          "target": 816,
          "time": 533
        }
      },
      "short": {
        "trades": 3202,
        "win_rate": 0.3007495315427858,
        "avg_win_R": 1.6265415753651724,
        "avg_loss_R": -1.0846749561388032,
        "net_avg_R": -0.2692778543779259,
        "net_avg_R_cost15": -0.3282808147315409,
        "profit_factor": 0.644967378480337,
        "t": -11.702055216240762,
        "max_drawdown_R": 863.0585729140719,
        "longest_losing_streak": 21,
        "exit_reason_counts": {
          "stop": 2066,
          "target": 731,
          "time": 405
        }
      }
    },
    "by_entry_hour": {
      "10": {
        "trades": 1031,
        "win_rate": 0.3288069835111542,
        "avg_win_R": 1.6088728101235146,
        "avg_loss_R": -1.0802838991108117,
        "net_avg_R": -0.1960703933586909,
        "net_avg_R_cost15": -0.24843607954239758,
        "profit_factor": 0.7295875470814673,
        "t": -4.753104263084835,
        "max_drawdown_R": 210.4576340502824,
        "longest_losing_streak": 14,
        "exit_reason_counts": {
          "stop": 646,
          "target": 248,
          "time": 137
        }
      },
      "11": {
        "trades": 859,
        "win_rate": 0.309662398137369,
        "avg_win_R": 1.6415974387388854,
        "avg_loss_R": -1.100480549114109,
        "net_avg_R": -0.25136210351585947,
        "net_avg_R_cost15": -0.30945219170635546,
        "profit_factor": 0.6691311349573609,
        "t": -5.586431538776872,
        "max_drawdown_R": 217.44491471604394,
        "longest_losing_streak": 25,
        "exit_reason_counts": {
          "stop": 561,
          "target": 200,
          "time": 98
        }
      },
      "12": {
        "trades": 930,
        "win_rate": 0.2870967741935484,
        "avg_win_R": 1.738967642441228,
        "avg_loss_R": -1.1210426564101363,
        "net_avg_R": -0.29994292544958345,
        "net_avg_R_cost15": -0.3637401637136381,
        "profit_factor": 0.6246936564740597,
        "t": -6.867076120812372,
        "max_drawdown_R": 281.24781423881933,
        "longest_losing_streak": 18,
        "exit_reason_counts": {
          "stop": 638,
          "target": 223,
          "time": 69
        }
      },
      "13": {
        "trades": 893,
        "win_rate": 0.2597984322508399,
        "avg_win_R": 1.7454440936579183,
        "avg_loss_R": -1.143849987343214,
        "net_avg_R": -0.3932159147874886,
        "net_avg_R_cost15": -0.4601406757433146,
        "profit_factor": 0.5355788232092762,
        "t": -9.044030773062445,
        "max_drawdown_R": 352.92848166680034,
        "longest_losing_streak": 15,
        "exit_reason_counts": {
          "stop": 647,
          "target": 197,
          "time": 49
        }
      },
      "14": {
        "trades": 1066,
        "win_rate": 0.30956848030018763,
        "avg_win_R": 1.6939345866542626,
        "avg_loss_R": -1.1278880749449587,
        "net_avg_R": -0.25434072191705714,
        "net_avg_R_cost15": -0.31504443611160454,
        "profit_factor": 0.6733901448172838,
        "t": -6.160213285242886,
        "max_drawdown_R": 275.5672315906115,
        "longest_losing_streak": 18,
        "exit_reason_counts": {
          "stop": 716,
          "target": 267,
          "time": 83
        }
      },
      "15": {
        "trades": 1231,
        "win_rate": 0.3428107229894395,
        "avg_win_R": 1.2520068120155181,
        "avg_loss_R": -1.0123673302142677,
        "net_avg_R": -0.23611559339788302,
        "net_avg_R_cost15": -0.29943233120828244,
        "profit_factor": 0.645108106677858,
        "t": -6.967754175217374,
        "max_drawdown_R": 294.9453082392365,
        "longest_losing_streak": 15,
        "exit_reason_counts": {
          "stop": 664,
          "time": 360,
          "target": 207
        }
      },
      "18": {
        "trades": 3,
        "win_rate": 0.3333333333333333,
        "avg_win_R": 1.9146757679180906,
        "avg_loss_R": -1.242091399226279,
        "net_avg_R": -0.18983567684482247,
        "net_avg_R_cost15": -0.2912526021723371,
        "profit_factor": 0.7707467297136009,
        "t": -0.1801910658790168,
        "max_drawdown_R": 2.484182798452558,
        "longest_losing_streak": 2,
        "exit_reason_counts": {
          "stop": 2,
          "target": 1
        }
      },
      "9": {
        "trades": 990,
        "win_rate": 0.3101010101010101,
        "avg_win_R": 1.5580455168121476,
        "avg_loss_R": -1.0502877510369948,
        "net_avg_R": -0.2414409699969072,
        "net_avg_R_cost15": -0.28140364086895364,
        "profit_factor": 0.6667906667395375,
        "t": -5.987695433070856,
        "max_drawdown_R": 244.58657508721714,
        "longest_losing_streak": 14,
        "exit_reason_counts": {
          "stop": 644,
          "target": 204,
          "time": 142
        }
      }
    },
    "daily": {
      "sharpe_annualized": -7.607582913766374,
      "max_drawdown_R": 1797.446485401724,
      "winning_periods": {
        "day": 0.32595573440643866,
        "week": 0.1339712918660287,
        "month": 0.0
      },
      "winning_days": {
        "wins": 324,
        "days": 994,
        "percent": 32.59557344064387
      }
    },
    "costs": {
      "x1_net_avg_R": -0.26410665820507256,
      "x1_5_net_avg_R": -0.3220109863280854,
      "x2_net_avg_R": -0.37991531445109816,
      "median_stop_points": 4.420500000000175,
      "median_cost_R": 0.08890864636586304
    },
    "diagnostics": {
      "minimum_stop_skips": 678,
      "entry_beyond_stop_skips": 721,
      "entry_beyond_stop": 0,
      "missing_target_skips": 0,
      "signals": 14182,
      "unfilled": 6501,
      "unresolved_at_end": 0
    }
  },
  "default": {
    "overall": {
      "trades": 19184,
      "win_rate": 0.28628023352793996,
      "avg_win_R": 1.6151440792479768,
      "avg_loss_R": -1.1375645425543752,
      "net_avg_R": -0.3495184754704242,
      "net_avg_R_cost15": -0.42512311836468086,
      "profit_factor": 0.5695067305298844,
      "t": -37.31268092850412,
      "max_drawdown_R": 6706.067875323142,
      "longest_losing_streak": 26,
      "exit_reason_counts": {
        "stop": 12961,
        "target": 4135,
        "time": 2088
      },
      "trades_per_year": 4796.0,
      "total_R": -6705.162433424618,
      "longest_losing_streak_days": 40,
      "winning_days": 0.1488933601609658,
      "winning_weeks": 0.03827751196172249,
      "winning_months": 0.0
    },
    "by_year": {
      "2019": {
        "trades": 3506,
        "win_rate": 0.26583000570450654,
        "avg_win_R": 1.474710636515735,
        "avg_loss_R": -1.197679715726955,
        "net_avg_R": -0.4872781731456125,
        "net_avg_R_cost15": -0.5951208214221093,
        "profit_factor": 0.44583431083117203,
        "t": -23.18190778321245,
        "max_drawdown_R": 1708.3972750485095,
        "longest_losing_streak": 22,
        "exit_reason_counts": {
          "stop": 2412,
          "target": 620,
          "time": 474
        }
      },
      "2020": {
        "trades": 5276,
        "win_rate": 0.29681576952236544,
        "avg_win_R": 1.6248432917852802,
        "avg_loss_R": -1.1226905184995146,
        "net_avg_R": -0.3071791563111165,
        "net_avg_R_cost15": -0.37394788964632353,
        "profit_factor": 0.6108988041046025,
        "t": -17.062830332449625,
        "max_drawdown_R": 1622.8414189511207,
        "longest_losing_streak": 26,
        "exit_reason_counts": {
          "stop": 3529,
          "target": 1182,
          "time": 565
        }
      },
      "2021": {
        "trades": 4916,
        "win_rate": 0.2792921074043938,
        "avg_win_R": 1.6059270608664782,
        "avg_loss_R": -1.1560648918371248,
        "net_avg_R": -0.3846623387325588,
        "net_avg_R_cost15": -0.46946255238627355,
        "profit_factor": 0.5383230659402338,
        "t": -20.862575908409724,
        "max_drawdown_R": 1896.4341146604345,
        "longest_losing_streak": 21,
        "exit_reason_counts": {
          "stop": 3348,
          "target": 1038,
          "time": 530
        }
      },
      "2022": {
        "trades": 5486,
        "win_rate": 0.2954794021144732,
        "avg_win_R": 1.694323578341641,
        "avg_loss_R": -1.0948477083987556,
        "net_avg_R": -0.27070504419784736,
        "net_avg_R_cost15": -0.3259645150377686,
        "profit_factor": 0.6490470158095599,
        "t": -15.226152965737587,
        "max_drawdown_R": 1487.9151129993918,
        "longest_losing_streak": 23,
        "exit_reason_counts": {
          "stop": 3672,
          "target": 1295,
          "time": 519
        }
      }
    },
    "long_vs_short": {
      "long": {
        "trades": 10044,
        "win_rate": 0.29589804858622065,
        "avg_win_R": 1.583779814101334,
        "avg_loss_R": -1.1331642233702515,
        "net_avg_R": -0.32922578456444196,
        "net_avg_R_cost15": -0.4026951374586416,
        "profit_factor": 0.5873655923325847,
        "t": -25.446801587975422,
        "max_drawdown_R": 3307.6492220637774,
        "longest_losing_streak": 21,
        "exit_reason_counts": {
          "stop": 6710,
          "target": 2146,
          "time": 1188
        }
      },
      "short": {
        "trades": 9140,
        "win_rate": 0.27571115973741794,
        "avg_win_R": 1.6521339983018744,
        "avg_loss_R": -1.1422653064924602,
        "net_avg_R": -0.3718182333981798,
        "net_avg_R_cost15": -0.44976935908899784,
        "profit_factor": 0.550580509523227,
        "t": -27.385687768934435,
        "max_drawdown_R": 3399.9221565481116,
        "longest_losing_streak": 28,
        "exit_reason_counts": {
          "stop": 6251,
          "target": 1989,
          "time": 900
        }
      }
    },
    "by_entry_hour": {
      "0": {
        "trades": 549,
        "win_rate": 0.2495446265938069,
        "avg_win_R": 1.728321687734859,
        "avg_loss_R": -1.2211604285677824,
        "net_avg_R": -0.4851330152099283,
        "net_avg_R_cost15": -0.587303169116752,
        "profit_factor": 0.47062523259241695,
        "t": -8.708255944690249,
        "max_drawdown_R": 268.3898581299496,
        "longest_losing_streak": 21,
        "exit_reason_counts": {
          "stop": 403,
          "target": 116,
          "time": 30
        }
      },
      "1": {
        "trades": 781,
        "win_rate": 0.24583866837387963,
        "avg_win_R": 1.823501382990954,
        "avg_loss_R": -1.2063886648915072,
        "net_avg_R": -0.46152453020081247,
        "net_avg_R_cost15": -0.5560988001014084,
        "profit_factor": 0.4927252096831299,
        "t": -9.750570504821567,
        "max_drawdown_R": 362.3804210367906,
        "longest_losing_streak": 20,
        "exit_reason_counts": {
          "stop": 579,
          "target": 176,
          "time": 26
        }
      },
      "10": {
        "trades": 1021,
        "win_rate": 0.32027424094025464,
        "avg_win_R": 1.6140726912621692,
        "avg_loss_R": -1.07786334544647,
        "net_avg_R": -0.2157055746298931,
        "net_avg_R_cost15": -0.2685040121367276,
        "profit_factor": 0.7055822852639058,
        "t": -5.234564535546272,
        "max_drawdown_R": 227.4142030455899,
        "longest_losing_streak": 13,
        "exit_reason_counts": {
          "stop": 646,
          "target": 241,
          "time": 134
        }
      },
      "11": {
        "trades": 880,
        "win_rate": 0.31022727272727274,
        "avg_win_R": 1.6311619860648197,
        "avg_loss_R": -1.0996040426455906,
        "net_avg_R": -0.25244594510247476,
        "net_avg_R_cost15": -0.31030377175856555,
        "profit_factor": 0.6671672506392982,
        "t": -5.6943897009586815,
        "max_drawdown_R": 223.67729948609852,
        "longest_losing_streak": 25,
        "exit_reason_counts": {
          "stop": 573,
          "target": 203,
          "time": 104
        }
      },
      "12": {
        "trades": 922,
        "win_rate": 0.2885032537960954,
        "avg_win_R": 1.7385231829792176,
        "avg_loss_R": -1.120344776121942,
        "net_avg_R": -0.2955520677478547,
        "net_avg_R_cost15": -0.3591176582937067,
        "profit_factor": 0.6292258992236441,
        "t": -6.7292550854358115,
        "max_drawdown_R": 275.34843077271285,
        "longest_losing_streak": 18,
        "exit_reason_counts": {
          "stop": 631,
          "target": 222,
          "time": 69
        }
      },
      "13": {
        "trades": 893,
        "win_rate": 0.2597984322508399,
        "avg_win_R": 1.7489474275947785,
        "avg_loss_R": -1.1423043463761533,
        "net_avg_R": -0.3911616682560457,
        "net_avg_R_cost15": -0.45807140226385984,
        "profit_factor": 0.5373799408256474,
        "t": -8.990405959191472,
        "max_drawdown_R": 351.0940395142217,
        "longest_losing_streak": 15,
        "exit_reason_counts": {
          "stop": 646,
          "target": 198,
          "time": 49
        }
      },
      "14": {
        "trades": 1066,
        "win_rate": 0.30956848030018763,
        "avg_win_R": 1.6939345866542626,
        "avg_loss_R": -1.1278880749449587,
        "net_avg_R": -0.25434072191705714,
        "net_avg_R_cost15": -0.31504443611160454,
        "profit_factor": 0.6733901448172838,
        "t": -6.160213285242886,
        "max_drawdown_R": 275.5672315906115,
        "longest_losing_streak": 18,
        "exit_reason_counts": {
          "stop": 716,
          "target": 267,
          "time": 83
        }
      },
      "15": {
        "trades": 1229,
        "win_rate": 0.3433685923515053,
        "avg_win_R": 1.2520068120155181,
        "avg_loss_R": -1.0119837768119266,
        "net_avg_R": -0.23460051522919137,
        "net_avg_R_cost15": -0.2978111674843228,
        "profit_factor": 0.646951996903395,
        "t": -6.915320790204597,
        "max_drawdown_R": 292.61104598311874,
        "longest_losing_streak": 15,
        "exit_reason_counts": {
          "stop": 663,
          "time": 359,
          "target": 207
        }
      },
      "18": {
        "trades": 639,
        "win_rate": 0.323943661971831,
        "avg_win_R": 1.4118082989702947,
        "avg_loss_R": -1.1104510106988112,
        "net_avg_R": -0.29338109348205854,
        "net_avg_R_cost15": -0.3659751073067752,
        "profit_factor": 0.609204251310658,
        "t": -5.86504052522977,
        "max_drawdown_R": 192.35251308329276,
        "longest_losing_streak": 18,
        "exit_reason_counts": {
          "stop": 398,
          "target": 123,
          "time": 118
        }
      },
      "19": {
        "trades": 574,
        "win_rate": 0.2857142857142857,
        "avg_win_R": 1.61463633502203,
        "avg_loss_R": -1.180960193835884,
        "net_avg_R": -0.38221832844790865,
        "net_avg_R_cost15": -0.470830912145781,
        "profit_factor": 0.5468893341027931,
        "t": -6.9827170215367795,
        "max_drawdown_R": 223.0507608206881,
        "longest_losing_streak": 17,
        "exit_reason_counts": {
          "stop": 393,
          "target": 122,
          "time": 59
        }
      },
      "2": {
        "trades": 913,
        "win_rate": 0.2617743702081051,
        "avg_win_R": 1.7346441402141906,
        "avg_loss_R": -1.190100729070805,
        "net_avg_R": -0.4244774828943386,
        "net_avg_R_cost15": -0.5102272064791666,
        "profit_factor": 0.5168501855618631,
        "t": -9.747801531998755,
        "max_drawdown_R": 387.54794188253067,
        "longest_losing_streak": 18,
        "exit_reason_counts": {
          "stop": 665,
          "target": 204,
          "time": 44
        }
      },
      "20": {
        "trades": 853,
        "win_rate": 0.27784290738569756,
        "avg_win_R": 1.5544485259380318,
        "avg_loss_R": -1.1302570523828792,
        "net_avg_R": -0.3843306490275967,
        "net_avg_R_cost15": -0.46890032447174795,
        "profit_factor": 0.5291353222361203,
        "t": -8.837817077589444,
        "max_drawdown_R": 331.5576534655733,
        "longest_losing_streak": 16,
        "exit_reason_counts": {
          "stop": 566,
          "target": 174,
          "time": 113
        }
      },
      "21": {
        "trades": 752,
        "win_rate": 0.2925531914893617,
        "avg_win_R": 1.4747577497671338,
        "avg_loss_R": -1.146069361959936,
        "net_avg_R": -0.3793380260823357,
        "net_avg_R_cost15": -0.47091001945428157,
        "profit_factor": 0.5321337849084132,
        "t": -8.23676517193009,
        "max_drawdown_R": 288.26050656088773,
        "longest_losing_streak": 13,
        "exit_reason_counts": {
          "stop": 486,
          "target": 144,
          "time": 122
        }
      },
      "22": {
        "trades": 609,
        "win_rate": 0.31527093596059114,
        "avg_win_R": 1.4883559532112127,
        "avg_loss_R": -1.142104435364557,
        "net_avg_R": -0.3127967266510138,
        "net_avg_R_cost15": -0.4078996047393778,
        "profit_factor": 0.6000206050032173,
        "t": -5.944819708902627,
        "max_drawdown_R": 190.49320653046743,
        "longest_losing_streak": 12,
        "exit_reason_counts": {
          "stop": 374,
          "target": 128,
          "time": 107
        }
      },
      "23": {
        "trades": 517,
        "win_rate": 0.25918762088974856,
        "avg_win_R": 1.4538929620965848,
        "avg_loss_R": -1.183533838788961,
        "net_avg_R": -0.4999454609965757,
        "net_avg_R_cost15": -0.6022678097217219,
        "profit_factor": 0.42979145741666297,
        "t": -9.317670099195167,
        "max_drawdown_R": 258.47180333522977,
        "longest_losing_streak": 19,
        "exit_reason_counts": {
          "stop": 357,
          "target": 84,
          "time": 76
        }
      },
      "3": {
        "trades": 1148,
        "win_rate": 0.2874564459930314,
        "avg_win_R": 1.571878440634836,
        "avg_loss_R": -1.1263033766594408,
        "net_avg_R": -0.3506936208170092,
        "net_avg_R_cost15": -0.4246851910832004,
        "profit_factor": 0.5630204990900993,
        "t": -9.256703543450428,
        "max_drawdown_R": 404.7952706915759,
        "longest_losing_streak": 23,
        "exit_reason_counts": {
          "stop": 769,
          "target": 240,
          "time": 139
        }
      },
      "4": {
        "trades": 819,
        "win_rate": 0.27106227106227104,
        "avg_win_R": 1.6380375537251866,
        "avg_loss_R": -1.1323891096526824,
        "net_avg_R": -0.3814309664660073,
        "net_avg_R_cost15": -0.4631321851482425,
        "profit_factor": 0.5379065262530152,
        "t": -8.496024187569889,
        "max_drawdown_R": 315.5179571900611,
        "longest_losing_streak": 16,
        "exit_reason_counts": {
          "stop": 555,
          "target": 171,
          "time": 93
        }
      },
      "5": {
        "trades": 823,
        "win_rate": 0.267314702308627,
        "avg_win_R": 1.5948618659612577,
        "avg_loss_R": -1.1608439852961898,
        "net_avg_R": -0.4242032960171638,
        "net_avg_R_cost15": -0.5119210639694216,
        "profit_factor": 0.5012502325619065,
        "t": -9.564471871845264,
        "max_drawdown_R": 349.1193126221254,
        "longest_losing_streak": 12,
        "exit_reason_counts": {
          "stop": 570,
          "target": 166,
          "time": 87
        }
      },
      "6": {
        "trades": 859,
        "win_rate": 0.23632130384167638,
        "avg_win_R": 1.6559887712764847,
        "avg_loss_R": -1.176484670659552,
        "net_avg_R": -0.507110853764307,
        "net_avg_R_cost15": -0.5955053721061395,
        "profit_factor": 0.43557536919093487,
        "t": -11.957577570635932,
        "max_drawdown_R": 435.60822338353955,
        "longest_losing_streak": 19,
        "exit_reason_counts": {
          "stop": 636,
          "target": 161,
          "time": 62
        }
      },
      "7": {
        "trades": 887,
        "win_rate": 0.2705749718151071,
        "avg_win_R": 1.7861296476033226,
        "avg_loss_R": -1.1856674223343342,
        "net_avg_R": -0.3815735138957348,
        "net_avg_R_cost15": -0.4665423705926144,
        "profit_factor": 0.5588008436040861,
        "t": -8.446849586461097,
        "max_drawdown_R": 343.8327244315664,
        "longest_losing_streak": 20,
        "exit_reason_counts": {
          "stop": 634,
          "target": 213,
          "time": 40
        }
      },
      "8": {
        "trades": 1053,
        "win_rate": 0.2792022792022792,
        "avg_win_R": 1.818479737173177,
        "avg_loss_R": -1.1653638386052638,
        "net_avg_R": -0.3322679114648445,
        "net_avg_R_cost15": -0.40638686669027246,
        "profit_factor": 0.6044390063511739,
        "t": -7.929370344084194,
        "max_drawdown_R": 349.8781107724815,
        "longest_losing_streak": 16,
        "exit_reason_counts": {
          "stop": 746,
          "target": 266,
          "time": 41
        }
      },
      "9": {
        "trades": 1397,
        "win_rate": 0.294201861130995,
        "avg_win_R": 1.6473390575439726,
        "avg_loss_R": -1.1026998358725226,
        "net_avg_R": -0.29363327524676774,
        "net_avg_R_cost15": -0.34668810303788095,
        "profit_factor": 0.622716814237305,
        "t": -8.441628878357976,
        "max_drawdown_R": 418.6931435349738,
        "longest_losing_streak": 19,
        "exit_reason_counts": {
          "stop": 955,
          "target": 309,
          "time": 133
        }
      }
    },
    "daily": {
      "sharpe_annualized": -16.249794621688412,
      "max_drawdown_R": 6292.6483734230305,
      "winning_periods": {
        "day": 0.1488933601609658,
        "week": 0.03827751196172249,
        "month": 0.0
      },
      "winning_days": {
        "wins": 148,
        "days": 994,
        "percent": 14.88933601609658
      }
    },
    "costs": {
      "x1_net_avg_R": -0.3495184754704242,
      "x1_5_net_avg_R": -0.42512311836468086,
      "x2_net_avg_R": -0.5007277612589375,
      "median_stop_points": 3.1559999999997217,
      "median_cost_R": 0.12148825604298552
    },
    "diagnostics": {
      "minimum_stop_skips": 3366,
      "entry_beyond_stop_skips": 2139,
      "entry_beyond_stop": 0,
      "missing_target_skips": 0,
      "signals": 47194,
      "unfilled": 24644,
      "unresolved_at_end": 0
    }
  }
}
```

## Grid heat map

| target | time_exit | entry | L | M | N | displacement | session | trades | unresolved_at_end | win_rate | avg_win_R | avg_loss_R | net_avg_R | profit_factor | net_avg_R_cost15 | t | max_drawdown_R | longest_losing_streak | exit_stop | exit_target | exit_time | net_avg_R_x1_5_rerun | net_avg_R_x2_rerun | net_avg_R_touch_fill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2.0 | 120 | proximal | 2 | 3 | 10 | False | all | 21979 | 0 | 0.3387324264070249 | 1.6484866520038524 | -1.03466392678943 | -0.12579382081936819 | 0.8161418974603444 | -0.17038796035545153 | -14.082596926656738 | 2773.2523152033837 | 21 | 13702 | 5717 | 2560 | -0.17038796035545153 | -0.2147851010835401 | -0.1015441939938615 |
| 2.0 | 120 | proximal | 3 | 1 | 10 | False | all | 18240 | 0 | 0.3379385964912281 | 1.6813438343555447 | -1.039834283083939 | -0.12024316927379773 | 0.8253381675372672 | -0.1644941467416284 | -12.152066273047922 | 2207.543278689167 | 22 | 11464 | 4883 | 1893 | -0.1644941467416284 | -0.20842987806712437 | -0.094017857420419 |
| 1.0 | 120 | ce | 3 | 3 | 10 | False | all | 23209 | 0 | 0.47024861045284155 | 0.9279345150757878 | -1.0543485410820197 | -0.12218268839959857 | 0.7812473258614128 | -0.1637125740264202 | -18.62424416643358 | 2849.290509561499 | 13 | 11886 | 10526 | 797 | -0.1637125740264202 | -0.2070348153538001 | -0.08733306703240923 |
| 1.0 | 240 | ce | 3 | 3 | 10 | False | all | 22734 | 0 | 0.47228820269200317 | 0.9381261411085855 | -1.0645964484315338 | -0.11873419612695646 | 0.7886540158573371 | -0.15970430950367462 | -17.79483509785722 | 2712.855709245438 | 13 | 11783 | 10526 | 425 | -0.15970430950367462 | -0.2028450316243938 | -0.08418339156164721 |
| 1.0 | 60 | ce | 3 | 3 | 10 | False | all | 24102 | 0 | 0.4685088374408763 | 0.9008165422413527 | -1.023606496956524 | -0.12199729611748897 | 0.7757558490752449 | -0.16428917587953604 | -19.28968473434947 | 2952.5529454805933 | 13 | 11808 | 10412 | 1882 | -0.16428917587953604 | -0.2083109029930698 | -0.08654881993093733 |
| 2.0 | 120 | ce | 3 | 3 | 10 | False | all | 18719 | 0 | 0.33693039158074684 | 1.7000786589600698 | -1.046167804629438 | -0.1208739082749841 | 0.8257502790399056 | -0.16200309494300374 | -12.310411340506544 | 2282.4934764005197 | 19 | 11851 | 5073 | 1795 | -0.16200309494300374 | -0.21022725074062842 | -0.08937457004837322 |
| 2.0 | 240 | ce | 3 | 3 | 10 | False | all | 17509 | 0 | 0.32703181221086297 | 1.8102158702945028 | -1.0604677079268037 | -0.1216628550571251 | 0.829522911203029 | -0.16135567823132657 | -11.723579654176334 | 2150.8659970422877 | 19 | 11503 | 5099 | 907 | -0.16135567823132657 | -0.20750384734098043 | -0.09014647015400747 |
| 2.0 | 60 | ce | 3 | 3 | 10 | False | all | 20671 | 0 | 0.35445793623917565 | 1.493961276434271 | -1.0095674777377261 | -0.12217184221848544 | 0.8125388726017474 | -0.16387638638152954 | -13.748329573253617 | 2548.627488015046 | 19 | 12033 | 4738 | 3900 | -0.16387638638152954 | -0.21228079795897722 | -0.08938025413568243 |
| dol | 120 | ce | 3 | 3 | 10 | False | all | 17420 | 0 | 0.3039035591274397 | 1.9873800940575126 | -1.0489833873024585 | -0.12622171851257985 | 0.8271393804443835 | -0.17124314814156633 | -10.173704285314335 | 2237.4599835089084 | 23 | 11601 | 3605 | 2214 | -0.17124314814156633 | -0.21992127442858872 | -0.10057771556449067 |
| dol | 240 | ce | 3 | 3 | 10 | False | all | 15747 | 0 | 0.28405410554391314 | 2.23937864044011 | -1.0624962368750979 | -0.12458512198140874 | 0.8362208630583121 | -0.16622908179518334 | -8.971348945292638 | 2002.3795488303126 | 27 | 11013 | 3628 | 1106 | -0.16622908179518334 | -0.21519934585393913 | -0.10162528266203849 |
| dol | 60 | ce | 3 | 3 | 10 | False | all | 19822 | 0 | 0.33341741499344163 | 1.6264287466195388 | -1.0143032891834625 | -0.13383724011565726 | 0.8020501507414791 | -0.17863925610363862 | -12.820392113145992 | 2678.788514995885 | 23 | 11975 | 3310 | 4537 | -0.17863925610363862 | -0.22862302314743146 | -0.1090121937686306 |
| 1.0 | 120 | proximal | 3 | 3 | 10 | False | all | 25612 | 0 | 0.4688427299703264 | 0.9253418829142248 | -1.0459186293155671 | -0.12170746927904759 | 0.7809232934376364 | -0.162593940871385 | -19.569366100821 | 3125.3639643116826 | 18 | 13041 | 11498 | 1073 | -0.162593940871385 | -0.20682247051329597 | -0.09419746982634328 |
| 1.0 | 240 | proximal | 3 | 3 | 10 | False | all | 24840 | 0 | 0.4713768115942029 | 0.9373735160058849 | -1.0594247725045385 | -0.11818036186973377 | 0.7889773940914035 | -0.15839176708844382 | -18.55646175022959 | 2943.7924499809164 | 18 | 12848 | 11440 | 552 | -0.15839176708844382 | -0.20238135452386924 | -0.0901383423413474 |
| 1.0 | 60 | proximal | 3 | 3 | 10 | False | all | 27090 | 0 | 0.46688815060908084 | 0.890759708154608 | -1.0066874352836035 | -0.12079184760525365 | 0.7749263569723861 | -0.1618703025266835 | -20.441692859070177 | 3281.684310901046 | 18 | 13019 | 11425 | 2646 | -0.1618703025266835 | -0.20620105007596362 | -0.0941320566950998 |
| 2.0 | 120 | proximal | 3 | 3 | 10 | False | all | 20073 | 0 | 0.3403576944153838 | 1.6651319271926464 | -1.037257011292933 | -0.11747814277634472 | 0.8283032035737706 | -0.16303890485773478 | -12.490443668219141 | 2379.3766482875985 | 22 | 12517 | 5329 | 2227 | -0.16303890485773478 | -0.20855046515616774 | -0.08983941628127214 |
| 2.0 | 240 | proximal | 3 | 3 | 10 | False | all | 18388 | 0 | 0.33119425712421147 | 1.7870434984320822 | -1.0559749331972947 | -0.11438355574336244 | 0.8380391712711518 | -0.16021742664258912 | -11.329692459347088 | 2123.3767809584388 | 24 | 11962 | 5324 | 1102 | -0.16021742664258912 | -0.20449235576938538 | -0.08621122133493563 |
| 2.0 | 60 | proximal | 3 | 3 | 10 | False | all | 22822 | 0 | 0.3617123827885374 | 1.4362702546946826 | -0.9967472866657365 | -0.11669471441395056 | 0.8165787266013645 | -0.16261913938298156 | -14.011768436711595 | 2690.2795784673813 | 18 | 12910 | 4996 | 4916 | -0.16261913938298156 | -0.20887936190002532 | -0.09185270173009809 |
| dol | 120 | proximal | 3 | 3 | 10 | False | all | 18894 | 0 | 0.31756113051762463 | 1.8654717465902306 | -1.0399257667782833 | -0.11728444782988261 | 0.8347374941475264 | -0.16308869932516212 | -10.17563856243993 | 2268.701523702236 | 21 | 12218 | 4029 | 2647 | -0.16308869932516212 | -0.2113134558274248 | -0.09615146258101848 |
| dol | 240 | proximal | 3 | 3 | 10 | False | all | 16674 | 0 | 0.29686937747391146 | 2.14549181731789 | -1.0567330558036516 | -0.10609055118858428 | 0.8572173624120494 | -0.15147984495688466 | -7.99959391838783 | 1819.676870120765 | 22 | 11399 | 3992 | 1283 | -0.15147984495688466 | -0.19796867314755873 | -0.08299142053404973 |
| dol | 60 | proximal | 3 | 3 | 10 | False | all | 22059 | 0 | 0.3481118817716125 | 1.5249981291225885 | -0.9989593133153776 | -0.12033973851683087 | 0.815205858829127 | -0.16527630360301748 | -12.551940244453442 | 2697.9767862965305 | 18 | 12779 | 3752 | 5528 | -0.16527630360301748 | -0.2130461792317458 | -0.10116538467564433 |
| 2.0 | 120 | proximal | 3 | 3 | 10 | False | rth | 7269 | 0 | 0.35231806300729124 | 1.6079986855750157 | -1.0073440474356548 | -0.08591156164114032 | 0.8683223692875248 | -0.12056954659885134 | -5.573388848868385 | 658.3319786499119 | 23 | 4375 | 1855 | 1039 | -0.12056954659885134 | -0.15602708166243243 | -0.05861779749892383 |
| 2.0 | 120 | proximal | 3 | 3 | 10 | True | all | 13916 | 0 | 0.34054325955734405 | 1.6583634945313563 | -1.031434579455189 | -0.11544197578874471 | 0.8302789334870394 | -0.16108870426273636 | -10.237311589301749 | 1609.0220372537185 | 21 | 8627 | 3671 | 1618 | -0.16108870426273636 | -0.20448612611171463 | -0.0919202380315374 |
| 2.0 | 120 | proximal | 3 | 3 | 20 | False | all | 20527 | 0 | 0.3539240999658986 | 1.506594999789649 | -1.00497067478548 | -0.11606705390623269 | 0.8212393065938315 | -0.16074472210691196 | -12.956800214366275 | 2389.1598208489536 | 20 | 11991 | 4811 | 3725 | -0.16074472210691196 | -0.2006040329349696 | -0.09178441218159505 |
| 2.0 | 120 | proximal | 3 | 3 | 5 | False | all | 16798 | 0 | 0.3371829979759495 | 1.759279391150503 | -1.0586862072820316 | -0.10851611860945892 | 0.8453558996204507 | -0.15614421288377597 | -10.286363690106072 | 1835.2838990060295 | 20 | 10792 | 4845 | 1161 | -0.15614421288377597 | -0.2041551663474307 | -0.08425185726268095 |
| 2.0 | 120 | proximal | 5 | 3 | 10 | False | all | 16992 | 0 | 0.3428083804143126 | 1.6848485281059515 | -1.0402501995941116 | -0.10606351828214904 | 0.8448555640955356 | -0.15168317129254694 | -10.298411762890506 | 1809.703793183905 | 19 | 10605 | 4635 | 1752 | -0.15168317129254694 | -0.1967747788164109 | -0.08071301861085761 |

## Strategy-specific diagnostics

### Ablation

| Rung | Trades | Net avg R | t | Daily Sharpe | Win rate | Winning months |
|---|---:|---:|---:|---:|---:|---:|
| fvg_only | 38697 | -0.14575020644595424 | -20.755433803925516 | -10.013377314802078 | 0.3166653745768406 | 0.0 |
| plus_sweep | 20073 | -0.11747814277634472 | -12.490443668219141 | -6.094532089919697 | 0.3403576944153838 | 0.020833333333333332 |
| plus_displacement | 13916 | -0.11544197578874471 | -10.237311589301749 | -4.799315864065977 | 0.34054325955734405 | 0.0625 |
| plus_windows | 2727 | -0.08312754667056439 | -3.270294429079802 | -1.5572992956079237 | 0.35203520352035206 | 0.2916666666666667 |
| plus_B4 | 1533 | -0.045428215192178795 | -1.3169908493205467 | -0.6885226642918492 | 0.36007827788649704 | 0.4375 |
| hindsight_Binf | 1557 | 0.14807696518892982 | 4.190675582816735 | 2.205053108406899 | 0.4341682723185613 | 0.7708333333333334 |

### Textbook Benchmarks

| Rung | Trades | Net avg R | t | Daily Sharpe | Win rate | Winning months |
|---|---:|---:|---:|---:|---:|---:|
| 1m | 1128 | -0.05698726363755213 | -1.6232515604041606 | -0.8097715143639718 | 0.4078014184397163 | 0.4375 |
| 5m | 144 | -0.08141990382230789 | -1.3526895372097614 | -0.6685172638625207 | 0.4236111111111111 | 0.375 |
