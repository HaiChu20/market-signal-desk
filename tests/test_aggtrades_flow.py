from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import pytest

from msd.data import aggtrades_flow as flow


HEADER = "agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"


def _make_archive(tmp_path: Path, *, header: bool, unit: str = "ms") -> Path:
    root=tmp_path/"raw"/"spot"/"BTCUSDT"
    root.mkdir(parents=True)
    archive=root/"BTCUSDT-aggTrades-2025-01.zip"
    stamp0=pd.Timestamp("2025-01-02 00:00:00.250",tz="UTC").value
    stamps=[stamp0//1_000_000 if unit=="ms" else stamp0//1_000,
            (stamp0+1_550_000_000)//1_000_000 if unit=="ms" else (stamp0+1_550_000_000)//1_000,
            (stamp0+59_850_000_000)//1_000_000 if unit=="ms" else (stamp0+59_850_000_000)//1_000]
    rows=[f"10,100,0.5,100,100,{stamps[0]},false",
          f"12,101,1.0,101,101,{stamps[1]},true",
          f"13,99,2.0,102,102,{stamps[2]},false"]
    content=(HEADER if header else "")+"\n".join(rows)+"\n"
    with ZipFile(archive,"w",ZIP_DEFLATED) as zf:
        zf.writestr("BTCUSDT-aggTrades-2025-01.csv",content)
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{sha}  {archive.name}\n")
    return archive


@pytest.mark.parametrize(("header","unit"),[(True,"ms"),(False,"us")])
def test_stream_parser_header_and_timestamp_units(tmp_path,header,unit):
    archive=_make_archive(tmp_path,header=header,unit=unit)
    minute,second,detected=flow._stream_archive(archive)
    assert detected==unit
    assert len(minute)==2
    assert second is not None and len(second)==3
    assert str(minute.ts.dtype)=="datetime64[ns, UTC]"
    assert (minute.known_at==minute.ts+pd.Timedelta(minutes=1)).all()
    assert (second.known_at==second.ts+pd.Timedelta(seconds=1)).all()


def test_taker_side_id_gaps_ohlc_offsets_and_trade_counts(tmp_path):
    archive=_make_archive(tmp_path,header=True,unit="ms")
    minute,second,_=flow._stream_archive(archive)
    first=minute.iloc[0]
    assert first.buy_vol==pytest.approx(.5)
    assert first.sell_vol==pytest.approx(1.0)
    assert first.buy_n==1 and first.sell_n==1
    assert first.first_agg_id==10 and first.last_agg_id==12
    assert first.id_gaps==1
    assert first.o==100 and first.h==101 and first.l==100 and first.c==101
    assert first.high_ms==1800 and first.low_ms==250
    assert second.iloc[0].buy_vol==pytest.approx(.5)
    assert second.iloc[1].buy_vol==pytest.approx(0.)
    assert second.iloc[1].n==1
    assert minute.o.dtype==np.float64 and second.o.dtype==np.float64


def test_streaming_second_sink_merges_a_boundary_second(tmp_path):
    first=pd.DataFrame({"second":[100,101],"o":[10.,11.],"h":[12.,12.],"l":[9.,10.],
                        "c":[11.,12.],"volume":[2.,3.],"buy_vol":[1.,2.],"n":[2,3]})
    next_block=pd.DataFrame({"second":[101,102],"o":[12.,13.],"h":[13.,14.],"l":[11.,12.],
                             "c":[13.,14.],"volume":[4.,5.],"buy_vol":[3.,1.],"n":[4,5]})
    path=tmp_path/"streamed.parquet"
    sink=flow._SecondParquetSink(path,"a"*64)
    sink.add(first);sink.add(next_block);sink.close()
    result=pd.read_parquet(path)
    assert len(result)==3
    boundary=result[result.ts==pd.to_datetime(101000,unit="ms",utc=True)].iloc[0]
    assert boundary.o==11. and boundary.h==13. and boundary.l==10. and boundary.c==13.
    assert boundary.volume==7. and boundary.buy_vol==5. and boundary.n==7
    assert result.o.dtype==np.float64
    assert pq.read_schema(path).metadata[b"msd_complete"]==b"1"


def test_um_kline_residual_is_causal_audit_only(tmp_path, monkeypatch):
    ts = pd.to_datetime(["2024-06-01 00:00:00", "2024-06-01 00:01:00"], utc=True)
    minute = pd.DataFrame({"ts": ts, "o": [100., 101.], "h": [102., 103.],
                           "l": [99., 100.], "c": [101., 102.],
                           "buy_vol": [.6, .5], "sell_vol": [.4, .5]})
    path = tmp_path / "klines.parquet"
    pd.DataFrame({"ts": ts, "bid_o": [100., 101.], "bid_h": [102., 103.],
                  "bid_l": [99., 100.], "bid_c": [101., 102.],
                  "volume": [1.2, 1.0]}).to_parquet(path)
    monkeypatch.setattr(flow, "_kline_path", lambda *_: path)
    audited = flow.add_um_kline_audit(minute, "BTCUSDT", "2024-06")
    assert audited.uncovered_volume.iloc[0] == pytest.approx(.2)
    assert audited.uncovered_volume.iloc[1] == pytest.approx(0.)
    assert audited.um_kline_agg_mismatch.tolist() == [True, False]
    pd.testing.assert_series_equal(audited.o, minute.o)
    pd.testing.assert_series_equal(audited.c, minute.c)
    output = tmp_path / "um.parquet"
    source_sha = "b" * 64
    flow._atomic_parquet(minute, output, source_sha)
    assert flow._is_complete(output, source_sha)
    assert not flow._um_audit_complete(output, source_sha)
    flow._atomic_parquet(audited, output, source_sha)
    assert flow._um_audit_complete(output, source_sha)


def test_resume_skips_matching_complete_outputs(tmp_path,monkeypatch):
    archive=_make_archive(tmp_path,header=True,unit="ms")
    minute,second,_=flow._stream_archive(archive)
    month_root=tmp_path/"minute";second_root=tmp_path/"second"
    monkeypatch.setattr(flow,"MINUTE_ROOT",month_root)
    monkeypatch.setattr(flow,"SECOND_ROOT",second_root)
    sha=flow._sidecar_sha256(archive)
    minute_path=month_root/"spot"/"BTCUSDT"/"2025-01.parquet"
    second_path=second_root/"BTCUSDT"/"2025-01.parquet"
    flow._atomic_parquet(minute,minute_path,sha)
    flow._atomic_parquet(second,second_path,sha)
    monkeypatch.setattr(flow,"_stream_archive",lambda _path: pytest.fail("should resume-skip"))
    result=flow.process_archive(archive,validate=False)
    assert result["skipped"] is True


def test_real_archive_first_arrow_block_if_available():
    archive=next((path for path in flow.RAW_ROOT.rglob("*.zip")
                  if path.with_suffix(path.suffix+".sha256").is_file()),None)
    if archive is None:
        pytest.skip("no checksum-complete aggTrades archive is present")
    from zipfile import ZipFile
    with ZipFile(archive) as zf:
        info=next(i for i in zf.infolist() if i.filename.lower().endswith(".csv"))
        with zf.open(info) as member:
            first_line=member.readline()
        with zf.open(info) as member:
            reader=flow._csv_reader(member,first_line)
            block=next(iter(reader))
    assert set(flow.REQUIRED_COLUMNS).issubset(block.column_names)
    assert block.num_rows>0
