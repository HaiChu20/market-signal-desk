"""Purged temporal folds. CPCV supports symmetric research splits; walk-forward is causal."""
from __future__ import annotations
from itertools import combinations
import numpy as np
import pandas as pd

EMBARGO = pd.Timedelta(days=1)

def _times(frame):
    start=pd.to_datetime(frame.known_at,utc=True).to_numpy(dtype='datetime64[ns]')
    end=pd.to_datetime(frame.label_end_ts,utc=True).to_numpy(dtype='datetime64[ns]')
    return start,end

def _purge(frame, test, forward=False, embargo=EMBARGO):
    start,end=_times(frame)
    t=np.asarray(test,dtype=int)
    if len(t)==0:return np.arange(len(frame),dtype=int)
    # Evaluation may contain disjoint intervals. Purge against every contiguous test block.
    mask=np.ones(len(frame),dtype=bool);mask[t]=False
    rank=np.empty(len(frame),dtype=int);rank[np.argsort(start,kind='stable')]=np.arange(len(frame))
    ordered=t[np.argsort(rank[t])];blocks=np.split(ordered,np.flatnonzero(np.diff(rank[ordered])>1)+1)
    for block in blocks:
        a=start[block].min();b=end[block].max()
        mask &= ~((start<=b+np.timedelta64(int(embargo.value),'ns'))&(end>=a))
    if forward: mask &= start<start[t].min()
    return np.flatnonzero(mask)

def walk_forward(frame, n_folds=5):
    order=np.argsort(_times(frame)[0],kind='stable')
    for test in np.array_split(order,n_folds+1)[1:]:
        train=_purge(frame,test,forward=True)
        if len(train) and len(test):yield train,test

def cpcv(frame,n_groups=5,n_test_groups=2):
    order=np.argsort(_times(frame)[0],kind='stable')
    groups=np.array_split(order,n_groups)
    for selected in combinations(range(n_groups),n_test_groups):
        test=np.sort(np.concatenate([groups[i] for i in selected]))
        train=_purge(frame,test)
        if len(train) and len(test):yield train,test
