import importlib.util
import json
import os
from pathlib import Path
import time

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "hpc/roihu/sequence/make_bundle.py"
spec = importlib.util.spec_from_file_location("sequence_bundle", SCRIPT)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def test_bundle_refuses_old_output_and_low_coverage(tmp_path, monkeypatch):
    data = tmp_path / "data"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"period": "dev", "end_exclusive": "2022-01-01",
                                  "symbols": ["BTCUSDT"], "starts": {"BTCUSDT": "2021-01-01"}}))
    marker = data / "tmp" / "stage9p4_BTCUSDT_year_chain_done.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"symbol": "BTCUSDT", "end_year": 2022}))
    year = marker.with_name("stage9p4_BTCUSDT_2021.json")
    year.write_text(json.dumps({"runtime_seconds": 100}))
    now = time.time()
    for month in range(1, 13):
        stem = f"2021-{month:02d}.parquet"
        for relative in (f"bars/binance_spot/BTCUSDT/{stem}",
                         *(f"derived/bars_{tf}/BTCUSDT/{stem}" for tf in ("15m", "1h", "4h")),
                         f"features/BTCUSDT/{stem}", f"labels/BTCUSDT/{stem}"):
            path = data / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
            os.utime(path, (now, now))
    monkeypatch.setattr(bundle, "anchor_coverage", lambda *a: {"anchors": 100, "kept": 79, "coverage": .79})
    with pytest.raises(RuntimeError, match="low-coverage"):
        bundle.make_bundle(data, config, tmp_path / "coverage")
    monkeypatch.setattr(bundle, "anchor_coverage", lambda *a: {"anchors": 100, "kept": 90, "coverage": .9})
    stale = data / "features/BTCUSDT/2021-06.parquet"
    os.utime(stale, (now - 1000, now - 1000))
    with pytest.raises(RuntimeError, match="stale"):
        bundle.make_bundle(data, config, tmp_path / "freshness")
    assert "features/BTCUSDT/2021-06.parquet" in (tmp_path / "freshness/stale.txt").read_text()
