# B alt USATECHIDXUSD dev

| Scope | Trades | Win rate | Avg win R | Avg loss R | Net avg R | 1.5x-cost R | PF | t | Max DD R | Longest loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| default | 975 | 0.4841025641025641 | 0.8565480333030112 | -0.7617919345029963 | 0.02165059350155304 | 0.013035074213267802 | 1.0550896567555061 | 0.7116991477376664 | 20.11119774088681 | 9 |
| chosen | 975 | 0.38769230769230767 | 1.5753589752008512 | -0.95281445933273 | 0.027338933747981315 | 0.012401141933371608 | 1.0468601331194645 | 0.6131437720596593 | 37.63104086275626 | 11 |

Full parameter grid is in the paired CSV. Equity is cumulative net R; period labels separate dev and holdout.

## Diagnostics

Configurations tried in local dev grids: 807.
DSR: 0.004602224165432656 (trials=807).

### default

- 2019: 239 trades, net avg 0.014725507397802073R
- 2020: 246 trades, net avg -0.038689862178677474R
- 2021: 245 trades, net avg 0.042961025982664054R
- 2022: 245 trades, net avg 0.06768239643323055R
- long: 516 trades, net avg 0.03658520573670112R
- short: 459 trades, net avg 0.0048613562175957295R
- Entry hour 10: 800 trades, net avg 0.03632788250764221R
- Entry hour 11: 97 trades, net avg -0.10998795109680784R
- Entry hour 12: 31 trades, net avg 0.010371459846246236R
- Entry hour 13: 18 trades, net avg 0.04953557393608394R
- Entry hour 14: 16 trades, net avg 0.07141878570483623R
- Entry hour 15: 13 trades, net avg 0.027692135148482823R

### chosen

- 2019: 239 trades, net avg 0.029121801632550483R
- 2020: 246 trades, net avg -0.03294437629000501R
- 2021: 245 trades, net avg 0.038255508101896256R
- 2022: 245 trades, net avg 0.07521251794481168R
- long: 516 trades, net avg 0.04014907574948038R
- short: 459 trades, net avg 0.012937989798583679R
- Entry hour 10: 800 trades, net avg 0.04095510794921015R
- Entry hour 11: 97 trades, net avg -0.08114609073267438R
- Entry hour 12: 31 trades, net avg 0.038692001383060864R
- Entry hour 13: 18 trades, net avg 0.05870225660075642R
- Entry hour 14: 16 trades, net avg -0.0833955269013808R
- Entry hour 15: 13 trades, net avg 0.06467543190128214R

## Random-direction benchmark

- default: 78.3 percentile; mean=-0.001986622409852102R; 5–95%=-0.05074470147079345–0.04692094786556333R
- chosen: 78.60000000000001 percentile; mean=-0.0040392747627161505R; 5–95%=-0.07192524531019302–0.06322716018826881R

## Cost and fill sensitivity

```json
{
  "cost_multipliers": {
    "chosen": {
      "1.0": {
        "summary": {
          "trades": 975,
          "win_rate": 0.38769230769230767,
          "avg_win_R": 1.5753589752008512,
          "avg_loss_R": -0.95281445933273,
          "net_avg_R": 0.027338933747981315,
          "net_avg_R_cost15": 0.012401141933371598,
          "profit_factor": 1.0468601331194645,
          "t": 0.6131437720596593,
          "max_drawdown_R": 37.63104086275626,
          "longest_losing_streak": 11,
          "exit_reason_counts": {
            "stop": 530,
            "time": 351,
            "target": 94
          },
          "trades_per_year": 243.75,
          "total_R": 26.655460404281783,
          "longest_losing_streak_days": 11,
          "winning_days": 0.3795180722891566,
          "winning_weeks": 0.5023923444976076,
          "winning_months": 0.5625
        }
      },
      "1.5": {
        "summary": {
          "trades": 975,
          "win_rate": 0.38666666666666666,
          "avg_win_R": 1.5653807270366418,
          "avg_loss_R": -0.966651205196951,
          "net_avg_R": 0.012401141933371608,
          "net_avg_R_cost15": -0.010005545788542928,
          "profit_factor": 1.0209168033345768,
          "t": 0.27802455692936356,
          "max_drawdown_R": 39.75594202437165,
          "longest_losing_streak": 11,
          "exit_reason_counts": {
            "stop": 530,
            "time": 351,
            "target": 94
          },
          "trades_per_year": 243.75,
          "total_R": 12.091113385037318,
          "longest_losing_streak_days": 11,
          "winning_days": 0.3785140562248996,
          "winning_weeks": 0.4880382775119617,
          "winning_months": 0.5208333333333334
        }
      },
      "2.0": {
        "summary": {
          "trades": 975,
          "win_rate": 0.38666666666666666,
          "avg_win_R": 1.551239193271968,
          "avg_loss_R": -0.982142619252895,
          "net_avg_R": -0.0025683184099479918,
          "net_avg_R_cost15": -0.032438384873886915,
          "profit_factor": 0.9957363873776511,
          "t": -0.0575547522623678,
          "max_drawdown_R": 43.656833036835906,
          "longest_losing_streak": 11,
          "exit_reason_counts": {
            "stop": 531,
            "time": 350,
            "target": 94
          },
          "trades_per_year": 243.75,
          "total_R": -2.504110449699292,
          "longest_losing_streak_days": 11,
          "winning_days": 0.3785140562248996,
          "winning_weeks": 0.4784688995215311,
          "winning_months": 0.4791666666666667
        }
      }
    },
    "default": {
      "1.0": {
        "summary": {
          "trades": 975,
          "win_rate": 0.4841025641025641,
          "avg_win_R": 0.8565480333030112,
          "avg_loss_R": -0.7617919345029963,
          "net_avg_R": 0.02165059350155304,
          "net_avg_R_cost15": 0.01303342012124499,
          "profit_factor": 1.0550896567555061,
          "t": 0.7116991477376664,
          "max_drawdown_R": 20.11119774088681,
          "longest_losing_streak": 9,
          "exit_reason_counts": {
            "time": 595,
            "stop": 312,
            "target": 68
          },
          "trades_per_year": 243.75,
          "total_R": 21.109328664014214,
          "longest_losing_streak_days": 9,
          "winning_days": 0.4738955823293173,
          "winning_weeks": 0.5119617224880383,
          "winning_months": 0.5
        }
      },
      "1.5": {
        "summary": {
          "trades": 975,
          "win_rate": 0.48205128205128206,
          "avg_win_R": 0.8519147371827852,
          "avg_loss_R": -0.767704414094996,
          "net_avg_R": 0.013035074213267802,
          "net_avg_R_cost15": 0.00011108638425874245,
          "profit_factor": 1.032781793330087,
          "t": 0.4283671888155407,
          "max_drawdown_R": 25.98513323967666,
          "longest_losing_streak": 9,
          "exit_reason_counts": {
            "time": 595,
            "stop": 312,
            "target": 68
          },
          "trades_per_year": 243.75,
          "total_R": 12.709197357936107,
          "longest_losing_streak_days": 9,
          "winning_days": 0.4718875502008032,
          "winning_weeks": 0.507177033492823,
          "winning_months": 0.4791666666666667
        }
      },
      "2.0": {
        "summary": {
          "trades": 975,
          "win_rate": 0.48102564102564105,
          "avg_win_R": 0.8454808890477828,
          "avg_loss_R": -0.777122213378893,
          "net_avg_R": 0.0033914840960926596,
          "net_avg_R_cost15": -0.013836119487707214,
          "profit_factor": 1.0084091976568483,
          "t": 0.11134395647092657,
          "max_drawdown_R": 32.861437796634185,
          "longest_losing_streak": 9,
          "exit_reason_counts": {
            "time": 594,
            "stop": 313,
            "target": 68
          },
          "trades_per_year": 243.75,
          "total_R": 3.306696993690343,
          "longest_losing_streak_days": 9,
          "winning_days": 0.4708835341365462,
          "winning_weeks": 0.49760765550239233,
          "winning_months": 0.4791666666666667
        }
      }
    }
  },
  "cost_models": {
    "chosen": {
      "futures": {
        "summary": {
          "trades": 975,
          "win_rate": 0.38769230769230767,
          "avg_win_R": 1.5753589752008512,
          "avg_loss_R": -0.95281445933273,
          "net_avg_R": 0.027338933747981315,
          "net_avg_R_cost15": 0.012401141933371598,
          "profit_factor": 1.0468601331194645,
          "t": 0.6131437720596593,
          "max_drawdown_R": 37.63104086275626,
          "longest_losing_streak": 11,
          "exit_reason_counts": {
            "stop": 530,
            "time": 351,
            "target": 94
          },
          "trades_per_year": 243.75,
          "total_R": 26.655460404281783,
          "longest_losing_streak_days": 11,
          "winning_days": 0.3795180722891566,
          "winning_weeks": 0.5023923444976076,
          "winning_months": 0.5625
        }
      },
      "dukascopy": {
        "summary": {
          "trades": 975,
          "win_rate": 0.38358974358974357,
          "avg_win_R": 1.5591834880214488,
          "avg_loss_R": -0.965997426694348,
          "net_avg_R": 0.002636072899198511,
          "net_avg_R_cost15": -0.019977842489059927,
          "profit_factor": 1.004427021085213,
          "t": 0.059388964299430504,
          "max_drawdown_R": 42.21597547445308,
          "longest_losing_streak": 11,
          "exit_reason_counts": {
            "stop": 535,
            "time": 349,
            "target": 91
          },
          "trades_per_year": 243.75,
          "total_R": 2.570171076718548,
          "longest_losing_streak_days": 11,
          "winning_days": 0.3755020080321285,
          "winning_weeks": 0.4784688995215311,
          "winning_months": 0.5
        }
      },
      "capital": {
        "summary": {
          "trades": 975,
          "win_rate": 0.38153846153846155,
          "avg_win_R": 1.5455342577027322,
          "avg_loss_R": -0.9744554375400362,
          "net_avg_R": -0.012982446124333781,
          "net_avg_R_cost15": -0.0413360591157957,
          "profit_factor": 0.9784582069568946,
          "t": -0.2934334155263675,
          "max_drawdown_R": 53.413924345167366,
          "longest_losing_streak": 11,
          "exit_reason_counts": {
            "stop": 536,
            "time": 349,
            "target": 90
          },
          "trades_per_year": 243.75,
          "total_R": -12.657884971225437,
          "longest_losing_streak_days": 11,
          "winning_days": 0.37349397590361444,
          "winning_weeks": 0.4688995215311005,
          "winning_months": 0.4583333333333333
        }
      }
    },
    "default": {
      "futures": {
        "summary": {
          "trades": 975,
          "win_rate": 0.4841025641025641,
          "avg_win_R": 0.8565480333030112,
          "avg_loss_R": -0.7617919345029963,
          "net_avg_R": 0.02165059350155304,
          "net_avg_R_cost15": 0.01303342012124499,
          "profit_factor": 1.0550896567555061,
          "t": 0.7116991477376664,
          "max_drawdown_R": 20.11119774088681,
          "longest_losing_streak": 9,
          "exit_reason_counts": {
            "time": 595,
            "stop": 312,
            "target": 68
          },
          "trades_per_year": 243.75,
          "total_R": 21.109328664014214,
          "longest_losing_streak_days": 9,
          "winning_days": 0.4738955823293173,
          "winning_weeks": 0.5119617224880383,
          "winning_months": 0.5
        }
      },
      "dukascopy": {
        "summary": {
          "trades": 975,
          "win_rate": 0.48102564102564105,
          "avg_win_R": 0.8485100004075918,
          "avg_loss_R": -0.7703875503754014,
          "net_avg_R": 0.008343681744828193,
          "net_avg_R_cost15": -0.005336072124700066,
          "profit_factor": 1.0208690448931754,
          "t": 0.27444040047967777,
          "max_drawdown_R": 29.698118277186765,
          "longest_losing_streak": 9,
          "exit_reason_counts": {
            "time": 594,
            "stop": 314,
            "target": 67
          },
          "trades_per_year": 243.75,
          "total_R": 8.135089701207487,
          "longest_losing_streak_days": 9,
          "winning_days": 0.4708835341365462,
          "winning_weeks": 0.507177033492823,
          "winning_months": 0.4583333333333333
        }
      },
      "capital": {
        "summary": {
          "trades": 975,
          "win_rate": 0.47692307692307695,
          "avg_win_R": 0.8469738424645656,
          "avg_loss_R": -0.7747392407692207,
          "net_avg_R": -0.0013068472269533898,
          "net_avg_R_cost15": -0.018802646153088437,
          "profit_factor": 0.996775193157908,
          "t": -0.042963255185817895,
          "max_drawdown_R": 35.81835542802905,
          "longest_losing_streak": 9,
          "exit_reason_counts": {
            "time": 591,
            "stop": 317,
            "target": 67
          },
          "trades_per_year": 243.75,
          "total_R": -1.274176046279555,
          "longest_losing_streak_days": 9,
          "winning_days": 0.46686746987951805,
          "winning_weeks": 0.49282296650717705,
          "winning_months": 0.4583333333333333
        }
      }
    }
  },
  "fill_variants": {
    "chosen": {
      "trade_through": {
        "summary": {
          "trades": 975,
          "win_rate": 0.38769230769230767,
          "avg_win_R": 1.5753589752008512,
          "avg_loss_R": -0.95281445933273,
          "net_avg_R": 0.027338933747981315,
          "net_avg_R_cost15": 0.012401141933371598,
          "profit_factor": 1.0468601331194645,
          "t": 0.6131437720596593,
          "max_drawdown_R": 37.63104086275626,
          "longest_losing_streak": 11,
          "exit_reason_counts": {
            "stop": 530,
            "time": 351,
            "target": 94
          },
          "trades_per_year": 243.75,
          "total_R": 26.655460404281783,
          "longest_losing_streak_days": 11,
          "winning_days": 0.3795180722891566,
          "winning_weeks": 0.5023923444976076,
          "winning_months": 0.5625
        }
      },
      "touch": {
        "summary": {
          "trades": 975,
          "win_rate": 0.38769230769230767,
          "avg_win_R": 1.5753589752008512,
          "avg_loss_R": -0.95281445933273,
          "net_avg_R": 0.027338933747981315,
          "net_avg_R_cost15": 0.012401141933371598,
          "profit_factor": 1.0468601331194645,
          "t": 0.6131437720596593,
          "max_drawdown_R": 37.63104086275626,
          "longest_losing_streak": 11,
          "exit_reason_counts": {
            "stop": 530,
            "time": 351,
            "target": 94
          },
          "trades_per_year": 243.75,
          "total_R": 26.655460404281783,
          "longest_losing_streak_days": 11,
          "winning_days": 0.3795180722891566,
          "winning_weeks": 0.5023923444976076,
          "winning_months": 0.5625
        }
      }
    },
    "default": {
      "trade_through": {
        "summary": {
          "trades": 975,
          "win_rate": 0.4841025641025641,
          "avg_win_R": 0.8565480333030112,
          "avg_loss_R": -0.7617919345029963,
          "net_avg_R": 0.02165059350155304,
          "net_avg_R_cost15": 0.01303342012124499,
          "profit_factor": 1.0550896567555061,
          "t": 0.7116991477376664,
          "max_drawdown_R": 20.11119774088681,
          "longest_losing_streak": 9,
          "exit_reason_counts": {
            "time": 595,
            "stop": 312,
            "target": 68
          },
          "trades_per_year": 243.75,
          "total_R": 21.109328664014214,
          "longest_losing_streak_days": 9,
          "winning_days": 0.4738955823293173,
          "winning_weeks": 0.5119617224880383,
          "winning_months": 0.5
        }
      },
      "touch": {
        "summary": {
          "trades": 975,
          "win_rate": 0.48512820512820515,
          "avg_win_R": 0.8588720479573861,
          "avg_loss_R": -0.7612042299568726,
          "net_avg_R": 0.024740466918454915,
          "net_avg_R_cost15": 0.016129768708136268,
          "profit_factor": 1.0631259020709913,
          "t": 0.812083729415852,
          "max_drawdown_R": 19.122698488773985,
          "longest_losing_streak": 9,
          "exit_reason_counts": {
            "time": 595,
            "stop": 311,
            "target": 69
          },
          "trades_per_year": 243.75,
          "total_R": 24.12195524549354,
          "longest_losing_streak_days": 9,
          "winning_days": 0.4748995983935743,
          "winning_weeks": 0.5119617224880383,
          "winning_months": 0.5
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
      "trades": 982,
      "win_rate": 0.34521384928716903,
      "avg_win_R": 1.747127711378964,
      "avg_loss_R": -1.0413795831464463,
      "net_avg_R": -0.0787482462379799,
      "net_avg_R_cost15": -0.12723724716870358,
      "profit_factor": 0.8845132002877798,
      "t": -1.6823940860412974,
      "max_drawdown_R": 111.86839540043042,
      "longest_losing_streak": 11,
      "exit_reason_counts": {
        "stop": 591,
        "time": 277,
        "target": 114
      },
      "trades_per_year": 245.5,
      "total_R": -77.33077780569626,
      "longest_losing_streak_days": 11,
      "winning_days": 0.341046277665996,
      "winning_weeks": 0.3923444976076555,
      "winning_months": 0.3125
    },
    "by_year": {
      "2019": {
        "trades": 244,
        "win_rate": 0.3360655737704918,
        "avg_win_R": 1.5691686190491894,
        "avg_loss_R": -1.060602006150036,
        "net_avg_R": -0.17682663210767358,
        "net_avg_R_cost15": -0.2508750556830759,
        "profit_factor": 0.7488865106443596,
        "t": -1.9665313039924406,
        "max_drawdown_R": 48.43629637399098,
        "longest_losing_streak": 8,
        "exit_reason_counts": {
          "stop": 142,
          "time": 77,
          "target": 25
        }
      },
      "2020": {
        "trades": 247,
        "win_rate": 0.3076923076923077,
        "avg_win_R": 1.941842186915399,
        "avg_loss_R": -1.0512225238367028,
        "net_avg_R": -0.13027953591297914,
        "net_avg_R_cost15": -0.17580642238420935,
        "profit_factor": 0.8209878997003537,
        "t": -1.368840550619162,
        "max_drawdown_R": 34.36326280930336,
        "longest_losing_streak": 11,
        "exit_reason_counts": {
          "stop": 162,
          "time": 54,
          "target": 31
        }
      },
      "2021": {
        "trades": 248,
        "win_rate": 0.3588709677419355,
        "avg_win_R": 1.583089425437499,
        "avg_loss_R": -1.0324207433651027,
        "net_avg_R": -0.09379007794804002,
        "net_avg_R_cost15": -0.1427493487199629,
        "profit_factor": 0.8583049327990439,
        "t": -1.048589869566825,
        "max_drawdown_R": 30.02922939527672,
        "longest_losing_streak": 8,
        "exit_reason_counts": {
          "stop": 143,
          "time": 80,
          "target": 25
        }
      },
      "2022": {
        "trades": 243,
        "win_rate": 0.3786008230452675,
        "avg_win_R": 1.9035815470209516,
        "avg_loss_R": -1.0190436900379578,
        "net_avg_R": 0.08746463016541516,
        "net_avg_R_cost15": 0.062109307318741175,
        "profit_factor": 1.1381239489401342,
        "t": 0.8799606525223009,
        "max_drawdown_R": 12.192310104390248,
        "longest_losing_streak": 8,
        "exit_reason_counts": {
          "stop": 144,
          "time": 66,
          "target": 33
        }
      }
    },
    "long_vs_short": {
      "long": {
        "trades": 530,
        "win_rate": 0.3660377358490566,
        "avg_win_R": 1.545166936722407,
        "avg_loss_R": -1.031342353450513,
        "net_avg_R": -0.08824272648155744,
        "net_avg_R_cost15": -0.1392464098892621,
        "profit_factor": 0.8650376419891207,
        "t": -1.4719357421051398,
        "max_drawdown_R": 61.04412842252677,
        "longest_losing_streak": 11,
        "exit_reason_counts": {
          "stop": 304,
          "time": 185,
          "target": 41
        }
      },
      "short": {
        "trades": 452,
        "win_rate": 0.32079646017699115,
        "avg_win_R": 2.0173372995401504,
        "avg_loss_R": -1.052364955061214,
        "net_avg_R": -0.06761533798776725,
        "net_avg_R_cost15": -0.11315570681052656,
        "profit_factor": 0.9054026641635348,
        "t": -0.9192746740965245,
        "max_drawdown_R": 65.01865012284883,
        "longest_losing_streak": 13,
        "exit_reason_counts": {
          "stop": 287,
          "time": 92,
          "target": 73
        }
      }
    },
    "by_entry_hour": {
      "10": {
        "trades": 827,
        "win_rate": 0.3385731559854897,
        "avg_win_R": 1.8119399717856848,
        "avg_loss_R": -1.046816371279702,
        "net_avg_R": -0.07891821401451665,
        "net_avg_R_cost15": -0.1259138497383103,
        "profit_factor": 0.8860209781885855,
        "t": -1.5285536713907604,
        "max_drawdown_R": 89.31231354945271,
        "longest_losing_streak": 11,
        "exit_reason_counts": {
          "stop": 510,
          "time": 218,
          "target": 99
        }
      },
      "11": {
        "trades": 94,
        "win_rate": 0.3723404255319149,
        "avg_win_R": 1.4801060040612848,
        "avg_loss_R": -1.0336522729525799,
        "net_avg_R": -0.0976784464048642,
        "net_avg_R_cost15": -0.1524205322021675,
        "profit_factor": 0.8494432880721435,
        "t": -0.6808611144392116,
        "max_drawdown_R": 34.64292107643699,
        "longest_losing_streak": 10,
        "exit_reason_counts": {
          "stop": 52,
          "time": 33,
          "target": 9
        }
      },
      "12": {
        "trades": 33,
        "win_rate": 0.3333333333333333,
        "avg_win_R": 1.6416834443583441,
        "avg_loss_R": -1.011392624709326,
        "net_avg_R": -0.12703393502010257,
        "net_avg_R_cost15": -0.1938334390353472,
        "profit_factor": 0.8115955190152607,
        "t": -0.5048650039948135,
        "max_drawdown_R": 10.339982447651003,
        "longest_losing_streak": 9,
        "exit_reason_counts": {
          "stop": 18,
          "time": 11,
          "target": 4
        }
      },
      "13": {
        "trades": 12,
        "win_rate": 0.3333333333333333,
        "avg_win_R": 1.4094278466264354,
        "avg_loss_R": -1.0114548867852475,
        "net_avg_R": -0.20449397564802005,
        "net_avg_R_cost15": -0.25653936423753315,
        "profit_factor": 0.6967329265203727,
        "t": -0.5303562492131291,
        "max_drawdown_R": 3.483672456575684,
        "longest_losing_streak": 3,
        "exit_reason_counts": {
          "stop": 7,
          "time": 4,
          "target": 1
        }
      },
      "14": {
        "trades": 11,
        "win_rate": 0.5454545454545454,
        "avg_win_R": 1.1929151628051293,
        "avg_loss_R": -0.9491376349792031,
        "net_avg_R": 0.21925480017588728,
        "net_avg_R_cost15": 0.177468250088034,
        "profit_factor": 1.508209286630512,
        "t": 0.5378545871003723,
        "max_drawdown_R": 2.3260613945543636,
        "longest_losing_streak": 2,
        "exit_reason_counts": {
          "time": 6,
          "stop": 4,
          "target": 1
        }
      },
      "15": {
        "trades": 5,
        "win_rate": 0.6,
        "avg_win_R": 0.7585572213512508,
        "avg_loss_R": -0.4625338780913152,
        "net_avg_R": 0.2701207815742245,
        "net_avg_R_cost15": 0.20682642979358667,
        "profit_factor": 2.4600053875453427,
        "t": 0.6792531403032666,
        "max_drawdown_R": 0.586634686096994,
        "longest_losing_streak": 1,
        "exit_reason_counts": {
          "time": 5
        }
      }
    },
    "daily": {
      "sharpe_annualized": -0.8470907119856478,
      "max_drawdown_R": 111.86839540043042,
      "winning_periods": {
        "day": 0.341046277665996,
        "week": 0.3923444976076555,
        "month": 0.3125
      },
      "winning_days": {
        "wins": 339,
        "days": 994,
        "percent": 34.1046277665996
      }
    },
    "costs": {
      "x1_net_avg_R": -0.0787482462379799,
      "x1_5_net_avg_R": -0.12723724716870358,
      "x2_net_avg_R": -0.17572624809942727,
      "median_stop_points": 9.870124999999689,
      "median_cost_R": 0.08134023507143562
    },
    "diagnostics": {
      "minimum_stop_skips": 0,
      "bad_opening_range": 1,
      "signals": 982,
      "unresolved_at_end": 0
    }
  },
  "default": {
    "overall": {
      "trades": 982,
      "win_rate": 0.4460285132382892,
      "avg_win_R": 0.9639858817985573,
      "avg_loss_R": -0.8436563578532456,
      "net_avg_R": -0.037396377234620685,
      "net_avg_R_cost15": -0.06592833727945267,
      "profit_factor": 0.9199840554186004,
      "t": -1.130710140954946,
      "max_drawdown_R": 76.53823838765624,
      "longest_losing_streak": 7,
      "exit_reason_counts": {
        "time": 505,
        "stop": 374,
        "target": 103
      },
      "trades_per_year": 245.5,
      "total_R": -36.72324244439751,
      "longest_losing_streak_days": 7,
      "winning_days": 0.44064386317907445,
      "winning_weeks": 0.4258373205741627,
      "winning_months": 0.4583333333333333
    },
    "by_year": {
      "2019": {
        "trades": 244,
        "win_rate": 0.39344262295081966,
        "avg_win_R": 0.9151267931880386,
        "avg_loss_R": -0.8033987967180186,
        "net_avg_R": -0.12725758101727483,
        "net_avg_R_cost15": -0.17161397718424032,
        "profit_factor": 0.7388556718886101,
        "t": -2.025595806899593,
        "max_drawdown_R": 40.14877569453444,
        "longest_losing_streak": 7,
        "exit_reason_counts": {
          "time": 139,
          "stop": 84,
          "target": 21
        }
      },
      "2020": {
        "trades": 247,
        "win_rate": 0.4291497975708502,
        "avg_win_R": 1.0513437078224346,
        "avg_loss_R": -0.8837824340367464,
        "net_avg_R": -0.05332344198381863,
        "net_avg_R_cost15": -0.0797480494691359,
        "profit_factor": 0.8943059230596804,
        "t": -0.7739399157925241,
        "max_drawdown_R": 18.37826812006457,
        "longest_losing_streak": 6,
        "exit_reason_counts": {
          "time": 111,
          "stop": 108,
          "target": 28
        }
      },
      "2021": {
        "trades": 248,
        "win_rate": 0.45161290322580644,
        "avg_win_R": 0.860399373536603,
        "avg_loss_R": -0.8361292174417931,
        "net_avg_R": -0.06995501506445286,
        "net_avg_R_cost15": -0.0984259471641585,
        "profit_factor": 0.8474338358121623,
        "t": -1.1092326603537184,
        "max_drawdown_R": 23.122623756849535,
        "longest_losing_streak": 7,
        "exit_reason_counts": {
          "time": 132,
          "stop": 92,
          "target": 24
        }
      },
      "2022": {
        "trades": 243,
        "win_rate": 0.5102880658436214,
        "avg_win_R": 1.020697429164829,
        "avg_loss_R": -0.8547826889633084,
        "net_avg_R": 0.10225243304446527,
        "net_avg_R_cost15": 0.08740570510337436,
        "profit_factor": 1.244274000282249,
        "t": 1.4802257492453945,
        "max_drawdown_R": 9.110167468172818,
        "longest_losing_streak": 6,
        "exit_reason_counts": {
          "time": 123,
          "stop": 90,
          "target": 30
        }
      }
    },
    "long_vs_short": {
      "long": {
        "trades": 530,
        "win_rate": 0.4830188679245283,
        "avg_win_R": 0.84700361886348,
        "avg_loss_R": -0.8215878310385223,
        "net_avg_R": -0.015626677878309875,
        "net_avg_R_cost15": -0.045357719433593055,
        "profit_factor": 0.963209306984483,
        "t": -0.3714524729317391,
        "max_drawdown_R": 29.598391457533232,
        "longest_losing_streak": 9,
        "exit_reason_counts": {
          "time": 309,
          "stop": 185,
          "target": 36
        }
      },
      "short": {
        "trades": 452,
        "win_rate": 0.4026548672566372,
        "avg_win_R": 1.1285323615314136,
        "avg_loss_R": -0.8660518258059647,
        "net_avg_R": -0.06292279462144529,
        "net_avg_R_cost15": -0.09004875201021728,
        "profit_factor": 0.8783705362597442,
        "t": -1.2037533179509736,
        "max_drawdown_R": 49.42508655873177,
        "longest_losing_streak": 10,
        "exit_reason_counts": {
          "time": 196,
          "stop": 189,
          "target": 67
        }
      }
    },
    "by_entry_hour": {
      "10": {
        "trades": 827,
        "win_rate": 0.4486094316807739,
        "avg_win_R": 0.9965359375429301,
        "avg_loss_R": -0.8608765937821546,
        "net_avg_R": -0.02762381370766073,
        "net_avg_R_cost15": -0.055414398591003645,
        "profit_factor": 0.9418053040628621,
        "t": -0.7509310550096534,
        "max_drawdown_R": 57.54771702920998,
        "longest_losing_streak": 8,
        "exit_reason_counts": {
          "time": 408,
          "stop": 326,
          "target": 93
        }
      },
      "11": {
        "trades": 94,
        "win_rate": 0.425531914893617,
        "avg_win_R": 0.812896971535524,
        "avg_loss_R": -0.7658405162728824,
        "net_avg_R": -0.09403732997143285,
        "net_avg_R_cost15": -0.1255861665512318,
        "profit_factor": 0.786254960460428,
        "t": -0.9777326491560555,
        "max_drawdown_R": 20.89003549366622,
        "longest_losing_streak": 10,
        "exit_reason_counts": {
          "time": 56,
          "stop": 30,
          "target": 8
        }
      },
      "12": {
        "trades": 33,
        "win_rate": 0.3939393939393939,
        "avg_win_R": 0.8418839538738353,
        "avg_loss_R": -0.7299590589186119,
        "net_avg_R": -0.11074817509128422,
        "net_avg_R_cost15": -0.14933635541038312,
        "profit_factor": 0.7496647426071696,
        "t": -0.6808562705631307,
        "max_drawdown_R": 6.160865915742967,
        "longest_losing_streak": 6,
        "exit_reason_counts": {
          "time": 21,
          "stop": 10,
          "target": 2
        }
      },
      "13": {
        "trades": 12,
        "win_rate": 0.3333333333333333,
        "avg_win_R": 0.7886931004515824,
        "avg_loss_R": -0.9480904477141374,
        "net_avg_R": -0.3691625983255642,
        "net_avg_R_cost15": -0.397749590226832,
        "profit_factor": 0.415937689464721,
        "t": -1.3499450277004323,
        "max_drawdown_R": 4.42995117990677,
        "longest_losing_streak": 3,
        "exit_reason_counts": {
          "stop": 7,
          "time": 5
        }
      },
      "14": {
        "trades": 11,
        "win_rate": 0.6363636363636364,
        "avg_win_R": 0.6683988585821731,
        "avg_loss_R": -0.5807947831261854,
        "net_avg_R": 0.21414662523367908,
        "net_avg_R_cost15": 0.18902413694039974,
        "profit_factor": 2.013960931644027,
        "t": 0.8462565573945767,
        "max_drawdown_R": 1.1955537545413948,
        "longest_losing_streak": 2,
        "exit_reason_counts": {
          "time": 10,
          "stop": 1
        }
      },
      "15": {
        "trades": 5,
        "win_rate": 0.6,
        "avg_win_R": 0.4056829085595514,
        "avg_loss_R": -0.26343006808869074,
        "net_avg_R": 0.13803771790025454,
        "net_avg_R_cost15": 0.10260187741470177,
        "profit_factor": 2.310003437551598,
        "t": 0.646092012076338,
        "max_drawdown_R": 0.35003002568011643,
        "longest_losing_streak": 1,
        "exit_reason_counts": {
          "time": 5
        }
      }
    },
    "daily": {
      "sharpe_annualized": -0.5693215475342202,
      "max_drawdown_R": 76.53823838765624,
      "winning_periods": {
        "day": 0.44064386317907445,
        "week": 0.4258373205741627,
        "month": 0.4583333333333333
      },
      "winning_days": {
        "wins": 438,
        "days": 994,
        "percent": 44.06438631790744
      }
    },
    "costs": {
      "x1_net_avg_R": -0.037396377234620685,
      "x1_5_net_avg_R": -0.06592833727945267,
      "x2_net_avg_R": -0.09446029732428471,
      "median_stop_points": 17.382250000000113,
      "median_cost_R": 0.048322082196203806
    },
    "diagnostics": {
      "minimum_stop_skips": 0,
      "bad_opening_range": 1,
      "signals": 982,
      "unresolved_at_end": 0
    }
  }
}
```

## Grid heat map

| target_r | stop_mode | trades | unresolved_at_end | win_rate | avg_win_R | avg_loss_R | net_avg_R | profit_factor | net_avg_R_cost15 | t | max_drawdown_R | longest_losing_streak | exit_stop | exit_target | exit_time | net_avg_R_x1_5_rerun | net_avg_R_x2_rerun | net_avg_R_touch_fill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.5 | mid | 975 | 0 | 0.4358974358974359 | 1.2483215411871451 | -0.955914853654671 | 0.0049061389686846976 | 1.0090983483731066 | -0.011659368201332237 | 0.1341487266401373 | 37.053030166495304 | 9 | 491 | 313 | 171 | -0.011659368201332237 | -0.02568759082271154 | 0.014983360675404699 |
| 2.0 | mid | 975 | 0 | 0.4 | 1.4104127291055484 | -0.9548173315930253 | -0.008725307313595719 | 0.9847696743923461 | -0.023181457746400545 | -0.2183180194215506 | 41.46285286778215 | 11 | 521 | 205 | 249 | -0.023181457746400545 | -0.03766927670791528 | -0.006728972726425504 |
| 3.0 | mid | 975 | 0 | 0.38769230769230767 | 1.5753589752008512 | -0.95281445933273 | 0.027338933747981315 | 1.0468601331194645 | 0.012401141933371608 | 0.6131437720596593 | 37.63104086275626 | 11 | 530 | 94 | 351 | 0.012401141933371608 | -0.0025683184099479918 | 0.027338933747981315 |
| 1.5 | opposite | 975 | 0 | 0.49230769230769234 | 0.8410322335917532 | -0.7631540320071183 | 0.026599206441556875 | 1.0686524268062703 | 0.01820979949697151 | 0.9065045771481065 | 17.528620983535344 | 9 | 308 | 144 | 523 | 0.01820979949697151 | 0.008792794321217042 | 0.026599206441556875 |
| 2.0 | opposite | 975 | 0 | 0.4841025641025641 | 0.8565480333030112 | -0.7617919345029963 | 0.02165059350155304 | 1.0550896567555061 | 0.013035074213267802 | 0.7116991477376664 | 20.11119774088681 | 9 | 312 | 68 | 595 | 0.013035074213267802 | 0.0033914840960926596 | 0.024740466918454915 |
| 3.0 | opposite | 975 | 0 | 0.48 | 0.8646455345187938 | -0.7622412725306704 | 0.018664394853072454 | 1.0470888527276578 | 0.009892425443547867 | 0.5932108591955233 | 23.287558932562447 | 9 | 315 | 22 | 638 | 0.009892425443547867 | 9.238520513336131e-05 | 0.018664394853072454 |
