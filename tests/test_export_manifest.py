import hashlib
from pathlib import Path

import pandas as pd

from msd.data import export_manifest as manifest


def test_manifest_sidecar_parquet_stats_and_verify(tmp_path):
    raw = tmp_path / "data/raw/source/file.bi5"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"verified archive")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    Path(str(raw) + ".sha256").write_text(f"{digest}  {raw.name}\n")
    bar = tmp_path / "data/bars/source/2024-01.parquet"
    bar.parent.mkdir(parents=True)
    pd.DataFrame({"ts": pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z"]),
                  "value": [1, 2]}).to_parquet(bar, index=False)
    rows = list(manifest.scan(tmp_path, ("raw", "bars")))
    raw_row = next(row for row in rows if row["path"].endswith("file.bi5"))
    bar_row = next(row for row in rows if row["path"].endswith("2024-01.parquet"))
    assert raw_row["sha256"] == digest
    assert "2024-01-01" in bar_row["ts_min"]
    assert "00:01:00" in bar_row["ts_max"]
    out = tmp_path / "data/manifest/export_20240102.csv"
    assert manifest.export(tmp_path, ("raw", "bars"), dry_run=True, output=out)["files"] == 3
    assert not out.exists()
    assert manifest.export(tmp_path, ("raw", "bars"), output=out)["files"] == 3
    assert manifest.verify(tmp_path, out)["checked"] == 3
    raw.write_bytes(b"tampered archive")
    assert any("size mismatch" in problem or "SHA256 mismatch" in problem
               for problem in manifest.verify(tmp_path, out)["problems"])
