"""Choose robust candidate edges using prediction uncertainty and neighbouring geometry."""
from __future__ import annotations
import numpy as np
import pandas as pd

def expected_r(p,tp_r,cost_r=0,financing_r=0):
    return np.asarray(p)*np.asarray(tp_r)-(1-np.asarray(p))-np.asarray(cost_r)-np.asarray(financing_r)

def choose(frame,threshold=0.05,uncertainty=None):
    """One signal per event; require adjacent candidates in SL/TP-distance rank."""
    if frame.empty:return frame.copy()
    work=frame.copy()
    if uncertainty is None:uncertainty=np.sqrt(np.clip(work.p*(1-work.p),0,1)/max(1,len(work)))
    work['edge']=expected_r(work.p,work.TP_R,work.cost_R,work.financing_R)
    work['shrunk_edge']=np.maximum(0,work.edge-1.64*np.asarray(uncertainty)*(work.TP_R+1))
    selected=[]
    for _,group in work.groupby('event_key',sort=False):
        group=group.sort_values('shrunk_edge',ascending=False)
        best=group.iloc[0]
        if best.shrunk_edge<=threshold:continue
        distances=(group.TP_R-best.TP_R).abs()+((group.price-group.sl).abs()-(best.price-best.sl)).abs()/max(abs(best.price-best.sl),1e-9)
        nearby=group.loc[distances.gt(0)].iloc[np.argsort(distances[distances.gt(0)].to_numpy())[:2]]
        if len(nearby)<2 or not nearby.shrunk_edge.gt(0).all():continue
        selected.append(best)
    return pd.DataFrame(selected,columns=work.columns).reset_index(drop=True)
