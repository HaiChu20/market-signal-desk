"""One source-aware loader interface for local market data."""
from pathlib import Path
import pandas as pd


def _utc(value):
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _load_index_primary(symbol, start, end):
    from .histdata import DUKASCOPY_SYMBOL, HISTDATA_SWITCH_UTC
    hist_symbol = {"USATECHIDXUSD":"NSXUSD", "USA500IDXUSD":"SPXUSD"}[symbol]
    switch = HISTDATA_SWITCH_UTC[symbol if symbol in HISTDATA_SWITCH_UTC else hist_symbol]
    from .catalog import load_source
    hist = load_source(hist_symbol, start, end, "histdata")
    duka_symbol = DUKASCOPY_SYMBOL[hist_symbol]
    duka_start = max(switch, _utc(start))
    duka = load_source(duka_symbol, duka_start, end, "dukascopy")
    hist = hist[pd.to_datetime(hist.ts, utc=True) < switch].copy()
    duka_ts = pd.to_datetime(duka.ts, utc=True)
    duka = duka[(duka_ts >= duka_start) & (duka_ts < _utc(end) + pd.Timedelta(days=1))].copy()
    if not hist.empty:
        hist.ts = pd.to_datetime(hist.ts, utc=True).astype("datetime64[ns, UTC]")
        for field in ("o", "h", "l", "c"):
            adj = f"adj_bid_{field}"
            if adj not in hist:
                hist[adj] = hist[f"bid_{field}"]
        # Dukascopy is supplementary cost/volume information before the
        # feed switch; primary prices remain the roll-adjusted HistData series.
        reference = load_source(duka_symbol, start, switch, "dukascopy")
        if not reference.empty:
            reference["ts"] = pd.to_datetime(reference.ts, utc=True).astype("datetime64[ns, UTC]")
            reference["duka_spread"] = reference.ask_o - reference.bid_o
            reference = reference[["ts", "duka_spread", "volume"]].rename(columns={"volume":"duka_volume"})
            hist = hist.merge(reference, on="ts", how="left", validate="one_to_one")
        else:
            hist["duka_spread"] = float("nan"); hist["duka_volume"] = float("nan")
    if not duka.empty:
        duka.ts = pd.to_datetime(duka.ts, utc=True).astype("datetime64[ns, UTC]")
        duka["feed"] = "cash_cfd"; duka["roll"] = False
        duka["duka_spread"] = duka.ask_o - duka.bid_o
        duka["duka_volume"] = duka.volume
        for field in ("o", "h", "l", "c"):
            duka[f"adj_bid_{field}"] = duka[f"bid_{field}"]
    result = pd.concat([hist, duka], ignore_index=True, sort=False)
    if result.empty:
        return result
    result.ts = pd.to_datetime(result.ts, utc=True).astype("datetime64[ns, UTC]")
    return result.sort_values("ts").reset_index(drop=True)


def load(symbol, start, end, source=None, *, raw=False):
    if source is None and symbol in {"USATECHIDXUSD", "USA500IDXUSD"}:
        result = _load_index_primary(symbol, start, end)
        if not raw and not result.empty:
            from msd.processing.pipeline import _modelled_spread, assert_executable_spread
            result = _modelled_spread(result, symbol)
            assert_executable_spread(result, symbol)
        return result
    supplement_dukas = False
    if source is None:
        if symbol == "USATECHIDXUSD":
            source = "histdata"
            source_symbol = "NSXUSD"
            supplement_dukas = True
        elif symbol == "USA500IDXUSD":
            source = "histdata"
            source_symbol = "SPXUSD"
            supplement_dukas = True
        elif symbol in {"NSXUSD", "SPXUSD", "GRXEUR", "WTIUSD"}:
            source = "histdata"
            source_symbol = symbol
        elif symbol in {"BTCUSDT", "ETHUSDT"}:
            source = "binance_spot"
            source_symbol = symbol
            if symbol == "BTCUSDT" and not Path("data/bars/binance_spot/BTCUSDT").exists() and Path("data/binance/BTCUSDT").exists():
                from .binance import load as legacy_load
                result = legacy_load(symbol, start, end, raw=raw)
                if not raw:
                    from msd.processing.pipeline import assert_executable_spread
                    assert_executable_spread(result, symbol)
                return result
        else:
            source = "dukascopy"
            source_symbol = symbol
    else:
        # Vendor aliases belong only to HistData.  Dukascopy stores its own
        # CFD epic names (e.g. USATECHIDXUSD) and must never be remapped.
        source_symbol = ({"USATECHIDXUSD": "NSXUSD", "USA500IDXUSD": "SPXUSD"}.get(symbol, symbol)
                         if source == "histdata" else symbol)
    from .catalog import load_source
    result = load_source(source_symbol, start, end, source)
    if supplement_dukas and not result.empty:
        from .dukascopy import load as load_dukas
        duka_symbol = symbol
        supplement = load_dukas(duka_symbol, start, end)
        if not supplement.empty:
            fields = {column: f"duka_{column}" for column in supplement.columns if column != "ts"}
            supplement = supplement.rename(columns=fields)
            result = result.merge(supplement, on="ts", how="left", validate="one_to_one")
            result["duka_spread"] = result["duka_ask_o"] - result["duka_bid_o"]
        else:
            for column in ("duka_bid_o", "duka_bid_h", "duka_bid_l", "duka_bid_c", "duka_ask_o", "duka_ask_h", "duka_ask_l", "duka_ask_c", "duka_volume", "duka_spread"):
                result[column] = float("nan")
    if not raw and not result.empty:
        # All research/backtest callers receive executable bid/ask bars. The
        # pipeline's modeled-spread function is also the single cost model
        # used by feature and label generation. Raw trade bars remain available
        # explicitly for source-level analyses.
        from msd.processing.pipeline import _modelled_spread, assert_executable_spread
        result = _modelled_spread(result, symbol)
        assert_executable_spread(result, symbol)
    return result
