import json

import pandas as pd
import pytest

from msd.research import family_random_v2 as correction
from msd.research.family_random_rerun import _card_unit,compare_jobs


def _fixture(tmp_path):
    output=tmp_path/"reports";jobs=output/"jobs";signals=tmp_path/"signals"
    jobs.mkdir(parents=True);signals.mkdir()
    for family in correction.FAMILIES:
        for symbol in correction.SYMBOLS:
            (jobs/f"{family}_{symbol}.json").write_text(json.dumps({
                "pooled":{"random_direction_percentile":98.5 if (family,symbol)==("f4_regime","USATECHIDXUSD") else None}}))
            pd.DataFrame({"sym":[symbol],"ts":[pd.Timestamp("2022-01-01",tz="UTC")],
                "side":[1],"price":[100.],"sl":[99.],"tp":[102.],
                "deadline_ts":[pd.Timestamp("2022-01-02",tz="UTC")],"net_R":[1.]}).to_parquet(
                    signals/f"{family}_{symbol}.parquet",index=False)
    (output/"families_summary.md").write_text("# summary\n")
    return output,signals


def test_correction_reuses_saved_signals_and_is_idempotent(tmp_path,monkeypatch):
    output,signals=_fixture(tmp_path)
    monkeypatch.setattr(correction,"random_direction",lambda frame,*args,**kwargs:(96.,len(frame),[]))
    result=correction.run(tmp_path,signals,output,seeds=2)
    assert len(result)==15
    assert result.random_pass_95.all()
    assert result.original_random_pass.isna().all()
    first=(output/"families_summary.md").read_text()
    correction.run(tmp_path,signals,output,seeds=2)
    assert (output/"families_summary.md").read_text()==first
    assert (output/"families_random_pct_v2.csv").exists()
    assert "original-threshold verdict is N/A" in first
    assert "Supplemental pct ≥95" in first


def test_missing_saved_signals_fails_instead_of_refitting(tmp_path):
    with pytest.raises(FileNotFoundError,match="models will not be refit"):
        correction._signals(tmp_path/"missing.parquet","f4_regime","USATECHIDXUSD")


def test_saved_signals_reject_2023(tmp_path):
    path=tmp_path/"signals.parquet"
    pd.DataFrame({"sym":["BTCUSDT"],"ts":[pd.Timestamp("2023-01-01",tz="UTC")],
        "side":[1],"price":[100.],"sl":[99.],"tp":[102.],
        "deadline_ts":[pd.Timestamp("2023-01-02",tz="UTC")],"net_R":[1.]}).to_parquet(path,index=False)
    with pytest.raises(ValueError,match="2023"):
        correction._signals(path,"f4_regime","BTCUSDT")


def test_rerun_comparison_checks_oof_and_selected_metrics():
    pooled={"n":15,"net_avg_R":.15,"hit_rate":.8,"brier":.18}
    original={"family":"f4_regime","symbol":"USATECHIDXUSD","candidates":100,
              "pooled":pooled}
    rerun={"family":"f4_regime","symbol":"USATECHIDXUSD","candidates":100,
           "pooled":dict(pooled)}
    assert compare_jobs(original,rerun)["deterministic"]
    rerun["pooled"]["brier"] += 1e-5
    result=compare_jobs(original,rerun)
    assert not result["brier_match"]
    assert not result["deterministic"]


def test_determinism_input_is_read_from_report_card(tmp_path):
    cards=tmp_path/"cards";cards.mkdir()
    (cards/"phase2_f4_regime_USATECHIDXUSD_dev.json").write_text(json.dumps({
        "pooled":{"n":15,"net_avg_R":.15,"hit_rate":.8,"brier":.18,
                  "row_accounting":{"assembled_rows":4561550}}}))
    unit=_card_unit(tmp_path,"f4_regime","USATECHIDXUSD")
    assert unit["candidates"]==4561550
    assert unit["pooled"]["n"]==15
