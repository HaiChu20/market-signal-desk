# Label kernel profile: BTCUSDT, 2024-01

Development/test performance-only profile; no label performance statistics were analyzed. Input: 44,640 1-minute bars. Output: 208,320 labels. Runtime: 4.140 s (50,317 labels/s). Peak process RSS: 0.369 GiB (reported by resource.getrusage).

Top 15 cumulative-time entries:

```text
         25263837 function calls (24828957 primitive calls) in 4.123 seconds

   Ordered by: cumulative time
   List reduced from 572 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.423    0.423    4.123    4.123 /Users/bfhach/Projects/market-signal-desk/src/msd/processing/labels.py:180(label_grid)
   428544    0.200    0.000    3.011    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:1327(__getitem__)
   428544    0.298    0.000    2.508    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2399(_getitem_axis)
   428560    0.124    0.000    0.987    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/series.py:1063(_ixs)
4438533/4438476    0.311    0.000    0.915    0.000 {built-in method builtins.isinstance}
   419620    0.121    0.000    0.709    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/arrays/datetimelike.py:372(__getitem__)
  2143119    0.365    0.000    0.604    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/dtypes/generic.py:45(_instancecheck)
   419620    0.085    0.000    0.571    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/arrays/_mixins.py:385(__getitem__)
   428549    0.068    0.000    0.559    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/common.py:112(is_bool_indexer)
   419616    0.211    0.000    0.486    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/arrays/datetimes.py:570(_box_func)
   428544    0.085    0.000    0.291    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/indexing.py:2347(_validate_integer)
        5    0.255    0.051    0.255    0.051 {built-in method msd._msd_kernels.first_hit_batch}
  2143119    0.169    0.000    0.239    0.000 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/dtypes/generic.py:40(_check)
        3    0.000    0.000    0.216    0.072 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/frame.py:466(__init__)
        1    0.004    0.004    0.215    0.215 /Users/bfhach/Projects/market-signal-desk/.venv/lib/python3.12/site-packages/pandas/core/internals/construction.py:466(nested_data_to_arrays)



```
