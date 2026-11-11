"""Causal, single-pass rules shared by the frozen tournament detectors."""
from __future__ import annotations

import numpy as np
import pandas as pd


def detect_rule(name: str, features: pd.DataFrame, levels: pd.DataFrame, bars: pd.DataFrame, *,
                cut_ts=None, initial_last_emit: dict | None = None) -> list[dict]:
    if features.empty or bars.empty:
        return []
    b = bars.sort_values('ts').reset_index(drop=True)
    f = features.drop_duplicates('ts', keep='last').set_index('ts').reindex(b.ts).reset_index(drop=True)
    n = len(b)
    c = b.bid_c.to_numpy(float)
    o = b.bid_o.to_numpy(float)
    h = b.bid_h.to_numpy(float)
    l = b.bid_l.to_numpy(float)
    ts = pd.to_datetime(b.ts, utc=True)
    known = pd.to_datetime(f.known_at, utc=True) if 'known_at' in f else ts + pd.Timedelta(minutes=1)
    # A missing feature row can never authorize a signal.
    valid = known.notna().to_numpy() & (known.to_numpy() >= (ts + pd.Timedelta(minutes=1)).to_numpy())
    def col(key):
        return pd.to_numeric(f[key], errors='coerce').to_numpy(float) if key in f else np.full(n, np.nan)
    atr = col('1h_atr14')
    atr = np.where(np.isfinite(atr) & (atr > 0), atr, col('1m_atr14'))
    atr = np.where(np.isfinite(atr) & (atr > 0), atr, np.nan)
    def prev(a, k=1):
        out = np.full(len(a), np.nan)
        if len(a) > k:
            out[k:] = a[:-k]
        return out
    def cross(a, threshold=0):
        return (a > threshold) & (prev(a) <= threshold)
    def fall(a, threshold=0):
        return (a < threshold) & (prev(a) >= threshold)
    side = np.zeros(n, dtype=np.int8)
    sl = np.full(n, np.nan)
    tp = np.full(n, np.nan)
    limit = np.full(n, np.nan)
    attrs: dict[str, np.ndarray] = {}
    # Active level matches are resolved at each bar close; future levels cannot enter.
    level_rules = {
        'round_number_reaction': {'round_number'},
        'session_level_reaction': {'prior_day_high','prior_day_low','prior_week_high','prior_week_low','overnight_high','overnight_low','opening_range_high_15m','opening_range_low_15m'},
        'supply_demand_zone_retest': {'supply_zone_edge','demand_zone_edge'},
        'candlestick_at_level': {'swing_high','swing_low','prior_day_high','prior_day_low','round_number','supply_zone_edge','demand_zone_edge'},
        'volume_profile_poc_vah_val': {'prior_day_poc','prior_day_vah','prior_day_val'},
    }
    if name in level_rules:
        if levels is None or levels.empty or not {'price','type','known_at'}.issubset(levels):
            return []
        lv = levels[levels.type.isin(level_rules[name])].copy()
        if lv.empty: return []
        lv['known_at'] = pd.to_datetime(lv.known_at, utc=True)
        lv['invalidated_at'] = pd.to_datetime(lv.invalidated_at, utc=True) if 'invalidated_at' in lv else pd.NaT
        lv = lv.sort_values('price')
        lp=lv.price.to_numpy(float)
        lk=lv.known_at.map(lambda x:x.value).to_numpy()
        li=lv.invalidated_at.map(lambda x:x.value if pd.notna(x) else np.iinfo(np.int64).max).to_numpy()
        lt=lv.type.astype(str).to_numpy()
        types=[]; prices=[]
        for i in range(n):
            if not valid[i] or not np.isfinite(atr[i]):
                types.append(None); prices.append(np.nan); continue
            a=np.searchsorted(lp,l[i]-.15*atr[i],side='left')
            z=np.searchsorted(lp,h[i]+.15*atr[i],side='right')
            now=known.iloc[i].value
            eligible=np.flatnonzero((lk[a:z]<=now)&(li[a:z]>now)&np.isfinite(lp[a:z]))+a
            if len(eligible):
                j=eligible[np.argmin(np.abs(lp[eligible]-c[i]))]
                types.append(lt[j]); prices.append(float(lp[j]))
            else:
                types.append(None); prices.append(np.nan)
        p = np.asarray(prices)
        touch = np.isfinite(p)
        bullish = (c > o) & (l < np.minimum(o,c) - .3*atr)
        bearish = (c < o) & (h > np.maximum(o,c) + .3*atr)
        if name == 'candlestick_at_level':
            side[touch & bullish] = 1; side[touch & bearish] = -1
        else:
            side[touch & (c > p)] = 1; side[touch & (c < p)] = -1
        if name in {'supply_demand_zone_retest','order_block_retest','fvg_retrace'}:
            # Place the order at the known zone edge and expire after 4 bars.
            limit[touch] = p[touch]
        sl = np.where(side > 0, np.minimum(l,p)-.2*atr, np.maximum(h,p)+.2*atr)
        tp = np.where(side > 0, c+2*np.abs(c-sl), c-2*np.abs(c-sl))
        attrs['level_type'] = np.asarray(types, dtype=object)
        attrs['level_price'] = p
    elif name in {'order_block_retest','fvg_retrace'}:
        hi = col('1h_swing_high'); lo = col('1h_swing_low')
        if not np.isfinite(hi).any(): hi = col('15m_swing_high')
        if not np.isfinite(lo).any(): lo = col('15m_swing_low')
        zone_side = 0; edge = np.nan; far = np.nan; formed_at = -1
        for i in range(3,n):
            if not valid[i] or not np.isfinite(atr[i]): continue
            # A gap is first known at bar i-1 close; a block is known only
            # when bar i-1 breaks a previously confirmed structure level.
            if name == 'fvg_retrace':
                if l[i-1] > h[i-3] and l[i-1]-h[i-3] >= .1*atr[i-1]:
                    zone_side=1; edge=float(l[i-1]); far=float(h[i-3]); formed_at=i-1
                elif h[i-1] < l[i-3] and l[i-3]-h[i-1] >= .1*atr[i-1]:
                    zone_side=-1; edge=float(h[i-1]); far=float(l[i-3]); formed_at=i-1
            else:
                if np.isfinite(hi[i-2]) and c[i-1]>hi[i-2] and c[i-2]<=hi[i-2] and c[i-2]<o[i-2]:
                    zone_side=1; edge=float(h[i-2]); far=float(l[i-2]); formed_at=i-1
                elif np.isfinite(lo[i-2]) and c[i-1]<lo[i-2] and c[i-2]>=lo[i-2] and c[i-2]>o[i-2]:
                    zone_side=-1; edge=float(l[i-2]); far=float(h[i-2]); formed_at=i-1
            if zone_side and i>formed_at and i-formed_at<=60 and l[i]<=edge<=h[i]:
                side[i]=zone_side; limit[i]=edge
                sl[i]=far-.2*atr[i] if zone_side>0 else far+.2*atr[i]
                tp[i]=edge+zone_side*2*abs(edge-sl[i])
                zone_side=0
        attrs['zone_edge']=limit.copy()
    elif name in {'trendline_channel','chart_patterns'}:
        if levels is None or levels.empty or not {'price','type','known_at','created_at','timeframe'}.issubset(levels): return []
        piv=levels[levels.type.isin(['swing_high','swing_low']) & levels.timeframe.isin(['15m','1h','4h'])].copy()
        if piv.empty: return []
        piv['known_at']=pd.to_datetime(piv.known_at,utc=True)
        piv['created_at']=pd.to_datetime(piv.created_at,utc=True)
        piv=piv.sort_values('known_at')
        rows=list(piv.itertuples(index=False)); j=0; seq=[]; highs=[]; lows=[]
        pattern_attr=np.full(n,'',dtype=object); line_slope=np.full(n,np.nan)
        for i in range(n):
            if not valid[i] or not np.isfinite(atr[i]): continue
            now=known.iloc[i]
            while j<len(rows) and rows[j].known_at<=now:
                x=rows[j]; j+=1
                (highs if x.type=='swing_high' else lows).append(x)
                if seq and seq[-1].type==x.type:
                    if (x.type=='swing_high' and x.price>seq[-1].price) or (x.type=='swing_low' and x.price<seq[-1].price): seq[-1]=x
                else: seq.append(x)
            if name=='trendline_channel':
                for direction,kind in ((1,'swing_low'),(-1,'swing_high')):
                    points=lows if kind=='swing_low' else highs
                    if len(points)<2: continue
                    a,z=points[-2:]
                    elapsed=(z.created_at-a.created_at).total_seconds()/60
                    if elapsed<=0: continue
                    slope=(z.price-a.price)/elapsed
                    if direction*slope<=0: continue
                    projected=z.price+slope*(now-z.created_at).total_seconds()/60
                    if direction>0 and l[i]<=projected+.2*atr[i] and c[i]>projected+.2*atr[i]:
                        side[i]=1; sl[i]=min(l[i],projected)-.2*atr[i]
                    elif direction<0 and h[i]>=projected-.2*atr[i] and c[i]<projected-.2*atr[i]:
                        side[i]=-1; sl[i]=max(h[i],projected)+.2*atr[i]
                    if side[i]:
                        tp[i]=c[i]+side[i]*2*abs(c[i]-sl[i]); line_slope[i]=slope; break
            else:
                # Pattern exists only after its last pivot is confirmed.
                if len(seq)<3: continue
                q=seq[-5:]
                pattern=None; neckline=np.nan; extreme=np.nan
                if len(q)>=5 and [x.type for x in q[-5:]]==['swing_high','swing_low','swing_high','swing_low','swing_high']:
                    a,b1,head,b2,z=q[-5:]
                    if head.price>max(a.price,z.price)+.3*atr[i] and abs(a.price-z.price)<=.5*atr[i]:
                        pattern='head_shoulders'; neckline=(b1.price+b2.price)/2; extreme=head.price
                if pattern is None and [x.type for x in q[-3:]]==['swing_high','swing_low','swing_high']:
                    a,b1,z=q[-3:]
                    if abs(a.price-z.price)<=.3*atr[i]: pattern='double_top'; neckline=b1.price; extreme=max(a.price,z.price)
                if pattern and c[i]<neckline and (i==0 or c[i-1]>=neckline):
                    side[i]=-1; sl[i]=extreme+.2*atr[i]; tp[i]=c[i]-2*abs(c[i]-sl[i]); pattern_attr[i]=pattern
                pattern=None
                if len(q)>=5 and [x.type for x in q[-5:]]==['swing_low','swing_high','swing_low','swing_high','swing_low']:
                    a,b1,head,b2,z=q[-5:]
                    if head.price<min(a.price,z.price)-.3*atr[i] and abs(a.price-z.price)<=.5*atr[i]:
                        pattern='inverse_head_shoulders'; neckline=(b1.price+b2.price)/2; extreme=head.price
                if pattern is None and [x.type for x in q[-3:]]==['swing_low','swing_high','swing_low']:
                    a,b1,z=q[-3:]
                    if abs(a.price-z.price)<=.3*atr[i]: pattern='double_bottom'; neckline=b1.price; extreme=min(a.price,z.price)
                if pattern and c[i]>neckline and (i==0 or c[i-1]<=neckline):
                    side[i]=1; sl[i]=extreme-.2*atr[i]; tp[i]=c[i]+2*abs(c[i]-sl[i]); pattern_attr[i]=pattern
        # The pivot table is filtered by known_at; no pivot is backdated.
        if name=='chart_patterns': attrs['pattern']=pattern_attr
        else: attrs['line_slope_per_minute']=line_slope
    elif name in {'market_structure_pullback','fib_pullback','ote_zone','price_action_h2l2','wyckoff_spring_upthrust'}:
        hi = col('1h_swing_high'); lo = col('1h_swing_low')
        if not np.isfinite(hi).any(): hi = col('15m_swing_high')
        if not np.isfinite(lo).any(): lo = col('15m_swing_low')
        trend = col('1h_ema50_200_gap_atr')
        if not np.isfinite(trend).any(): trend = col('15m_ema50_200_gap_atr')
        rng = hi-lo
        depth = (hi-c)/rng
        depth_down = (c-lo)/rng
        if name == 'market_structure_pullback':
            if levels is None or levels.empty or not {'type','price','known_at','timeframe'}.issubset(levels): return []
            state={}
            for kind in ('swing_high','swing_low'):
                pv=levels[(levels.type==kind)&levels.timeframe.isin(['15m','1h','4h'])].copy()
                pv['known_at']=pd.to_datetime(pv.known_at,utc=True)
                pv=pv.sort_values('known_at')
                pv['direction']=np.sign(pv.price.diff())
                if pv.empty: state[kind]=np.full(n,np.nan); continue
                aligned=pd.merge_asof(pd.DataFrame({'known_at':known.fillna(ts+pd.Timedelta(minutes=1))}).sort_values('known_at'),
                    pv[['known_at','direction']].sort_values('known_at'),on='known_at',direction='backward')
                state[kind]=aligned.direction.to_numpy(float)
            hh=state['swing_high']; hl=state['swing_low']
            side[(hh>0)&(hl>0)&(l<=hi)&(c>hi)&(prev(c)>hi)] = 1
            side[(hh<0)&(hl<0)&(h>=lo)&(c<lo)&(prev(c)<lo)] = -1
            attrs['higher_high_state']=hh; attrs['higher_low_state']=hl
        elif name == 'trendline_channel':
            side[(trend > 0) & (l <= lo+.2*atr) & (c > lo+.2*atr)] = 1
            side[(trend < 0) & (h >= hi-.2*atr) & (c < hi-.2*atr)] = -1
        elif name == 'chart_patterns':
            # Two visits to an extreme, separated by a neckline at the opposite pivot.
            second_top = (prev(h,2) >= hi-.2*atr) & (prev(l) <= lo+.5*atr)
            second_bottom = (prev(l,2) <= lo+.2*atr) & (prev(h) >= hi-.5*atr)
            side[second_top & fall(c-lo)] = -1
            side[second_bottom & cross(c-hi)] = 1
        elif name in {'fib_pullback','ote_zone'}:
            lower_depth,upper_depth = (.40,.60) if name == 'fib_pullback' else (.62,.79)
            side[(trend > 0) & (depth >= lower_depth) & (depth <= upper_depth) & (prev(depth) < lower_depth)] = 1
            side[(trend < 0) & (depth_down >= lower_depth) & (depth_down <= upper_depth) & (prev(depth_down) < lower_depth)] = -1
            if name == 'ote_zone':
                limit = np.where(side > 0, hi-lower_depth*rng, np.where(side < 0, lo+lower_depth*rng, np.nan))
            attrs['retracement_depth'] = np.where(side > 0, depth, depth_down)
        elif name == 'price_action_h2l2':
            side[(trend > 0) & (prev(c,3)>prev(c,2)) & (prev(c,2)<prev(c)) & (prev(c)>prev(c,2)) & (c>prev(h))] = 1
            side[(trend < 0) & (prev(c,3)<prev(c,2)) & (prev(c,2)>prev(c)) & (prev(c)<prev(c,2)) & (c<prev(l))] = -1
        else:
            side[(l < lo-.1*atr) & (c > lo)] = 1
            side[(h > hi+.1*atr) & (c < hi)] = -1
        sl = np.where(side > 0, np.minimum(lo,l)-.2*atr, np.maximum(hi,h)+.2*atr)
        tp = np.where(side > 0, np.maximum(hi,c+2*np.abs(c-sl)), np.minimum(lo,c-2*np.abs(c-sl)))
        attrs['confirmed_swing_high'] = hi; attrs['confirmed_swing_low'] = lo
    elif name in {'ma_cross','macd_signal','stochastic','bollinger','vwap_reclaim_reject','donchian_atr_breakout','ichimoku_cloud','dow_trend_confirmation','trend_following','intraday_momentum','range_breakout_nr4_nr7','btc_order_flow','vix_spike_dip_buy','funding_extreme_fade','post_macro_event_reaction','post_earnings_index_reaction'}:
        if name == 'ma_cross':
            gap = col('1h_ema20_50_gap_atr'); slow = col('1h_ema50_200_gap_atr')
            side[cross(gap) | cross(slow)] = 1; side[fall(gap) | fall(slow)] = -1
            attrs['fast_gap_atr'] = gap; attrs['slow_gap_atr'] = slow
        elif name == 'macd_signal':
            x = col('1h_macd_hist_atr'); side[cross(x)] = 1; side[fall(x)] = -1
        elif name == 'stochastic':
            k=col('1h_stoch_k14'); d=col('1h_stoch_d3')
            side[cross(k-d) & (k<25)] = 1; side[fall(k-d) & (k>75)] = -1
        elif name == 'bollinger':
            pct=col('1h_bollinger_pctb20'); width=col('1h_bollinger_width20')
            side[cross(pct) & (prev(pct)<0)] = 1; side[fall(pct-1) & (prev(pct)>1)] = -1
            squeeze=width < pd.Series(width).rolling(100,min_periods=100).quantile(.2).to_numpy()
            side[squeeze & cross(pct-1)] = 1; side[squeeze & fall(pct)] = -1
            attrs['variant'] = np.where(squeeze,'squeeze_breakout','band_reversion')
        elif name == 'vwap_reclaim_reject':
            x=col('vwap_distance_atr'); side[cross(x)] = 1; side[fall(x)] = -1
        elif name == 'donchian_atr_breakout':
            x=col('1h_donchian20_position'); side[cross(x-.99)] = 1; side[fall(x-.01)] = -1
        elif name == 'ichimoku_cloud':
            # Tenkan/Kijun proxy from causal rolling 9/26 high-low midpoints.
            a=(pd.Series(h).rolling(9,min_periods=9).max()+pd.Series(l).rolling(9,min_periods=9).min()).to_numpy()/2
            b26=(pd.Series(h).rolling(26,min_periods=26).max()+pd.Series(l).rolling(26,min_periods=26).min()).to_numpy()/2
            side[cross(a-b26) & (c>b26)] = 1; side[fall(a-b26) & (c<b26)] = -1
        elif name == 'dow_trend_confirmation':
            a=col('1h_ema50_200_gap_atr'); d=col('1d_ema50_200_gap_atr'); v=col('volume_z20')
            side[cross(a) & (d>0) & (v>0)] = 1; side[fall(a) & (d<0) & (v>0)] = -1
        elif name == 'trend_following':
            a=col('1d_return_bars_20'); d=col('1d_return_bars_60')
            day=f.get('1d_bar_known_at',pd.Series([pd.NaT]*n))
            changed=day.notna().to_numpy() & day.ne(day.shift()).to_numpy()
            if not (np.isfinite(a).any() and np.isfinite(d).any()):
                # Index feeds can lack completed 1d indicators. Build only from
                # completed sessions already present in this scan.
                session=col('session_id'); boundaries=np.flatnonzero(np.r_[True,session[1:]!=session[:-1]])
                completed=[]; a=np.full(n,np.nan); d=np.full(n,np.nan); changed=np.zeros(n,bool)
                for k in boundaries[1:]:
                    completed.append(c[k-1]); changed[k]=True
                    if len(completed)>60:
                        a[k]=completed[-1]/completed[-21]-1
                        d[k]=completed[-1]/completed[-61]-1
            side[changed & (a>0) & (d>0)] = 1; side[changed & (a<0) & (d<0)] = -1
            attrs['return_20d']=a; attrs['return_60d']=d
        elif name == 'intraday_momentum':
            pos=col('minutes_since_session_open'); day=col('session_id')
            first= np.r_[True,day[1:]!=day[:-1]]
            op=np.where(first,o,np.nan)
            open_series=pd.Series(op).ffill().to_numpy()
            noise=pd.Series(np.abs(c-open_series)).rolling(20,min_periods=20).mean().shift(1).to_numpy()
            x=c-open_series
            side[(x>noise) & (prev(x)<=prev(noise)) & (pos>30)] = 1
            side[(x<-noise) & (prev(x)>=-prev(noise)) & (pos>30)] = -1
            attrs['gamma_regime']=col('gex'); attrs['vol_regime']=col('vix_percentile_1y')
        elif name == 'range_breakout_nr4_nr7':
            session=col('session_id'); boundaries=np.flatnonzero(np.r_[True,session[1:]!=session[:-1]])
            narrow=np.zeros(n,bool); variant=np.full(n,'',dtype=object)
            prior_ranges=[]
            for j,k in enumerate(boundaries[1:],start=1):
                previous=slice(boundaries[j-1],k)
                r=float(np.max(h[previous])-np.min(l[previous]))
                is_nr7=len(prior_ranges)>=7 and r<min(prior_ranges[-7:])
                is_nr4=len(prior_ranges)>=4 and r<min(prior_ranges[-4:])
                end=boundaries[j+1] if j+1<len(boundaries) else n
                narrow[k:end]=is_nr7 or is_nr4
                variant[k:end]='nr7' if is_nr7 else 'nr4' if is_nr4 else ''
                prior_ranges.append(r)
            up=col('prior_day_high_distance_atr'); dn=col('prior_day_low_distance_atr')
            side[narrow & cross(up)] = 1; side[narrow & fall(dn)] = -1
            attrs['variant']=variant
        elif name == 'btc_order_flow':
            x=col('taker_buy_ratio'); z=col('volume_z20')
            side[(x>.65)&(prev(x)<=.65)&(z>1)] = 1; side[(x<.35)&(prev(x)>=.35)&(z>1)] = -1
            attrs['taker_buy_ratio']=x
        elif name == 'vix_spike_dip_buy':
            v=col('vix_percentile_1y'); ret=col('1d_return_bars_1')
            day=f.get('1d_bar_known_at',pd.Series([pd.NaT]*n)); changed=day.notna().to_numpy() & day.ne(day.shift()).to_numpy()
            if not np.isfinite(ret).any():
                session=col('session_id'); boundaries=np.flatnonzero(np.r_[True,session[1:]!=session[:-1]])
                ret=np.full(n,np.nan); changed=np.zeros(n,bool); completed=[]
                for k in boundaries[1:]:
                    completed.append(c[k-1]); changed[k]=True
                    if len(completed)>=2: ret[k]=completed[-1]/completed[-2]-1
            side[changed & (v>.9) & (ret<-.02)] = 1
            attrs['vix_percentile_1y']=v
        elif name == 'funding_extreme_fade':
            x=col('funding_z20'); side[(x>2)&(prev(x)<=2)] = -1; side[(x<-2)&(prev(x)>=-2)] = 1
            attrs['funding_z20']=x
        elif name in {'post_macro_event_reaction','post_earnings_index_reaction'}:
            key='macro_minutes_since_event' if name=='post_macro_event_reaction' else 'earnings_minutes_since_event'
            x=col(key)
            move=c-prev(c,5)
            side[(x>=5)&(prev(x)<5)&(move>.2*atr)] = 1
            side[(x>=5)&(prev(x)<5)&(move<-.2*atr)] = -1
            attrs['first_move_atr']=move/atr
        sl=np.where(side>0, np.minimum(l,c-atr)-.2*atr, np.maximum(h,c+atr)+.2*atr)
        tp=np.where(side>0,c+2*np.abs(c-sl),c-2*np.abs(c-sl))
    else:
        raise KeyError(name)
    # Explicitly limit scans to the relevant market and suppress serial duplicate bars.
    if name in {'btc_order_flow','funding_extreme_fade'} and 'sym' in b:
        allowed=b.sym.astype(str).isin(['BTCUSDT','ETHUSDT']).to_numpy(); side[~allowed]=0
    if name in {'post_earnings_index_reaction','vix_spike_dip_buy','intraday_momentum'} and 'sym' in b:
        symbols=['USATECHIDXUSD'] if name=='post_earnings_index_reaction' else ['USATECHIDXUSD','USA500IDXUSD']
        allowed=b.sym.astype(str).isin(symbols).to_numpy(); side[~allowed]=0
    events=[]
    last_key={str(k):pd.Timestamp(v) for k,v in (initial_last_emit or {}).items()}
    for i in np.flatnonzero(valid & (side!=0)):
        if cut_ts is not None and ts.iloc[i] < cut_ts: continue
        if not np.isfinite(atr[i]) or not np.isfinite(sl[i]) or not np.isfinite(tp[i]): continue
        price=float(limit[i]) if np.isfinite(limit[i]) else float(c[i])
        if side[i]*(price-sl[i])<=0 or side[i]*(tp[i]-price)<=0: continue
        key=str(attrs.get('variant',np.full(n,''))[i])
        if key in last_key and (known.iloc[i]-last_key[key])<pd.Timedelta(hours=4): continue
        last_key[key]=known.iloc[i]
        event={'ts':ts.iloc[i], 'known_at':known.iloc[i], 'sym':str(b.sym.iloc[i]) if 'sym' in b else '',
               'method':name, 'side':int(side[i]), 'price':float(c[i]), 'natural_sl':float(sl[i]),
               'natural_tp':float(tp[i]), 'entry_type':'limit' if np.isfinite(limit[i]) else 'market'}
        if np.isfinite(limit[i]):
            event['limit_price']=price; event['expiry_at']=known.iloc[i]+pd.Timedelta(minutes=4)
        for k,v in attrs.items():
            value=v[i]
            if isinstance(value,np.generic): value=value.item()
            if value is not None and (not isinstance(value,float) or np.isfinite(value)): event[k]=value
        events.append(event)
        if name=='post_macro_event_reaction':
            reverse=-event['side']
            reverse_sl=float(max(h[i],c[i]+atr[i])+.2*atr[i]) if reverse<0 else float(min(l[i],c[i]-atr[i])-.2*atr[i])
            fade={**event,'side':reverse,'natural_sl':reverse_sl,
                  'natural_tp':float(c[i]+reverse*2*abs(c[i]-reverse_sl)),
                  'variant':'fade'}
            event['variant']='follow'
            events.append(fade)
    return events
