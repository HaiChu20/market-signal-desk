from datetime import date
import csv
import io
import lzma
import struct

import pandas as pd
import pytest


def test_binance_12_column_kline_parse_ms_and_us():
    from msd.data.binance_lake import parse_kline_rows
    row = ["1718150400000", "100", "102", "99", "101", "4", "1718150459999", "404", "12", "2", "202", "0"]
    ms = parse_kline_rows([row])
    row_us = row.copy(); row_us[0] = "1735689600000000"
    us = parse_kline_rows([row_us])
    assert ms.ts.iloc[0] == pd.Timestamp("2024-06-12", tz="UTC")
    assert us.ts.iloc[0] == pd.Timestamp("2025-01-01", tz="UTC")
    assert ms.iloc[0].quote_volume == 404 and ms.iloc[0].trades == 12
    assert ms.iloc[0].taker_buy_base == 2 and ms.iloc[0].taker_buy_quote == 202
    assert ms.bid_o.iloc[0] == ms.ask_o.iloc[0] == 100


def test_binance_funding_metrics_and_cboe_parsers():
    from msd.data.binance_lake import parse_funding_csv, parse_metrics_csv
    from msd.data.auxiliary import parse_cboe_csv
    funding = parse_funding_csv(b"symbol,fundingTime,fundingRate,markPrice\nBTCUSDT,1700000000000,0.0001,36000\n")
    assert funding.iloc[0].symbol == "BTCUSDT" and funding.iloc[0].funding_rate == .0001
    metrics = parse_metrics_csv(b"create_time,symbol,sum_open_interest\n2024-01-01T00:00:00Z,BTCUSDT,100\n")
    assert metrics.iloc[0].sum_open_interest == 100
    cboe = parse_cboe_csv(b"DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2024,12,13,11,12.5\n")
    assert cboe.close.iloc[0] == 12.5


def test_binance_funding_vision_calc_time_format():
    from msd.data.binance_lake import parse_funding_csv
    frame = parse_funding_csv(b"calc_time,funding_interval_hours,last_funding_rate\n1577836800000,8,-0.00012359\n", "BTCUSDT")
    assert frame.iloc[0].symbol == "BTCUSDT"
    assert frame.iloc[0].ts == pd.Timestamp("2020-01-01T00:00:00Z")
    assert frame.iloc[0].funding_rate == -.00012359
    assert frame.iloc[0].funding_interval_hours == 8


def test_funding_uses_fundingrate_archive_name_and_logs_404(monkeypatch, capsys):
    import msd.data.auxiliary as auxiliary
    requested=[]
    monkeypatch.setattr(auxiliary,"_get",lambda url: requested.append(url) or None)
    assert auxiliary._download_funding_month("BTCUSDT",date(2023,1,1)) is None
    assert requested==["https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2023-01.zip.CHECKSUM"]
    assert "MISSING Binance funding BTCUSDT 2023-01" in capsys.readouterr().out


def test_funding_run_fails_when_all_months_are_missing(monkeypatch):
    import msd.data.auxiliary as auxiliary
    original_datetime=auxiliary.datetime
    class FrozenDateTime:
        @staticmethod
        def now(tz=None):
            return original_datetime(2019,9,1,tzinfo=tz)
    monkeypatch.setattr(auxiliary,"datetime",FrozenDateTime)
    monkeypatch.setattr(auxiliary,"_get",lambda url: None)
    monkeypatch.setattr(auxiliary,"ensure_disk_space",lambda: None)
    with pytest.raises(RuntimeError,match="every month missing or empty"):
        auxiliary.download_funding()


def test_macro_et_conversion_dst_and_scale_sanity():
    from msd.data.auxiliary import et_to_utc
    from msd.data.dukascopy import infer_price_scale
    assert et_to_utc(date(2024, 1, 15), 8, 30).hour == 13
    assert et_to_utc(date(2024, 7, 15), 8, 30).hour == 12
    raw = lzma.compress(struct.pack(">5if", 0, 2_000_000, 2_010_000, 1_990_000, 2_005_000, 1.))
    assert infer_price_scale(raw, "XAUUSD") == 1000
    bad = lzma.compress(struct.pack(">5if", 0, 999_999_999, 1_000_000_000, 900_000_000, 1_001_000_000, 1.))
    with pytest.raises(ValueError):
        infer_price_scale(bad, "XAUUSD")


def test_manifest_and_source_routing(tmp_path, monkeypatch):
    from msd.data.catalog import write_manifest
    from msd.data import load
    from msd.data import catalog
    frame = pd.DataFrame({"ts": pd.date_range("2024-01-01", periods=2, freq="min", tz="UTC"), "bid_o": [10., 11.]})
    path = write_manifest("histdata", "TEST", frame, "bid", "none", root=tmp_path)
    text = path.read_text()
    assert '"price_type": "bid"' in text and '"volume_type": "none"' in text
    calls = []
    monkeypatch.setattr(catalog, "load_source", lambda symbol, start, end, source: calls.append((symbol, source)) or frame)
    assert load("SPXUSD", "2024-01-01", "2024-01-02", raw=True).equals(frame)
    assert calls == [("SPXUSD", "histdata")]


def test_explicit_dukascopy_keeps_cfd_epic(monkeypatch):
    from msd.data import load
    from msd.data import catalog
    frame = pd.DataFrame({"ts": pd.date_range("2024-06-12", periods=1, tz="UTC"), "bid_c": [1.]})
    calls=[]
    monkeypatch.setattr(catalog, "load_source", lambda symbol, start, end, source: calls.append((symbol, source)) or frame)
    assert load("USATECHIDXUSD", "2024-06-12", "2024-06-12", source="dukascopy", raw=True).equals(frame)
    assert calls == [("USATECHIDXUSD", "dukascopy")]


def test_default_index_loader_switches_from_histdata_to_dukascopy(monkeypatch):
    import numpy as np
    from msd.data import load
    from msd.data import catalog
    switch=pd.Timestamp("2018-12-16 23:00",tz="UTC")
    hist=pd.DataFrame({"ts":[switch-pd.Timedelta(minutes=1),switch],"bid_o":[10.,20.],"bid_h":[10.,20.],
                       "bid_l":[10.,20.],"bid_c":[10.,20.],"ask_o":[10.,20.],"ask_h":[10.,20.],
                       "ask_l":[10.,20.],"ask_c":[10.,20.],"volume":[np.nan,np.nan],
                       "feed":["futures_cont","cash_cfd"],"roll":[False,False],
                       "adj_bid_o":[10.,20.],"adj_bid_h":[10.,20.],"adj_bid_l":[10.,20.],"adj_bid_c":[10.,20.]})
    duka=hist.loc[[0,1]].copy()
    for field in "ohlc": duka[f"ask_{field}"]+=.2
    duka["feed"]="cash_cfd"
    calls=[]
    def fake(symbol,start,end,source):
        calls.append((symbol,source))
        return hist.copy() if source=="histdata" else duka.copy()
    monkeypatch.setattr(catalog,"load_source",fake)
    result=load("USATECHIDXUSD","2018-12-16","2018-12-16")
    assert result.ts.tolist()==[switch-pd.Timedelta(minutes=1),switch]
    assert result.feed.tolist()==["futures_cont","cash_cfd"]
    assert calls[0]==("NSXUSD","histdata") and all(source=="dukascopy" for _,source in calls[1:])


def test_missing_requested_source_raises():
    from msd.data.catalog import load_source
    import pytest
    with pytest.raises(FileNotFoundError, match="no dukascopy data files"):
        load_source("TEST_NO_DATA", "2024-01-01", "2024-01-02", "dukascopy")


def test_parquet_loader_accepts_timezone_aware_bounds(tmp_path):
    from msd.data.catalog import _load_parquet
    root=tmp_path/"source"; directory=root/"BTCUSDT"; directory.mkdir(parents=True)
    frame=pd.DataFrame({"ts":pd.date_range("2024-01-01",periods=2,freq="min",tz="UTC"),"bid_o":[10.,11.]})
    frame.to_parquet(directory/"2024-01.parquet")
    result=_load_parquet("BTCUSDT",pd.Timestamp("2024-01-01",tz="UTC"),pd.Timestamp("2024-01-01",tz="UTC"),root)
    assert len(result)==2


def test_roll_gap_estimator_holds_day_minus_one_and_plus_one_out():
    from msd.data.histdata import _full_day_roll_measure
    days=pd.bdate_range("2024-01-01",periods=12).date
    offsets=pd.Series([4.,4.,4.,4.,4.,4.,3.,99.,1.,1.,1.,1.],index=days)
    measured=_full_day_roll_measure(offsets,days[7],days[6])
    assert measured["gap_1day"] == -3.0
    assert measured["gap_2day"] == -3.0
    assert measured["uncertainty"] == 0.0
    assert measured["estimate_before_days"] == list(days[3:5])
    assert measured["estimate_after_days"] == list(days[9:11])
    assert measured["validation_before_day"] == days[5]
    assert measured["validation_after_day"] == days[8]
    assert measured["validation_residual"] == 0.0


def test_roll_classifier_accepts_zero_gap_and_requires_post_soq_stale_evidence():
    from msd.data.histdata import _classify_roll
    expiry=date(2016,12,16)
    record={"switch_ts":pd.Timestamp("2016-12-15 21:30Z"),"gap_minutes":15,
            "gap":-.32,"uncertainty":.43,"validation_residual":.85,"stale_detected":False}
    assert _classify_roll(record,expiry)=="measured"
    record["uncertainty"]=1.01
    assert _classify_roll(record,expiry)=="unmeasured_uncertainty"
    record.update(switch_ts=pd.Timestamp("2016-12-16 15:00Z"),uncertainty=.2)
    assert _classify_roll(record,expiry)=="unmeasured_stale_unconfirmed"
    record["stale_detected"]=True
    assert _classify_roll(record,expiry)=="measured"
