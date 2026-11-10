# Processing performance and output equivalence

Profile target: BTCUSDT, 2022-01, 44,640 one-minute bars. cProfile artifacts and full top-15 listings are stored under `data/tmp/profiles/perf_after/` (gitignored). The production 370-day warm-up was excluded, consistent with the accepted baseline profile.

## Before / after

| Layer | Before | After | Notes |
|---|---:|---:|---|
| HTF construction | 0.433 s | 0.413 s | no algorithm change |
| Levels | 2.888 s | 0.539 s | `_vwap_snapshots` changed from per-row pandas access to per-session NumPy cumulative sums |
| VWAP snapshots only | 2.332 s | 0.0033 s median | 5-run timing; same values and dtypes |
| Features | 0.750 s | 0.718 s | no algorithm change |
| S/R touch detector | 2.056 s | 1.367 s | array touch-state, split-based clustering, array cluster reductions |
| Liquidity sweep detector | 2.182 s | 1.357 s | same shared clustering improvements |
| RSI(2) detector | 0.017 s | 0.017 s | no change |
| Full label grid | 0.798 s / 208,250 labels | 2.702 s / 204,400 labels | current cProfile run; inputs/output row counts differ, so this is not a like-for-like speed comparison. One unprofiled current run was 2.57 s. Investigate after the concurrent data campaign drains. |

The optimized VWAP was compared row-for-row and dtype-for-dtype against the saved pre-change BTCUSDT 2024-01 output: 44,640 rows exactly match. The event detectors were compared against saved pre-change Jan 2024 outputs after restricting to the calendar month: S/R 110/110 and sweep 346/346 rows match exactly, including all event fields. The checked-in synthetic tests also cover VWAP session resets and missing volumes, plus the pilot event behavior.

## Current cProfile top 15 per layer


### HTF

```text
         1606875 function calls (1603176 primitive calls) in 0.413 seconds

   Ordered by: cumulative time
   List reduced from 898 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.413    0.413 <stdin>:22(<lambda>)
        1    0.000    0.000    0.413    0.413 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/timeframes.py:121(build_all_timeframes)
        5    0.006    0.001    0.413    0.083 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/timeframes.py:34(build_timeframe)
        5    0.000    0.000    0.207    0.041 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:2076(aggregate)
        5    0.000    0.000    0.206    0.041 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/apply.py:335(agg)
        5    0.000    0.000    0.206    0.041 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/apply.py:574(agg_dict_like)
        5    0.000    0.000    0.206    0.041 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/apply.py:1873(agg_or_apply_dict_like)
        5    0.000    0.000    0.203    0.041 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/apply.py:584(compute_dict_like)
   120/55    0.000    0.000    0.201    0.004 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:324(aggregate)
       55    0.000    0.000    0.201    0.004 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:520(_aggregate_multiple_funcs)
        5    0.000    0.000    0.188    0.038 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:512(_python_agg_general)
        5    0.000    0.000    0.187    0.037 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/ops.py:1148(agg_series)
        5    0.006    0.001    0.187    0.037 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/ops.py:1163(_aggregate_series_pure_python)
    12865    0.002    0.000    0.131    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/groupby/generic.py:513(<lambda>)
    12865    0.002    0.000    0.129    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/timeframes.py:83(<lambda>)
```

### Levels

```text
         2747921 function calls (2736442 primitive calls) in 0.539 seconds

   Ordered by: cumulative time
   List reduced from 1184 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.539    0.539 <stdin>:23(<lambda>)
        1    0.000    0.000    0.539    0.539 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/levels.py:267(build_levels)
        1    0.076    0.076    0.268    0.268 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/levels.py:105(_round_levels)
       10    0.005    0.001    0.210    0.021 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/levels.py:28(pivot_events)
    44642    0.100    0.000    0.143    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_index_tricks_impl.py:343(__getitem__)
     8868    0.004    0.000    0.130    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/generic.py:6419(__getattr__)
     8826    0.007    0.000    0.099    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4283(__getitem__)
     8825    0.002    0.000    0.080    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4978(_get_item)
     8843    0.005    0.000    0.075    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4239(_ixs)
     8591    0.005    0.000    0.069    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1327(__getitem__)
     8591    0.007    0.000    0.057    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2399(_getitem_axis)
607186/606806    0.029    0.000    0.040    0.000 {built-in method builtins.isinstance}
     8843    0.010    0.000    0.035    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/managers.py:1241(iget)
    17311    0.006    0.000    0.032    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/arrays/datetimelike.py:372(__getitem__)
     8783    0.004    0.000    0.027    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexes/base.py:5742(_can_hold_identifiers_and_holds_name)
```

### Features

```text
         1839252 function calls (1818354 primitive calls) in 0.718 seconds

   Ordered by: cumulative time
   List reduced from 984 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.718    0.718 <stdin>:24(<lambda>)
        1    0.002    0.002    0.718    0.718 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/features.py:190(build_features)
        1    0.334    0.334    0.358    0.358 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/features.py:140(_nearest_level_features)
        5    0.001    0.000    0.160    0.032 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/features.py:113(_structure)
        5    0.003    0.001    0.131    0.026 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/levels.py:28(pivot_events)
        6    0.001    0.000    0.104    0.017 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/features.py:37(indicator_frame)
     6792    0.003    0.000    0.088    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/generic.py:6419(__getattr__)
     6274    0.005    0.000    0.084    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4283(__getitem__)
     6172    0.002    0.000    0.057    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4978(_get_item)
     6172    0.004    0.000    0.054    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4239(_ixs)
     5367    0.003    0.000    0.043    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1327(__getitem__)
  744/393    0.001    0.000    0.042    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4540(__setitem__)
      647    0.002    0.000    0.041    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/managers.py:410(apply)
     5365    0.004    0.000    0.036    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2399(_getitem_axis)
372171/370069    0.021    0.000    0.032    0.000 {built-in method builtins.isinstance}
```

### S/R touch

```text
         4411871 function calls (4411665 primitive calls) in 1.367 seconds

   Ordered by: cumulative time
   List reduced from 524 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.127    0.127    1.367    1.367 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/sr_touch.py:24(detect)
    43801    0.218    0.000    0.991    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:49(bar_clusters)
    68002    0.190    0.000    0.444    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:65(_cluster)
    43801    0.171    0.000    0.237    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:36(update_touches)
   330338    0.053    0.000    0.143    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:48(_wrapfunc)
    43565    0.014    0.000    0.128    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_shape_base_impl.py:780(split)
   175204    0.027    0.000    0.121    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:1459(searchsorted)
   201500    0.061    0.000    0.118    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:66(_wrapreduction)
    43565    0.054    0.000    0.110    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_shape_base_impl.py:719(array_split)
   136004    0.029    0.000    0.106    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:3187(min)
    43565    0.020    0.000    0.067    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/numeric.py:675(flatnonzero)
   272388    0.067    0.000    0.067    0.000 {method 'reduce' of 'numpy.ufunc' objects}
    43565    0.053    0.000    0.063    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_function_base_impl.py:1414(diff)
    65496    0.019    0.000    0.063    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:2342(sum)
   175204    0.057    0.000    0.057    0.000 {method 'searchsorted' of 'numpy.ndarray' objects}
```

### Liquidity sweep

```text
         4515443 function calls (4515249 primitive calls) in 1.357 seconds

   Ordered by: cumulative time
   List reduced from 518 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.102    0.102    1.357    1.357 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/liquidity_sweep.py:25(detect)
    43801    0.219    0.000    0.997    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:49(bar_clusters)
    68002    0.191    0.000    0.446    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:65(_cluster)
    43801    0.173    0.000    0.240    0.000 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/level_clusters.py:36(update_touches)
   330338    0.054    0.000    0.145    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:48(_wrapfunc)
    43565    0.014    0.000    0.128    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_shape_base_impl.py:780(split)
   175204    0.027    0.000    0.123    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:1459(searchsorted)
   201500    0.062    0.000    0.119    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:66(_wrapreduction)
    43565    0.054    0.000    0.110    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_shape_base_impl.py:719(array_split)
   136004    0.029    0.000    0.107    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:3187(min)
   272388    0.067    0.000    0.067    0.000 {method 'reduce' of 'numpy.ufunc' objects}
    43565    0.020    0.000    0.067    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/numeric.py:675(flatnonzero)
    43565    0.053    0.000    0.063    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/lib/_function_base_impl.py:1414(diff)
    65496    0.019    0.000    0.063    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/numpy/_core/fromnumeric.py:2342(sum)
   175204    0.058    0.000    0.058    0.000 {method 'searchsorted' of 'numpy.ndarray' objects}
```

### RSI(2)

```text
         90145 function calls (88524 primitive calls) in 0.017 seconds

   Ordered by: cumulative time
   List reduced from 579 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.017    0.017 <stdin>:27(<lambda>)
        1    0.000    0.000    0.017    0.017 /Users/bfhach/Projects/market-signal-desk/src/msd/methods/rsi2_mean_reversion.py:15(detect)
        1    0.000    0.000    0.011    0.011 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:1376(itertuples)
        1    0.000    0.000    0.010    0.010 {method 'extend' of 'list' objects}
      361    0.000    0.000    0.010    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:1450(<genexpr>)
      360    0.000    0.000    0.010    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1327(__getitem__)
      360    0.000    0.000    0.008    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2369(_getitem_tuple)
      360    0.001    0.000    0.005    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1189(_getitem_lowerdim)
      360    0.000    0.000    0.004    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2399(_getitem_axis)
      368    0.000    0.000    0.003    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4239(_ixs)
        1    0.000    0.000    0.003    0.003 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:15963(merge)
        1    0.000    0.000    0.003    0.003 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/reshape/merge.py:151(merge)
       12    0.000    0.000    0.002    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:4283(__getitem__)
15477/15448    0.001    0.000    0.002    0.000 {built-in method builtins.isinstance}
      360    0.000    0.000    0.002    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1115(_validate_tuple_indexer)
```

### Full label grid

```text
         1302946 function calls (1296871 primitive calls) in 2.702 seconds

   Ordered by: cumulative time
   List reduced from 507 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.013    0.013    2.702    2.702 <stdin>:30(<lambda>)
        1    0.253    0.253    2.689    2.689 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/labels.py:180(label_grid)
        5    2.185    0.437    2.185    0.437 {built-in method msd._msd_kernels.first_hit_batch}
        3    0.000    0.000    0.162    0.054 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:466(__init__)
        1    0.003    0.003    0.161    0.161 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:466(nested_data_to_arrays)
        1    0.000    0.000    0.159    0.159 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:765(to_arrays)
        1    0.000    0.000    0.132    0.132 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:955(_finalize_columns_and_data)
        1    0.000    0.000    0.132    0.132 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:1010(convert_object_array)
       16    0.128    0.008    0.132    0.008 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:1032(convert)
    45/44    0.019    0.000    0.030    0.001 {built-in method numpy.asarray}
        1    0.022    0.022    0.027    0.027 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:856(_list_to_arrays)
   411746    0.018    0.000    0.018    0.000 {method 'lower' of 'str' objects}
   408986    0.016    0.000    0.016    0.000 {method 'append' of 'list' objects}
        4    0.000    0.000    0.011    0.003 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/base.py:601(to_numpy)
        1    0.000    0.000    0.011    0.011 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/arrays/base.py:687(to_numpy)
```
