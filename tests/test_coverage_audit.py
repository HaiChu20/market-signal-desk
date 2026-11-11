from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from msd.data.coverage_audit import audit_symbol


def test_detects_planted_asian_session_gap(tmp_path: Path):
    symbol = "USATECHIDXUSD"
    target = tmp_path / "data/bars/dukascopy" / symbol
    target.mkdir(parents=True)
    hours = pd.date_range("2020-01-01", "2024-01-01", freq="h", tz="UTC", inclusive="left")
    local = hours.tz_convert("America/New_York")
    keep = (local.day_of_week < 5) & ((local.year >= 2022) | (local.hour >= 6))
    stamps = hours[keep]
    frame = pd.DataFrame({"ts": stamps})
    for side, price in (("bid", 100.0), ("ask", 100.1)):
        for field in "ohlc":
            frame[f"{side}_{field}"] = price
    frame["bad_tick"] = False
    for month, part in frame.groupby(frame.ts.dt.strftime("%Y-%m")):
        table = pa.Table.from_pandas(part, preserve_index=False)
        metadata = dict(table.schema.metadata or {})
        metadata[b"msd_complete"] = b"1"
        pq.write_table(table.replace_schema_metadata(metadata), target / f"{month}.parquet")
    result = audit_symbol(symbol, tmp_path)
    early = next(row for row in result["missing_hours_by_era"] if row["year"] == 2020)
    recent = next(row for row in result["missing_hours_by_era"] if row["year"] == 2023)
    assert early["missing_hour_count"] >= 25
    assert "0:00" in early["missing_hours_of_week"]
    assert recent["missing_hour_count"] == 0
    assert result["recommended_start"] >= "2022-01-01"
