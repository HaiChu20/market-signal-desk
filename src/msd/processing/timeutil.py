"""Resolution-independent timestamp conversion for kernels and as-of searches."""
from __future__ import annotations

import numpy as np
import pandas as pd


def epoch_ints(values, *, unit: str="ns"):
    """Return UTC Unix integers after an explicit nanosecond normalization."""
    stamps=pd.to_datetime(values,utc=True)
    if isinstance(stamps,pd.Timestamp):
        ns=stamps.as_unit("ns").value
    else:
        ns=stamps.astype("datetime64[ns, UTC]").astype("int64")
    if unit=="ns":return ns
    if unit=="s":return ns//1_000_000_000
    raise ValueError(unit)


def epoch_ns(values):
    return epoch_ints(values,unit="ns")


def epoch_seconds(values):
    return epoch_ints(values,unit="s")
