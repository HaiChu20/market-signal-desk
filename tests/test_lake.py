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


def test_squeezemetrics_dix_parser_sets_next_ny_day_known_at():
    from msd.data.auxiliary import parse_squeezemetrics_csv
    frame=parse_squeezemetrics_csv(b"date,price,dix,gex\n2024-03-08,5100,0.42,-12.5\n")
    assert frame.iloc[0].dix==.42 and frame.iloc[0].gex==-12.5
    # Friday's after-close publication is only available from Saturday local midnight.
    assert frame.iloc[0].known_at==pd.Timestamp("2024-03-09T05:00:00Z")


def test_deribit_dvol_response_parses_hourly_close():
    from msd.data.auxiliary import parse_deribit_dvol_response
    stamp=int(pd.Timestamp("2024-01-01T00:00Z").timestamp()*1000)
    raw=(f'{{"result":{{"data":[[{stamp},50,52,49,51]]}}}}').encode()
    frame=parse_deribit_dvol_response(raw,"BTC",date(2024,1,1))
    assert frame.iloc[0].ts==pd.Timestamp("2024-01-01T00:00Z") and frame.iloc[0].close==51
    assert frame.iloc[0].known_at==pd.Timestamp("2024-01-01T01:00Z")
    assert frame.iloc[0].resolution_seconds==3600


def test_sec_submissions_parser_selects_8k_item_202():
    from msd.data.auxiliary import parse_edgar_submissions
    payload={"filings":{"recent":{"form":["8-K","8-K","10-Q"],"items":["2.02, 9.01","1.01","2.02"],
              "acceptanceDateTime":["20240102140500","20240103120000","20240104120000"],
              "filingDate":["2024-01-02","2024-01-03","2024-01-04"],
              "accessionNumber":["a","b","c"],"primaryDocument":["a.htm","b.htm","c.htm"]}}}
    frame=parse_edgar_submissions(payload,"AAPL")
    assert len(frame)==1 and frame.iloc[0].accessionNumber=="a"
    assert frame.iloc[0].datetime_utc=="20240102140500"


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


def test_crypto_cfd_scale_is_cross_checked_against_binance_within_two_percent():
    from msd.data.dukascopy import CRYPTO_SYMBOLS, _binance_daily_reference, _download_days, infer_price_scale
    day = date(2024, 6, 12)  # Wednesday
    fields = [(0, 35_438, 35_440, 35_430, 35_439, 1.0),
              (60, 35_439, 35_445, 35_435, 35_441, 1.0)]
    raw = lzma.compress(b"".join(struct.pack(">5if", *row) for row in fields))

    assert "ETHUSD" in CRYPTO_SYMBOLS
    assert infer_price_scale(raw, "ETHUSD", reference_price=3543.84) == 10
    with pytest.raises(ValueError, match="within 2%"):
        infer_price_scale(raw, "ETHUSD", reference_price=3000.0)

    assert _download_days("ETHUSD", date(2024, 6, 1), date(2024, 6, 2), date(2024, 6, 1)) == [date(2024, 6, 1), date(2024, 6, 2)]
    assert date(2024, 6, 1) not in _download_days("XAUUSD", date(2024, 6, 1), date(2024, 6, 2), date(2024, 6, 1))


def test_binance_crypto_scale_reference_uses_same_utc_day(tmp_path, monkeypatch):
    from msd.data.dukascopy import _binance_daily_reference
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "data/bars/binance_spot/ETHUSDT"
    root.mkdir(parents=True)
    frame = pd.DataFrame({
        "ts": pd.to_datetime(["2024-06-12T00:00Z", "2024-06-12T00:01Z", "2024-06-13T00:00Z"]),
        "bid_c": [3500.0, 3600.0, 9999.0],
    })
    frame.to_parquet(root / "2024-06.parquet")
    assert _binance_daily_reference("ETHUSD", date(2024, 6, 12)) == 3550.0


def test_archived_eth_cfd_scale_matches_binance_sample_when_available():
    from pathlib import Path
    from msd.data.dukascopy import _binance_daily_reference, infer_price_scale
    day=date(2018,1,1)
    raw_path=Path("data/raw/dukascopy/ETHUSD/2018-01-01_BID.bi5")
    if not raw_path.exists():
        pytest.skip("local ETHUSD calibration archive unavailable")
    raw=raw_path.read_bytes()
    reference=_binance_daily_reference("ETHUSD",day)
    assert infer_price_scale(raw,"ETHUSD",reference_price=reference)==10


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


def test_rebuild_manifest_recomputes_files_rows_completeness_and_checksums(tmp_path, monkeypatch):
    import hashlib
    import json
    import pyarrow as pa
    import pyarrow.parquet as pq
    from msd.data import catalog

    root = tmp_path / "dukascopy"
    directory = root / "TEST"
    directory.mkdir(parents=True)
    for month, stamp, complete in (
        ("2024-01", "2024-01-03T00:00:00Z", b"1"),
        ("2024-02", "2024-02-05T00:00:00Z", b"0"),
    ):
        table = pa.table({"ts": [pd.Timestamp(stamp)], "bid_c": [1.0]})
        table = table.replace_schema_metadata({b"msd_complete": complete})
        pq.write_table(table, directory / f"{month}.parquet")
    (directory / "manifest.json").write_text(json.dumps({"months": {"2013-01": {"bars": 999}}}))
    monkeypatch.setitem(catalog.SOURCE_DIRS, "dukascopy", root)

    path = catalog.rebuild_manifest("dukascopy", "TEST")
    result = json.loads(path.read_text())
    assert set(result["months"]) == {"2024-01", "2024-02"}
    assert result["months"]["2024-01"]["complete"] is True
    assert result["months"]["2024-02"]["complete"] is False
    assert all(item["bars"] == 1 and len(item["sha256"]) == 64 for item in result["months"].values())
    for month in result["months"]:
        parquet_path = directory / f"{month}.parquet"
        assert result["months"][month]["sha256"] == hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    assert result["bars"] == 2
    assert result["first_ts"] == "2024-01-03 00:00:00+00:00"


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


def test_default_index_loader_applies_start_bound_to_cash_dukas(monkeypatch):
    import numpy as np
    from msd.data import load
    from msd.data import catalog
    switch=pd.Timestamp("2018-12-16 23:00",tz="UTC")
    start=pd.Timestamp("2019-01-01",tz="UTC")
    ts=pd.DatetimeIndex([switch-pd.Timedelta(minutes=1),switch,start])
    duka=pd.DataFrame({"ts":ts,"bid_o":[1.,2.,3.],"bid_h":[1.,2.,3.],"bid_l":[1.,2.,3.],"bid_c":[1.,2.,3.],
                       "ask_o":[1.2,2.2,3.2],"ask_h":[1.2,2.2,3.2],"ask_l":[1.2,2.2,3.2],"ask_c":[1.2,2.2,3.2],"volume":[1.,1.,1.]})
    calls=[]
    def fake(symbol,lo,hi,source):
        calls.append((symbol,pd.Timestamp(lo),source))
        return duka.copy() if source=="dukascopy" else duka.iloc[0:0].copy()
    monkeypatch.setattr(catalog,"load_source",fake)
    result=load("USATECHIDXUSD",start,"2019-01-01",raw=True)
    assert result.ts.tolist()==[start]
    duka_call=next(call for call in calls if call[2]=="dukascopy")
    assert duka_call[1]==start


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
