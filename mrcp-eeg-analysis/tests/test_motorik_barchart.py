from pathlib import Path

import pandas as pd
import pytest

from src.main import build_parser, run
from src.motorik_barchart import (generate_motorik_barcharts, prepare_valid_motor_events,
                                  select_epoch_winners, summarize_regions)


def _feature_rows(metric="minimum_amplitude_uv"):
    rows=[]
    values={0:{"C3":-4.0,"Cz":-2.0,"O1":-20.0},1:{"C3":-1.0,"Cz":-5.0,"O1":-30.0}}
    for epoch,channels in values.items():
        for channel,value in channels.items():
            rows.append({"subject_id":"SUBJECT01","recording_key":"R1","epoch_index":epoch,
                         "channel":channel,metric:value,"epoch_valid":True})
    return pd.DataFrame(rows)


def test_subject_motor_events_are_filtered_renamed_and_sorted():
    qc=pd.DataFrame([
        {"subject_id":"S1","valid_epoch_count":2,"dropped_epoch_count":1,"processing_status":"success"},
        {"subject_id":"S2","valid_epoch_count":5,"dropped_epoch_count":0,"processing_status":"partial_success"},
        {"subject_id":"S3","valid_epoch_count":99,"dropped_epoch_count":0,"processing_status":"failed"},
    ])
    result=prepare_valid_motor_events(qc)
    assert result["subject_id"].tolist()==["S2","S1"]
    assert result.columns.tolist()==["subject_id","valid_motor_events","dropped_motor_events","processing_status"]


def test_minimum_metric_selects_one_winner_and_excludes_non_focus_channels():
    winners=select_epoch_winners(_feature_rows())
    assert len(winners)==2 and not winners.duplicated(["subject_id","recording_key","epoch_index"]).any()
    assert winners["channel"].tolist()==["C3","Cz"]
    assert set(winners["metric_used"])=={"minimum_amplitude_uv"}


def test_post_minus_pre_fallback_uses_largest_absolute_value():
    frame=_feature_rows("post_minus_pre_uv")
    winners=select_epoch_winners(frame)
    assert winners["channel"].tolist()==["C3","Cz"]
    assert set(winners["metric_used"])=={"post_minus_pre_uv"}


def test_region_groups_are_left_midline_right():
    winners=pd.DataFrame([
        {"subject_id":"S","recording_key":"R","epoch_index":0,"channel":"FC3","metric_used":"minimum_amplitude_uv"},
        {"subject_id":"S","recording_key":"R","epoch_index":1,"channel":"Cz","metric_used":"minimum_amplitude_uv"},
        {"subject_id":"S","recording_key":"R","epoch_index":2,"channel":"CP4","metric_used":"minimum_amplitude_uv"},
    ])
    result=summarize_regions(winners).set_index("region")
    assert result["winner_count"].to_dict()=={"left":1,"midline":1,"right":1}


def test_missing_metric_and_empty_table_raise_clear_errors():
    with pytest.raises(ValueError,match="requires minimum_amplitude_uv or post_minus_pre_uv"):
        select_epoch_winners(_feature_rows().drop(columns="minimum_amplitude_uv"))
    with pytest.raises(ValueError,match="empty"):
        select_epoch_winners(pd.DataFrame(columns=["subject_id","recording_key","epoch_index","channel"]))


def test_png_csv_report_generation_does_not_touch_raw_or_create_emotion(tmp_path):
    group=tmp_path/"outputs"/"group_analysis"; tables=group/"tables"; logs=group/"logs"
    tables.mkdir(parents=True); logs.mkdir(); (logs/"warnings.txt").write_text("",encoding="utf-8")
    raw=tmp_path/"SUBJECT01_Trial_01_EEG.csv"; raw.write_bytes(b"Triggers,0\n0,1\n"); before=raw.read_bytes()
    pd.DataFrame([{"subject_id":"SUBJECT01","valid_epoch_count":2,"dropped_epoch_count":1,"processing_status":"success"}]).to_csv(tables/"subject_qc_summary.csv",index=False)
    pd.DataFrame([{"recording_key":"R1","status":"success"}]).to_csv(tables/"recording_qc_summary.csv",index=False)
    pd.DataFrame(columns=["eeg_emg_latency_s"]).to_csv(tables/"eeg_emg_latency_features.csv",index=False)
    _feature_rows().to_csv(tables/"mrcp_epoch_features.csv",index=False)
    generate_motorik_barcharts(tmp_path/"outputs")
    for name in ("valid_motor_events_per_subject","most_frequent_mrcp_channel","mrcp_region_frequency"):
        assert (tables/f"{name}.csv").exists()
        assert (group/"figures"/f"{name}.png").stat().st_size>0
    report=(group/"reports"/"group_mrcp_report.html").read_text(encoding="utf-8")
    assert "Motorik frequency analysis" in report
    assert raw.read_bytes()==before
    assert not list(tmp_path.rglob("emotion_frequency.csv"))


def test_cli_motorik_mode_does_not_require_data_dir():
    args=build_parser().parse_args(["--output-dir","outputs","--make-motorik-barcharts"])
    assert args.make_motorik_barcharts and args.data_dir is None


def test_cli_motorik_flag_calls_generator_and_prints_paths(monkeypatch, tmp_path, capsys):
    called={}
    def fake_generate(output_dir):
        called["output_dir"]=output_dir
        return {"valid_events_png": Path(output_dir)/"group_analysis"/"figures"/"x.png"}
    monkeypatch.setattr("src.motorik_barchart.generate_motorik_barcharts", fake_generate)
    args=build_parser().parse_args(["--output-dir",str(tmp_path),"--make-motorik-barcharts"])
    assert run(args)==0
    assert called["output_dir"]==tmp_path
    assert "valid_events_png" in capsys.readouterr().out


def test_missing_motorik_input_reports_required_path_and_command(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        generate_motorik_barcharts(tmp_path/"outputs")
    message=str(exc.value)
    assert "Motorik Bar Chart input not found:" in message
    assert "subject_qc_summary.csv" in message
    assert "--all-subjects" in message
