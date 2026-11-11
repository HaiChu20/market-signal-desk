"""Declared inputs for the frozen detector rules."""
from __future__ import annotations

COMMON = {'1m_atr14', '1h_atr14'}
RULES = {
    'rsi2_mean_reversion': {'1d_rsi2','1d_ema200_distance_atr'},
    'ma_cross': {'1h_ema20_50_gap_atr','1h_ema50_200_gap_atr'},
    'macd_signal': {'1h_macd_hist_atr'},
    'stochastic': {'1h_stoch_k14','1h_stoch_d3'},
    'bollinger': {'1h_bollinger_pctb20','1h_bollinger_width20'},
    'vwap_reclaim_reject': {'vwap_distance_atr'},
    'donchian_atr_breakout': {'1h_donchian20_position'},
    'dow_trend_confirmation': {'1h_ema50_200_gap_atr','1d_ema50_200_gap_atr','volume_z20'},
    'trend_following': {'1d_return_bars_20','1d_return_bars_60','session_id'},
    'intraday_momentum': {'minutes_since_session_open','session_id','gex','vix_percentile_1y'},
    'range_breakout_nr4_nr7': {'session_id','prior_day_high_distance_atr','prior_day_low_distance_atr'},
    'btc_order_flow': {'taker_buy_ratio','volume_z20'},
    'vix_spike_dip_buy': {'vix_percentile_1y','1d_return_bars_1','session_id'},
    'funding_extreme_fade': {'funding_z20'},
    'post_macro_event_reaction': {'macro_minutes_since_event'},
    'post_earnings_index_reaction': {'earnings_minutes_since_event'},
}
SWING = {'1h_swing_high','1h_swing_low','15m_swing_high','15m_swing_low',
         '1h_ema50_200_gap_atr','15m_ema50_200_gap_atr'}
for name in ('order_block_retest','fvg_retrace','market_structure_pullback','fib_pullback',
             'ote_zone','price_action_h2l2','wyckoff_spring_upthrust'):
    RULES[name] = SWING
MARKET = {'btc_order_flow':'crypto','funding_extreme_fade':'crypto',
          'intraday_momentum':'indices','vix_spike_dip_buy':'indices',
          'post_earnings_index_reaction':'indices','rsi2_mean_reversion':'indices'}

def required_features(name: str) -> tuple[str, ...]:
    return tuple(sorted(COMMON | RULES.get(name,set())))

def market_for(name: str) -> str:
    return MARKET.get(name,'all')
