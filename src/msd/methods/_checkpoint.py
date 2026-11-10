"""Finite detector context carried across production event chunks."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ._detectors import detect_rule

# Only inputs consumed by _detectors are kept in a JSON checkpoint.  The long
# lookbacks are isolated to the two rules that compute session statistics.
FEATURES = (
    'ts','known_at','1h_atr14','1m_atr14','1h_swing_high','1h_swing_low',
    '15m_swing_high','15m_swing_low','1h_ema50_200_gap_atr',
    '15m_ema50_200_gap_atr','1h_ema20_50_gap_atr',
    '1d_ema50_200_gap_atr','volume_z20','1h_macd_hist_atr',
    '1h_stoch_k14','1h_stoch_d3','1h_bollinger_pctb20',
    '1h_bollinger_width20','vwap_distance_atr','1h_donchian20_position',
    '1d_return_bars_20','1d_return_bars_60','1d_return_bars_1',
    '1d_bar_known_at','minutes_since_session_open','session_id',
    'prior_day_high_distance_atr','prior_day_low_distance_atr',
    'taker_buy_ratio','funding_z20','vix_percentile_1y',
    'macro_minutes_since_event','earnings_minutes_since_event','gex',
)
BARS = ('ts','bid_o','bid_h','bid_l','bid_c','sym')
SESSION_RULES = {'intraday_momentum': 2, 'vix_spike_dip_buy': 4,
                 'range_breakout_nr4_nr7': 14, 'trend_following': 100}
SESSION_FEATURES = {'trend_following': ('ts','known_at','1h_atr14','1m_atr14','1d_return_bars_20',
                                       '1d_return_bars_60','1d_bar_known_at','session_id'),
                    'range_breakout_nr4_nr7': ('ts','known_at','1h_atr14','1m_atr14','session_id',
                                               'prior_day_high_distance_atr','prior_day_low_distance_atr')}


def _records(frame: pd.DataFrame) -> list[dict]:
    def value(x):
        if isinstance(x, pd.Timestamp): return x.isoformat()
        if isinstance(x, np.generic): x=x.item()
        if pd.isna(x): return None
        return x
    return [{key:value(item) for key,item in row.items()} for row in frame.to_dict('records')]


def _frame(rows: list[dict]) -> pd.DataFrame:
    out=pd.DataFrame(rows)
    for key in ('ts','known_at','1d_bar_known_at'):
        if key in out: out[key]=pd.to_datetime(out[key],utc=True)
    return out


def detect_checkpointed(name: str, features: pd.DataFrame, levels: pd.DataFrame,
                         bars: pd.DataFrame, *, state: dict | None = None,
                         return_state: bool = False):
    """Replay bounded causal context, and emit only events from the new chunk.

    State is JSON serializable. It includes recent inputs needed for rolling
    conditions, cooldown replay, pending zones, and confirmed swing patterns.
    """
    state=state or {}
    if bars.empty or features.empty:
        return ([], state, []) if return_state else []
    start=pd.to_datetime(bars.ts,utc=True).min()
    old_bars=_frame(state.get('context_bars',[]))
    old_features=_frame(state.get('context_features',[]))
    b=pd.concat([old_bars,bars],ignore_index=True).drop_duplicates('ts',keep='last').sort_values('ts').reset_index(drop=True)
    f=pd.concat([old_features,features],ignore_index=True).drop_duplicates('ts',keep='last').sort_values('ts').reset_index(drop=True)
    events=detect_rule(name,f,levels,b,cut_ts=start,
                       initial_last_emit=state.get('cooldowns',{}))
    days=SESSION_RULES.get(name,2)
    end=pd.to_datetime(b.ts,utc=True).max()
    # Calendar-day retention handles weekend gaps without retaining stale
    # future context; 100 days covers 61 index trading sessions.
    cutoff=end-pd.Timedelta(days=days)
    b=b[pd.to_datetime(b.ts,utc=True)>=cutoff]
    f=f[pd.to_datetime(f.ts,utc=True)>=cutoff]
    chosen=SESSION_FEATURES.get(name,FEATURES)
    f=f[[key for key in chosen if key in f]]
    b=b[[key for key in BARS if key in b]]
    # Explicit state keys make the checkpoint inspectable. Replay of the
    # bounded context restores pending zones, pattern pivots and cooldowns.
    cooldowns=dict(state.get('cooldowns',{}))
    for e in events:
        key='' if name=='post_macro_event_reaction' else str(e.get('variant',''))
        cooldowns[key]=pd.Timestamp(e['known_at']).isoformat()
    state_out={'context_bars':_records(b), 'context_features':_records(f),
               'cooldowns':cooldowns,
               'last_swing_high':float(f['1h_swing_high'].dropna().iloc[-1]) if '1h_swing_high' in f and f['1h_swing_high'].notna().any() else None,
               'last_swing_low':float(f['1h_swing_low'].dropna().iloc[-1]) if '1h_swing_low' in f and f['1h_swing_low'].notna().any() else None,
               'pending_context_bars':min(len(b),60)}
    # Fail in tests if any checkpoint value ceases to be JSON compatible.
    json.dumps(state_out,allow_nan=False)
    return (events,state_out,[]) if return_state else events
