# cProfile baseline: BTCUSDT, 2022-01

Development-period month; no labels or outcome metrics were evaluated. The event definitions were already registered in module docstrings and `reports/trials.csv`. Profile artifacts are under `data/tmp/profiles/` (gitignored).

| Layer | Runtime | Peak RSS at end of layer |
|---|---:|---:|
| HTF | 0.433 s | 0.165 GiB |
| Levels | 2.888 s | 0.179 GiB |
| Features | 0.750 s | 0.695 GiB |
| S/R event detection | 2.056 s | 0.696 GiB |
| Liquidity sweep detection | 2.182 s | 0.696 GiB |
| RSI(2) detection | 0.017 s | 0.696 GiB |

Annual-streaming check: a separate BTCUSDT 2022 full-year development pass peaked at 4.44 GiB RSS after full-year feature construction. This exceeds the 3 GiB per-worker requirement and prevents launching parallel workers. The month profile used only the target month and did not include the production warm-up overlap.

## Top cumulative-time entries by layer

### HTF

```text
         1652409 function calls (1648708 primitive calls) in 0.433 seconds

   Ordered by: cumulative time
   List reduced from 905 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.433    0.433 <stdin>:20(<lambda>)
        1    0.000    0.000    0.433    0.433 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/timeframes.py:121(build_all_timeframes)
        5    0.006    0.001    0.433    0.087 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/timeframes.py:34(build_timeframe)
        5    0.000    0.000    0.214    0.043 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:2076(aggregate)
        5    0.000    0.000    0.214    0.043 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/apply.py:335(agg)
        5    0.000    0.000    0.214    0.043 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/apply.py:574(agg_dict_like)
        5    0.000    0.000    0.214    0.043 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/apply.py:1873(agg_or_apply_dict_like)
        5    0.000    0.000    0.211    0.042 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/apply.py:584(compute_dict_like)
   120/55    0.000    0.000    0.208    0.004 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:324(aggregate)
       55    0.000    0.000    0.208    0.004 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:520(_aggregate_multiple_funcs)
        5    0.000    0.000    0.194    0.039 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:512(_python_agg_general)
        5    0.000    0.000    0.194    0.039 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/ops.py:1148(agg_series)
        5    0.006    0.001    0.194    0.039 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/ops.py:1163(_aggregate_series_pure_python)
    13280    0.002    0.000    0.136    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:513(<lambda>)
    13280    0.002    0.000    0.134    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/timeframes.py:83(<lambda>)
```

### Levels

```text
         16612360 function calls (16416220 primitive calls) in 2.889 seconds

   Ordered by: cumulative time
   List reduced from 1174 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    2.888    2.888 <stdin>:21(<lambda>)
        1    0.002    0.002    2.888    2.888 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/levels.py:261(build_levels)
        1    0.004    0.004    2.332    2.332 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/levels.py:130(_vwap_snapshots)
      265    0.003    0.000    2.288    0.009 {method 'extend' of 'list' objects}
    46112    0.173    0.000    2.285    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/levels.py:152(<genexpr>)
   101302    0.040    0.000    1.514    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/generic.py:6419(__getattr__)
   101259    0.083    0.000    1.149    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4283(__getitem__)
   101258    0.026    0.000    0.939    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4978(_get_item)
   101275    0.058    0.000    0.886    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4239(_ixs)
   101015    0.052    0.000    0.799    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1327(__getitem__)
   101015    0.076    0.000    0.671    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2399(_getitem_axis)
   101275    0.114    0.000    0.408    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/managers.py:1241(iget)
   202166    0.073    0.000    0.364    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/arrays/datetimelike.py:372(__getitem__)
3944021/3943628    0.205    0.000    0.323    0.000 {built-in method builtins.isinstance}
   101003    0.034    0.000    0.310    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/series.py:1063(_ixs)
```

### Features

```text
         1895695 function calls (1873840 primitive calls) in 0.750 seconds

   Ordered by: cumulative time
   List reduced from 1034 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.750    0.750 <stdin>:22(<lambda>)
        1    0.002    0.002    0.750    0.750 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/features.py:190(build_features)
        1    0.337    0.337    0.360    0.360 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/features.py:140(_nearest_level_features)
        5    0.001    0.000    0.173    0.035 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/features.py:113(_structure)
        5    0.004    0.001    0.143    0.029 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/levels.py:28(pivot_events)
        6    0.001    0.000    0.107    0.018 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/features.py:37(indicator_frame)
     6975    0.003    0.000    0.097    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/generic.py:6419(__getattr__)
     6430    0.006    0.000    0.092    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4283(__getitem__)
     6328    0.002    0.000    0.065    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4978(_get_item)
     6328    0.004    0.000    0.062    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4239(_ixs)
      674    0.002    0.000    0.047    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/managers.py:410(apply)
     5555    0.003    0.000    0.045    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1327(__getitem__)
  743/392    0.001    0.000    0.043    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4540(__setitem__)
     5555    0.004    0.000    0.038    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2399(_getitem_axis)
       81    0.000    0.000    0.034    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/generic.py:7685(replace)
```

### Events: S/R touch

```text
         7584366 function calls (7583933 primitive calls) in 2.056 seconds

   Ordered by: cumulative time
   List reduced from 524 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    2.056    2.056 <stdin>:24(<lambda>)
        1    0.152    0.152    2.056    2.056 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/sr_touch.py:24(detect)
    45241    0.552    0.000    1.640    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:43(bar_clusters)
    71881    0.338    0.000    0.937    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:66(_cluster)
    69121    0.101    0.000    0.286    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_function_base_impl.py:451(average)
    45241    0.177    0.000    0.247    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:36(update_touches)
    71881    0.081    0.000    0.167    0.000 {built-in method builtins.min}
   180964    0.029    0.000    0.128    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:1459(searchsorted)
   210123    0.028    0.000    0.101    0.000 {method 'sum' of 'numpy.ndarray' objects}
   180966    0.030    0.000    0.099    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:48(_wrapfunc)
    69121    0.014    0.000    0.094    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:2474(any)
   354265    0.088    0.000    0.088    0.000 {method 'reduce' of 'numpy.ufunc' objects}
  2061456    0.086    0.000    0.086    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:77(<genexpr>)
  1990206    0.083    0.000    0.083    0.000 {method 'append' of 'list' objects}
    69125    0.029    0.000    0.079    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:86(_wrapreduction_any_all)
```

### Events: liquidity sweep

```text
         7709740 function calls (7709196 primitive calls) in 2.182 seconds

   Ordered by: cumulative time
   List reduced from 518 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    2.182    2.182 <stdin>:24(<lambda>)
        1    0.133    0.133    2.182    2.182 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/liquidity_sweep.py:25(detect)
    45241    0.574    0.000    1.746    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:43(bar_clusters)
    71881    0.373    0.000    1.015    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:66(_cluster)
    69121    0.108    0.000    0.311    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_function_base_impl.py:451(average)
    45241    0.194    0.000    0.269    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:36(update_touches)
    71881    0.084    0.000    0.173    0.000 {built-in method builtins.min}
   180964    0.030    0.000    0.136    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:1459(searchsorted)
   210123    0.030    0.000    0.108    0.000 {method 'sum' of 'numpy.ndarray' objects}
   180966    0.032    0.000    0.106    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:48(_wrapfunc)
    69121    0.015    0.000    0.100    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:2474(any)
   354265    0.094    0.000    0.094    0.000 {method 'reduce' of 'numpy.ufunc' objects}
  2061456    0.089    0.000    0.089    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:77(<genexpr>)
  1990329    0.085    0.000    0.085    0.000 {method 'append' of 'list' objects}
    69125    0.030    0.000    0.084    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:86(_wrapreduction_any_all)
```

### Events: RSI(2)

```text
         90091 function calls (88470 primitive calls) in 0.017 seconds

   Ordered by: cumulative time
   List reduced from 580 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.017    0.017 <stdin>:24(<lambda>)
        1    0.000    0.000    0.017    0.017 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/rsi2_mean_reversion.py:15(detect)
        1    0.000    0.000    0.011    0.011 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:1376(itertuples)
        1    0.000    0.000    0.010    0.010 {method 'extend' of 'list' objects}
      361    0.000    0.000    0.010    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:1450(<genexpr>)
      360    0.000    0.000    0.009    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1327(__getitem__)
      360    0.000    0.000    0.008    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2369(_getitem_tuple)
      360    0.001    0.000    0.005    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1189(_getitem_lowerdim)
      360    0.000    0.000    0.004    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2399(_getitem_axis)
      368    0.000    0.000    0.003    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4239(_ixs)
        1    0.000    0.000    0.003    0.003 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:15963(merge)
        1    0.000    0.000    0.003    0.003 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/reshape/merge.py:151(merge)
       12    0.000    0.000    0.002    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4283(__getitem__)
15470/15441    0.001    0.000    0.002    0.000 {built-in method builtins.isinstance}
      360    0.000    0.000    0.002    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1115(_validate_tuple_indexer)
```


### Labels

Input: 44,640 one-minute bars; output 208,250 labels; runtime 0.798 s (261,119 labels/s); peak process RSS 0.344 GiB. This is a performance-only label kernel profile; no label outcomes were analyzed. Optimized output was compared row-for-row with the pre-optimization baseline and matched exactly.

Top 15 cumulative-time entries:

```text
         1326678 function calls (1320391 primitive calls) in 0.785 seconds

   Ordered by: cumulative time
   List reduced from 585 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.265    0.265    0.785    0.785 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/labels.py:180(label_grid)
        5    0.262    0.052    0.262    0.052 {built-in method msd._msd_kernels.first_hit_batch}
        3    0.000    0.000    0.162    0.054 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:466(__init__)
        1    0.003    0.003    0.161    0.161 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:466(nested_data_to_arrays)
        1    0.000    0.000    0.158    0.158 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:765(to_arrays)
        1    0.000    0.000    0.131    0.131 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:955(_finalize_columns_and_data)
        1    0.000    0.000    0.131    0.131 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:1010(convert_object_array)
       16    0.127    0.008    0.131    0.008 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:1032(convert)
    46/45    0.022    0.000    0.033    0.001 {built-in method numpy.asarray}
        1    0.022    0.022    0.027    0.027 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:856(_list_to_arrays)
   419501    0.019    0.000    0.019    0.000 {method 'lower' of 'str' objects}
   416689    0.016    0.000    0.016    0.000 {method 'append' of 'list' objects}
        4    0.000    0.000    0.012    0.003 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/base.py:601(to_numpy)
        1    0.000    0.000    0.012    0.012 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/arrays/base.py:687(to_numpy)
        1    0.000    0.000    0.012    0.012 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/arrays/datetimes.py:671(__array__)



```
