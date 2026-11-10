"""Causal add-ons for candidate events; these never generate events."""
from __future__ import annotations

import numpy as np
import pandas as pd


def killzones(events: list[dict], *, timezone: str = 'America/New_York') -> list[dict]:
    """#15 Keep London 02:00-05:00 and New York 08:00-11:00 local signals."""
    out=[]
    for event in events:
        t=pd.Timestamp(event['known_at']).tz_convert(timezone)
        minute=t.hour*60+t.minute
        if 120<=minute<300 or 480<=minute<660: out.append(event)
    return out


def macro_blackout(events: list[dict], macro_events: pd.DataFrame) -> list[dict]:
    """#32 Remove decisions from 15 minutes before to 30 minutes after known scheduled macro releases."""
    if macro_events is None or macro_events.empty: return events
    times=pd.to_datetime(macro_events['ts'] if 'ts' in macro_events else macro_events['known_at'],utc=True).sort_values().map(lambda x: x.value).to_numpy()
    out=[]
    for event in events:
        t=pd.Timestamp(event['known_at']).tz_convert('UTC').value
        j=np.searchsorted(times,t)
        near=times[max(j-1,0):min(j+1,len(times))]
        if not any(-15*60*10**9<=t-x<=30*60*10**9 for x in near): out.append(event)
    return out


def time_of_day_calendar(events: list[dict], *, timezone: str = 'America/New_York') -> list[dict]:
    """#41 Annotate local hour, weekday and month without removing events."""
    result=[]
    for event in events:
        t=pd.Timestamp(event['known_at']).tz_convert(timezone)
        result.append({**event,'local_hour':t.hour,'local_weekday':t.day_of_week,'local_month':t.month})
    return result


def vol_sizing(events: list[dict], features: pd.DataFrame, *, target_atr_fraction: float = .01,
               max_fraction: float = .01) -> list[dict]:
    """#43 Annotate size fraction scaled by causal ATR/price, capped at max_fraction."""
    if features is None or features.empty: return [{**e,'size_fraction':0.0} for e in events]
    f=features.set_index('ts')
    result=[]
    for event in events:
        row=f.loc[event['ts']] if event['ts'] in f.index else None
        if isinstance(row,pd.DataFrame): row=row.iloc[-1]
        if row is None or pd.Timestamp(row.known_at)>pd.Timestamp(event['known_at']): size=0.0
        else:
            atr=float(row.get('1d_atr14',row.get('1h_atr14',np.nan)))
            price=float(event['price'])
            size=min(max_fraction,target_atr_fraction/(atr/price)) if np.isfinite(atr) and atr>0 and price>0 else 0.0
        result.append({**event,'size_fraction':float(size)})
    return result
