from datetime import date
import lzma
import struct
import numpy as np
import pandas as pd
import pytest
from msd.backtest import simulate
from msd.data.dukascopy import decode
from msd.data.quality import analyze, write_report


def bars(rows):
    ts = pd.date_range("2024-06-12 10:00", periods=len(rows), freq="min", tz="UTC")
    return pd.DataFrame([dict(ts=t, bid_o=o, bid_h=h, bid_l=l, bid_c=c, ask_o=o+1, ask_h=h+1, ask_l=l+1, ask_c=c+1, volume=1.) for t,(o,h,l,c) in zip(ts, rows)])


def order(b, **kw):
    return dict(decision_ts=b.ts.iloc[0], side=1, stop=99., exit_ts=b.ts.iloc[-1]+pd.Timedelta(minutes=1), **kw)


def test_decode_bi5_field_order_and_zero_volume():
    raw = lzma.compress(struct.pack(">5if",0,5375939,5376000,5375000,5377000,1.) + struct.pack(">5if",60,0,0,0,0,0.))
    frame = decode(raw, "USA500IDXUSD", date(2024,6,12), "BID")
    assert len(frame) == 1
    assert frame.iloc[0][["bid_o","bid_h","bid_l","bid_c"]].tolist() == [5375.939,5377.,5375.,5376.]


def test_decode_implausible_day_exposes_scaled_raw_range_for_quarantine():
    from msd.data.dukascopy import PlausibilityError
    raw=lzma.compress(struct.pack(">5if",0,11000000,11000000,10999000,11001000,1.))
    try:
        decode(raw,"XAUUSD",date(2003,5,8),"BID")
    except PlausibilityError as exc:
        assert exc.raw_min>10000 and exc.raw_max>10000 and exc.side=="BID"
    else:
        raise AssertionError("implausible gold day was accepted")


def test_full_history_plausibility_bands_include_negative_wti_and_old_silver(monkeypatch):
    from msd.data import dukascopy
    assert dukascopy.PRICE_BANDS["XAUUSD"]==(200,10000)
    assert dukascopy.PRICE_BANDS["XAGUSD"]==(3,200)
    assert dukascopy.PRICE_BANDS["LIGHTCMDUSD"]==(-60,300)
    assert dukascopy.PRICE_BANDS["BRENTCMDUSD"]==(10,300)
    assert dukascopy.PRICE_BANDS["USDJPY"]==(50,300)
    assert dukascopy.PRICE_BANDS["EURUSD"]==dukascopy.PRICE_BANDS["GBPUSD"]==(0.5,3.0)
    monkeypatch.setitem(dukascopy.SCALES,"LIGHTCMDUSD",1000)
    monkeypatch.setitem(dukascopy.RANGES,"LIGHTCMDUSD",(-60,300))
    raw=lzma.compress(struct.pack(">5if",0,-40000,-39000,-41000,-38000,1.))
    parsed=decode(raw,"LIGHTCMDUSD",date(2020,4,20),"BID")
    assert parsed.bid_l.iloc[0]==-41.


def test_simulator_spread_gap_sl_first_tp_time_and_path():
    frame = bars([(100,101,100,100),(100,101,100,100),(98,105,97,104),(100,101,100,100)])
    assert simulate(frame,[order(frame,tp=104)]).iloc[0].exit_reason == "stop"
    assert simulate(frame,[order(frame,tp=110)]).iloc[0].exit_price == 98
    take = bars([(100,101,100,100),(100,105,100,104),(100,101,100,100)])
    assert simulate(take,[order(take,tp=103)]).iloc[0].exit_reason == "tp"
    timed = bars([(100,101,100,100),(100,101,100,100)])
    trade=simulate(timed,[order(timed)]).iloc[0]
    assert trade.exit_reason == "time" and trade.spread_paid == 1
    pathbars=bars([(100,101,100,100),(100,101,99.5,100),(100,101,99,100)])
    path={pathbars.ts.iloc[1]:102.}
    assert simulate(pathbars,[order(pathbars,stop_path=path)]).iloc[0].exit_reason == "stop"


def test_quality_handles_empty_and_reports_full_day_metrics(tmp_path, monkeypatch):
    assert analyze(pd.DataFrame()).empty
    ts=pd.date_range("2024-06-10", periods=5*1440, freq="min", tz="UTC")
    frame=pd.DataFrame({"ts":ts,"bid_o":100.,"ask_o":100.1,"volume":1.})
    quality=analyze(frame)
    assert {"median_full_day_bars","missing_in_hours","longest_in_hours_gap"}.issubset(quality)
    assert quality.median_full_day_bars.notna().any() and quality.missing_in_hours.notna().any()
    assert "typical_weekday_gap_windows" in quality.columns
    monkeypatch.chdir(tmp_path)
    report=write_report("TEST",frame)
    assert "Missing in-hours" in report and "Median cash bars" in report


def test_dukascopy_persistent_connection_reuse_and_retry(monkeypatch):
    from msd.data import dukascopy
    payload=lzma.compress(struct.pack(">5if",0,5375939,5376000,5375000,5377000,1.))
    state={"conn":None,"fail":False}; made=[]
    class Response:
        status=200
        def read(self):return payload
    class Connection:
        def request(self,*_args,**_kwargs):
            if state["fail"]:
                state["fail"]=False
                raise TimeoutError("retry")
        def getresponse(self):return Response()
        def close(self):pass
    def connection():
        if state["conn"] is None: state["conn"]=Connection(); made.append(state["conn"])
        return state["conn"]
    def disconnect():state["conn"]=None
    monkeypatch.setattr(dukascopy,"_connection",connection)
    monkeypatch.setattr(dukascopy,"_disconnect",disconnect)
    monkeypatch.setattr(dukascopy.time,"sleep",lambda _seconds:None)
    for day in (date(2024,6,12),date(2024,6,13)):
        assert len(dukascopy.fetch("USA500IDXUSD",day,"BID"))==1
    assert len(made)==1
    state["fail"]=True
    assert len(dukascopy.fetch("USA500IDXUSD",date(2024,6,14),"BID",retries=2))==1
    assert len(made)==2


def test_dukascopy_drops_connection_after_cannot_send_request(monkeypatch):
    from msd.data import dukascopy
    from http.client import CannotSendRequest
    payload=lzma.compress(struct.pack(">5if",0,67000,67100,66900,67050,1.))
    made=[]
    class Response:
        status=200
        def read(self):return payload
    class Connection:
        def __init__(self):
            self.index=len(made);self.closed=False;made.append(self)
        def request(self,*_args,**_kwargs):
            if self.index==0:raise CannotSendRequest("Request-sent")
        def getresponse(self):return Response()
        def close(self):self.closed=True
    dukascopy._disconnect()
    monkeypatch.setattr(dukascopy.http.client,"HTTPSConnection",lambda *_args,**_kwargs:Connection())
    monkeypatch.setattr(dukascopy.time,"sleep",lambda _seconds:None)
    try:
        frame=dukascopy.fetch("BTCUSD",date(2024,1,1),"BID",retries=2)
        assert len(frame)==1 and len(made)==2 and made[0].closed
    finally:
        dukascopy._disconnect()


def test_dukascopy_retries_http_503_then_succeeds(monkeypatch):
    from msd.data import dukascopy
    payload=lzma.compress(struct.pack(">5if",0,5375939,5376000,5375000,5377000,1.))
    made=[]
    class Response:
        def __init__(self,status): self.status=status
        def read(self): return payload if self.status==200 else b"overloaded"
    class Connection:
        def __init__(self): self.index=len(made);self.closed=False;made.append(self)
        def request(self,*_args,**_kwargs): pass
        def getresponse(self): return Response(503 if self.index==0 else 200)
        def close(self): self.closed=True
    before=dukascopy._HTTP_503_COUNTS["USA500IDXUSD"]
    dukascopy._disconnect()
    monkeypatch.setattr(dukascopy.http.client,"HTTPSConnection",lambda *_args,**_kwargs:Connection())
    monkeypatch.setattr(dukascopy.time,"sleep",lambda _seconds:None)
    try:
        frame=dukascopy.fetch("USA500IDXUSD",date(2024,6,12),"BID",retries=1)
        assert len(frame)==1 and len(made)==2 and made[0].closed
        assert dukascopy._HTTP_503_COUNTS["USA500IDXUSD"]==before+1
    finally:
        dukascopy._disconnect()


def test_dukascopy_transport_day_failure_does_not_skip_later_days(tmp_path,monkeypatch):
    from msd.data import dukascopy
    import pyarrow.parquet as pq
    monkeypatch.chdir(tmp_path)
    root=tmp_path/"bars"
    calls=[]
    stamp=pd.Timestamp("2024-06-13",tz="UTC")
    good=pd.DataFrame({"ts":[stamp],"bid_o":[100.],"bid_h":[101.],"bid_l":[99.],"bid_c":[100.],
        "ask_o":[100.1],"ask_h":[101.1],"ask_l":[99.1],"ask_c":[100.1],"volume":[1.],"bad_tick":[False]})
    def fetch_day(_symbol,day,raw_root=None):
        calls.append(day)
        if day==date(2024,6,12) and calls.count(day)==1:
            raise dukascopy.DailyFetchError("USA500IDXUSD",day,"BID",ConnectionResetError("reset"))
        result=good.copy()
        result["ts"]=pd.to_datetime([day],utc=True)
        return result
    monkeypatch.setattr(dukascopy,"fetch_day",fetch_day)
    monkeypatch.setattr("msd.data.catalog.write_manifest",lambda *_args,**_kwargs:None)
    dukascopy.download("USA500IDXUSD",date(2024,6,12),date(2024,6,13),root=root,workers=1)
    assert calls[0:2]==[date(2024,6,12),date(2024,6,13)]
    assert calls.count(date(2024,6,12))==2 # final missing-day pass
    missing=pd.read_csv("data/logs/missing_USA500IDXUSD.csv")
    assert missing.empty
    assert pq.read_metadata(root/"USA500IDXUSD/2024-06.parquet").num_rows==2


def test_dukascopy_unresolved_missing_day_marks_existing_month_incomplete(tmp_path,monkeypatch):
    from msd.data import dukascopy
    import pyarrow.parquet as pq
    monkeypatch.chdir(tmp_path)
    root=tmp_path/"bars"
    path=root/"XAUUSD/2024-06.parquet"
    frame=pd.DataFrame({"ts":pd.to_datetime(["2024-06-12"],utc=True),"bid_o":[2300.],"bid_h":[2301.],
        "bid_l":[2299.],"bid_c":[2300.],"ask_o":[2301.],"ask_h":[2302.],"ask_l":[2300.],"ask_c":[2301.],
        "volume":[1.],"bad_tick":[False]})
    dukascopy._atomic_month(frame,path,True)
    dukascopy._write_missing("XAUUSD",[{"date":"2024-06-12","side":"BID","error":"TimeoutError"}])
    monkeypatch.setattr(dukascopy,"fetch_day",lambda *_args,**_kwargs: (_ for _ in ()).throw(
        dukascopy.DailyFetchError("XAUUSD",date(2024,6,12),"BID",TimeoutError("still down"))))
    assert dukascopy._final_missing_pass("XAUUSD",root,date(2003,1,1),date(2026,11,10))==1
    assert pq.read_metadata(path).metadata[b"msd_complete"]==b"0"


def test_dukascopy_empty_decode_has_utc_timestamp_dtype():
    from msd.data.dukascopy import COLUMNS, DUKA_COLUMNS
    empty=decode(b"","BTCUSD",date(2024,1,1),"BID")
    assert empty.columns.tolist()==DUKA_COLUMNS and empty.columns[:len(COLUMNS)].tolist()==COLUMNS
    assert str(empty.ts.dtype)=="datetime64[ns, UTC]"


def test_stage8_dukascopy_tier_order_starts_with_gold_then_crypto():
    from msd.data.stage8_download import DUKASCOPY_ORDER, DUKASCOPY_START
    assert DUKASCOPY_ORDER[:3]==("XAUUSD","USA30IDXUSD","DEUIDXEUR")
    assert set(DUKASCOPY_ORDER)==set(DUKASCOPY_START)


def test_gold_point_scale_covers_2003_history_when_raw_sample_available():
    from pathlib import Path
    from msd.data.dukascopy import PRICE_BANDS, SCALES
    raw=Path("data/raw/dukascopy/XAUUSD/2003-05-08_BID.bi5")
    assert SCALES["XAUUSD"]==1000
    assert PRICE_BANDS["XAUUSD"]==(200,10000)
    if raw.exists():
        decoded=decode(raw.read_bytes(),"XAUUSD",date(2003,5,8),"BID")
        assert 300 < decoded.bid_o.median() < 400


def test_dukascopy_bad_tick_is_flagged_and_retained():
    from msd.data.dukascopy import mark_bad_ticks
    ts=pd.date_range("2024-06-12",periods=5,freq="min",tz="UTC")
    mid=np.array([100.,100.1,100.2,150.,100.3])
    frame=pd.DataFrame({"ts":ts,"bid_o":mid,"ask_o":mid+.01,
                        "bid_h":mid+.1,"ask_h":mid+.11,"bid_l":mid-.1,"ask_l":mid-.09,
                        "bid_c":mid,"ask_c":mid+.01,"volume":1.})
    flagged=mark_bad_ticks(frame)
    assert len(flagged)==len(frame) and flagged.bad_tick.any()


def test_dukascopy_quarantine_csv_records_reason_and_range(tmp_path,monkeypatch):
    from msd.data import dukascopy
    monkeypatch.chdir(tmp_path)
    error=dukascopy.PlausibilityError("XAUUSD",date(2003,5,8),"BID","out of range",100.,20000.)
    dukascopy._record_quarantine("XAUUSD",error)
    result=pd.read_csv("data/logs/quarantine_XAUUSD.csv")
    assert result.loc[0,"date"]=="2003-05-08" and result.loc[0,"raw_min"]==100.
    assert "out of range" in result.loc[0,"reason"]


def test_binance_timestamp_units_checksum_and_embedded_spread(monkeypatch,tmp_path):
    from io import BytesIO
    from zipfile import ZipFile
    import hashlib
    import pyarrow as pa
    import pyarrow.parquet as pq
    from msd.data import binance
    for stamp,expected_year in ((1718150400000,2024),(1735689600000000,2025)):
        buffer=BytesIO()
        with ZipFile(buffer,"w") as archive:
            archive.writestr("klines.csv",f"{stamp},67000,67100,66900,67050,12,0,0,0,0,0,0\\n")
        raw=buffer.getvalue(); digest=hashlib.sha256(raw).hexdigest()
        monkeypatch.setattr(binance,"_get",lambda url,raw=raw,digest=digest: f"{digest} archive.zip".encode() if url.endswith("CHECKSUM") else raw)
        decoded=binance.fetch_month(date(expected_year,1,1))
        assert decoded.ts.iloc[0].year==expected_year
    month=binance.fetch_month(date(2024,6,1))
    path=tmp_path/"BTCUSDT"/"2024-06.parquet"; path.parent.mkdir()
    pq.write_table(pa.Table.from_pandas(month,preserve_index=False),path)
    loaded=binance.load("BTCUSDT","2024-06-01","2024-06-30",root=tmp_path)
    assert np.allclose(loaded.ask_o-loaded.bid_o,binance.BTC_SPREAD[2024])


def test_binance_checksum_mismatch_is_rejected(monkeypatch):
    from msd.data import binance
    monkeypatch.setattr(binance,"_get",lambda _url: b"0"*64 if _url.endswith("CHECKSUM") else b"wrong")
    try: binance.fetch_month(date(2024,6,1))
    except ValueError as exc: assert "SHA256 mismatch" in str(exc)
    else: raise AssertionError("checksum mismatch accepted")


def test_quality_cash_thresholds_and_usable_year_run():
    from msd.data.quality import analyze, contiguous_usable_years
    times=[]
    for day in pd.date_range("2024-06-10",periods=5,freq="D"):
        session=pd.date_range(pd.Timestamp(f"{day.date()} 09:30",tz="America/New_York"),periods=390,freq="min")
        times.extend(session.tz_convert("UTC"))
    frame=pd.DataFrame({"ts":times,"bid_o":100.,"ask_o":100.1,"volume":1.})
    quality=analyze(frame)
    row=quality.loc[quality.year==2024].iloc[0]
    assert row.sessions==5 and row.median_bars==390 and row.open_coverage==1 and row.usable
    years=pd.DataFrame({"year":[2018,2019,2020,2022],"usable":[True,True,False,True]})
    assert contiguous_usable_years(years)==[2018,2019]


def test_shared_stop_ratchet_applies_from_next_bar_only():
    from msd.backtest import ratchet_stop
    assert ratchet_stop(1,100.,99.)==100. and ratchet_stop(1,100.,101.)==101.
    assert ratchet_stop(-1,100.,101.)==100. and ratchet_stop(-1,100.,99.)==99.
    frame=bars([(100,101,100,100),(100,101,99,100),(100,101,99.5,100),(100,101,100,100)])
    order={"decision_ts":frame.ts.iloc[0],"side":1,"stop":95.,"exit_ts":frame.ts.iloc[3],"stop_path":{frame.ts.iloc[1]:100.}}
    trade=simulate(frame,[order]).iloc[0]
    assert trade.exit_reason=="stop" and trade.exit_ts==frame.ts.iloc[2] and trade.exit_price==100.
    from msd.backtest import evaluate_bar
    bar={"bid_o":101.,"bid_h":102.,"bid_l":100.,"bid_c":101.,"ask_o":101.2,"ask_h":102.2,"ask_l":100.2,"ask_c":101.2}
    _,reason,price=evaluate_bar(-1,105.,None,bar,time_exit=True)
    assert reason=="time" and price==101.2


def test_quality_reports_typical_cme_gap_windows():
    from msd.data.quality import analyze
    stamps=[]
    for day in pd.date_range("2024-06-03",periods=5,freq="D"):
        local=day.date()
        weekday=day.weekday()
        pieces=[(pd.Timestamp(f"{local} 00:00",tz="America/New_York"),pd.Timestamp(f"{local} 16:14",tz="America/New_York"))]
        if weekday<4:
            pieces.append((pd.Timestamp(f"{local} 18:08",tz="America/New_York"),pd.Timestamp(f"{local} 23:59",tz="America/New_York")))
        for start,end in pieces:
            stamps.extend(pd.date_range(start,end,freq="min").tz_convert("UTC"))
    frame=pd.DataFrame({"ts":stamps,"bid_o":100.,"ask_o":100.1,"volume":1.})
    row=analyze(frame).iloc[0]
    assert "16:15-17:00 (100%)" in row.typical_weekday_gap_windows
    assert "18:00-18:08 (100%)" in row.typical_weekday_gap_windows


def test_histdata_parse_fixed_est_schema_volume_and_token(tmp_path):
    import io
    from zipfile import ZipFile
    from msd.data.histdata import HIST_COLUMNS, parse_archive, parse_csv, parse_token
    source = b"20240115 093000;100;102;99;101;0\n20240715 093000;101;103;100;102;0\n"
    frame = parse_csv(source)
    assert frame.columns.tolist() == HIST_COLUMNS
    assert frame.ts.tolist() == [pd.Timestamp("2024-01-15 14:30", tz="UTC"), pd.Timestamp("2024-07-15 13:30", tz="UTC")]
    transition = parse_csv(b"20190311 093000;1;1;1;1;0\n20190401 093000;1;1;1;1;0\n20191028 093000;1;1;1;1;0\n20191104 093000;1;1;1;1;0\n")
    assert transition.ts.tolist() == [pd.Timestamp("2019-03-11 14:30",tz="UTC"),
                                      pd.Timestamp("2019-04-01 13:30",tz="UTC"),
                                      pd.Timestamp("2019-10-28 14:30",tz="UTC"),
                                      pd.Timestamp("2019-11-04 14:30",tz="UTC")]
    assert (frame.ask_o == frame.bid_o).all() and frame.volume.isna().all()
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("DAT_ASCII_NSXUSD_M1_2024.csv", source)
        archive.writestr("DAT_ASCII_NSXUSD_M1_2024.txt", "gaps: none")
    parsed, gaps = parse_archive(buffer.getvalue(), "NSXUSD")
    assert len(parsed) == 2 and "gaps" in gaps
    assert parse_token('<form id="file_down"><input type="hidden" value="abc123" name="tk"></form>') == "abc123"


def test_histdata_eu_calendar_dst_spring_drop_and_fall_fold_order():
    from msd.data.histdata import parse_csv
    # U.S. switched on March 12, but HistData remained on standard time until
    # the EU-style March 26 switch. All four of these local wall times exist.
    us_spring = parse_csv(b"20230312 015900;1;1;1;1;0\n20230312 020000;1;1;1;1;0\n20230312 023000;1;1;1;1;0\n20230312 030000;1;1;1;1;0\n")
    assert us_spring.ts.tolist() == [pd.Timestamp(f"2023-03-12 {x}",tz="UTC") for x in ("06:59","07:00","07:30","08:00")]
    spring = parse_csv(b"20230326 015900;1;1;1;1;0\n20230326 020000;1;1;1;1;0\n20230326 023000;1;1;1;1;0\n20230326 030000;1;1;1;1;0\n")
    assert spring.ts.tolist() == [pd.Timestamp("2023-03-26 06:59", tz="UTC"), pd.Timestamp("2023-03-26 07:00", tz="UTC")]
    assert len(spring.attrs["nonexistent_local_rows"]) == 2
    fall = parse_csv(b"20231029 005900;1;1;1;1;0\n20231029 010000;1;1;1;1;0\n20231029 010100;1;1;1;1;0\n20231029 010000;1;1;1;1;0\n20231029 010100;1;1;1;1;0\n20231029 020000;1;1;1;1;0\n")
    assert fall.ts.tolist() == [pd.Timestamp(f"2023-10-29 {hour}", tz="UTC") for hour in ("04:59", "05:00", "05:01", "06:00", "06:01", "07:00")]


def test_histdata_feed_and_backward_adjustment():
    from msd.data.histdata import HISTDATA_SWITCH_UTC, apply_feed_and_rolls
    ts=pd.DatetimeIndex(["2018-12-15 22:58Z","2018-12-15 22:59Z","2018-12-16 22:59Z","2018-12-16 23:00Z","2018-12-16 23:01Z"])
    frame=pd.DataFrame({"ts":ts,"bid_o":[10.,11.,12.,13.,14.],"bid_h":[10.,11.,12.,13.,14.],
                        "bid_l":[10.,11.,12.,13.,14.],"bid_c":[10.,11.,12.,13.,14.],
                        "ask_o":[10.,11.,12.,13.,14.],"ask_h":[10.,11.,12.,13.,14.],
                        "ask_l":[10.,11.,12.,13.,14.],"ask_c":[10.,11.,12.,13.,14.],"volume":np.nan})
    result=apply_feed_and_rolls(frame,"NSXUSD",{pd.Timestamp("2018-12-16").date():2.})
    assert HISTDATA_SWITCH_UTC["NSXUSD"]==pd.Timestamp("2018-12-16 23:00",tz="UTC")
    assert result.feed.tolist()==["futures_cont","futures_cont","futures_cont","cash_cfd","cash_cfd"]
    assert result.roll.tolist()==[False,False,True,False,False]
    assert result.adj_bid_c.tolist()==[12.,13.,12.,13.,14.]


def test_histdata_roll_recovered_at_exact_gap_bar_and_adjusted_continuously():
    from msd.data.histdata import _gap_candidates,apply_feed_and_rolls
    before=pd.date_range("2016-03-18 12:00",periods=60,freq="min",tz="UTC")
    after=pd.date_range("2016-03-18 13:21",periods=60,freq="min",tz="UTC")
    ts=before.append(after)
    base=1000.+np.arange(len(ts))*.01
    offset=np.r_[np.full(60,1.55),np.full(60,-11.30)]
    hist_price=base+offset
    hist=pd.DataFrame({"ts":ts,"bid_o":hist_price,"bid_h":hist_price+.1,"bid_l":hist_price-.1,
                       "bid_c":hist_price,"ask_o":hist_price,"ask_h":hist_price+.1,"ask_l":hist_price-.1,
                       "ask_c":hist_price,"volume":np.nan,"feed":"futures_cont"})
    candidates=_gap_candidates(hist,date(2016,3,18))
    assert len(candidates)==1
    row=candidates[0]
    assert row["switch_ts"]==after[0] and row["gap_minutes"]==22.
    adjusted=apply_feed_and_rolls(hist,"NSXUSD",{row["switch_ts"]:-12.85})
    assert adjusted.roll.sum()==1 and adjusted.loc[60,"roll"]
    jump=adjusted.adj_bid_c.iloc[60]-adjusted.adj_bid_c.iloc[59]
    assert abs(jump)<1.


def test_histdata_roll_uses_held_out_full_days_and_independent_validation():
    from datetime import date
    from msd.data.histdata import _full_day_roll_measure
    days=[date(2016,3,14),date(2016,3,15),date(2016,3,16),date(2016,3,17),date(2016,3,18),
          date(2016,3,21),date(2016,3,22),date(2016,3,23),date(2016,3,24)]
    offsets=pd.Series([-1.0,-1.2,-1.1,-1.3,99.,-11.2,-10.1,-10.0,-10.2],index=days)
    result=_full_day_roll_measure(offsets,date(2016,3,18),date(2016,3,18))
    assert result is not None
    assert result["estimate_before_days"]==[days[1],days[2]]
    assert result["estimate_after_days"]==[days[6],days[7]]
    assert result["validation_before_day"]==days[3]
    assert result["validation_after_day"]==days[5]
    adjusted_before=result["validation_before"]+result["gap"]
    assert abs(adjusted_before-result["validation_after"])<2
    assert result["gap"]==pytest.approx(-8.9)


def test_histdata_march_2016_full_day_roll_measurement():
    from datetime import date
    from msd.data.histdata import _full_day_roll_measure
    offsets=pd.Series([-0.5,-0.4535,-1.254,50.,-11.296,-9.998,-10.0,-10.2],index=[
        date(2016,3,15),date(2016,3,16),date(2016,3,17),date(2016,3,18),
        date(2016,3,21),date(2016,3,22),date(2016,3,23),date(2016,3,24)])
    result=_full_day_roll_measure(offsets,date(2016,3,18),date(2016,3,18))
    assert result is not None
    assert result["gap"]==pytest.approx(-9.52225)
    assert result["gap_2day"]==pytest.approx(-9.52225)
    assert result["uncertainty"]==pytest.approx(0.02225)
    assert result["validation_residual"]==pytest.approx(0.51975)


def test_histdata_stale_detector_flags_expiry_open_to_switch():
    from msd.data.histdata import _stale_span
    before=pd.date_range("2016-03-18 13:00",periods=30,freq="min",tz="UTC")
    frozen=pd.date_range("2016-03-18 13:30",periods=81,freq="min",tz="UTC")
    after=pd.date_range("2016-03-18 14:51",periods=40,freq="min",tz="UTC")
    ts=before.append(frozen).append(after)
    duka_price=4400+np.arange(len(ts),dtype=float)*.5
    hist_price=duka_price.copy()
    hist_price[30:111]=duka_price[29]
    hist=pd.DataFrame({"ts":ts,"bid_c":hist_price})
    duka=pd.DataFrame({"ts":ts,"bid_c":duka_price})
    found=_stale_span(hist,duka,date(2016,3,18),pd.Timestamp("2016-03-18 14:51",tz="UTC"))
    assert found["stale_detected"]
    assert found["stale_start"]==pd.Timestamp("2016-03-18 13:30",tz="UTC")
    assert found["stale_end"]==pd.Timestamp("2016-03-18 14:51",tz="UTC")


def test_histdata_roll_application_flags_stale_and_unmeasured_history():
    from msd.data.histdata import apply_feed_and_rolls
    ts=pd.date_range("2018-12-16 22:58",periods=5,freq="min",tz="UTC")
    frame=pd.DataFrame({"ts":ts,**{f"bid_{f}":np.arange(5,dtype=float)+100 for f in "ohlc"},
                        **{f"ask_{f}":np.arange(5,dtype=float)+100.1 for f in "ohlc"},"volume":1.})
    start=ts[1];end=ts[3]
    out=apply_feed_and_rolls(frame,"NSXUSD",{ts[3]:2.},stale_spans=[(start,end)],valid_from=ts[2])
    assert out.stale_expired.tolist()==[False,True,True,False,False]
    assert out.loc[0,"adj_bid_c"]!=out.loc[0,"adj_bid_c"]
    assert np.isfinite(out.loc[2,"adj_bid_c"])
