from pathlib import Path

import pandas as pd

from src.main import build_parser, run
from src.report_rebuild import discover_subject_video, rebuild_reports


def _artifacts(root,subject,video_name=None,video_bytes=b"valid-video"):
    base=root/subject
    for folder in ("tables","figures","videos","logs","reports"): (base/folder).mkdir(parents=True,exist_ok=True)
    pd.DataFrame([{"subject":subject,"session":"01"}]).to_csv(base/"tables"/"dataset_inventory.csv",index=False)
    pd.DataFrame([{"detected_channels":"C3|Cz|C4"}]).to_csv(base/"tables"/"channel_diagnostics.csv",index=False)
    pd.DataFrame([{"trigger_code":7711,"count":10}]).to_csv(base/"tables"/"trigger_summary.csv",index=False)
    (base/"figures"/"mrcp_grand_average.png").write_bytes(b"png")
    (base/"logs"/"warnings.txt").write_text("",encoding="utf-8")
    if video_name: (base/"videos"/video_name).write_bytes(video_bytes)
    return base


def test_video_detection_prefers_valid_mp4_then_gif(tmp_path):
    base=_artifacts(tmp_path,"subject04","mrcp_eeg_emg_animation.mp4",b"x"*8)
    gif=base/"videos"/"mrcp_eeg_emg_animation04.gif"; gif.write_bytes(b"g"*2048)
    assert discover_subject_video(base)==gif
    mp4=base/"videos"/"SUBJECT04.mp4"; mp4.write_bytes(b"m"*2048)
    assert discover_subject_video(base)==mp4


def test_rebuild_subjects_and_overview_from_artifacts_only(tmp_path):
    for subject in ("SUBJECT01","SUBJECT03","subject04"):
        _artifacts(tmp_path,subject,f"{subject.upper()}.gif",b"g"*2048)
    result=rebuild_reports(tmp_path)
    assert result["success_count"]==3 and result["failure_count"]==0
    overview=Path(result["overview"]); html=overview.read_text(encoding="utf-8")
    for subject in ("SUBJECT01","SUBJECT03","SUBJECT04"):
        assert subject in html
    for directory in ("SUBJECT01","SUBJECT03","subject04"):
        report=tmp_path/directory/"reports"/"mrcp_report.html"
        text=report.read_text(encoding="utf-8")
        assert "Generated:" in text and "../videos/" in text and "../figures/mrcp_grand_average.png" in text
        assert str(tmp_path) not in text


def test_cli_rebuild_one_subject_does_not_require_data_dir(tmp_path,capsys):
    _artifacts(tmp_path,"subject04","SUBJECT04.gif",b"g"*2048)
    other=_artifacts(tmp_path,"SUBJECT05","SUBJECT05.gif",b"g"*2048)
    (other/"reports"/"mrcp_report.html").write_text("<h1>existing</h1>",encoding="utf-8")
    args=build_parser().parse_args(["--output-dir",str(tmp_path),"--subject","SUBJECT04","--rebuild-reports","--force"])
    assert run(args)==0
    output=capsys.readouterr().out
    assert "Reports rebuilt: 1 succeeded" in output and "SUBJECT04.gif" in output
    overview=(tmp_path/"reports"/"index.html").read_text(encoding="utf-8")
    assert "subject04/reports/mrcp_report.html" in overview
    assert "SUBJECT05/reports/mrcp_report.html" in overview


def test_rebuild_is_logically_idempotent(tmp_path):
    _artifacts(tmp_path,"SUBJECT01","SUBJECT01.gif",b"g"*2048)
    first=rebuild_reports(tmp_path); second=rebuild_reports(tmp_path)
    assert Path(first["reports"][0]["report"])==Path(second["reports"][0]["report"])
    assert second["success_count"]==1


def test_overview_has_dynamic_metrics_and_portable_relative_links(tmp_path):
    for subject in ("SUBJECT01","SUBJECT04","SUBJECT40"):
        _artifacts(tmp_path,subject)
    videos=tmp_path/"videos";videos.mkdir()
    for subject in ("SUBJECT01","SUBJECT04"):
        (videos/f"{subject}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42"+b"x"*2048)
    group=tmp_path/"group_analysis"/"reports"/"group_mrcp_report.html"
    group.parent.mkdir(parents=True);group.write_text("<h1>group</h1>",encoding="utf-8")
    project=tmp_path/"project"/"reports"/"mrcp_report.html"
    project.parent.mkdir(parents=True);project.write_text("<h1>project</h1>",encoding="utf-8")

    result=rebuild_reports(tmp_path)
    html=Path(result["overview"]).read_text(encoding="utf-8")
    assert "MRCP Analysis Summary" in html
    assert 'href="../SUBJECT01/reports/mrcp_report.html"' in html
    assert 'href="../SUBJECT04/reports/mrcp_report.html"' in html
    assert 'href="../SUBJECT40/reports/mrcp_report.html"' in html
    assert 'href="../videos/SUBJECT01.mp4"' in html
    assert 'href="../group_analysis/reports/group_mrcp_report.html"' in html
    assert 'href="../project/reports/mrcp_report.html"' in html
    assert "Subjects" in html and "With reports" in html and "With video" in html
    assert "✓" in html and "—" in html
    assert "file:///" not in html and "file:\\" not in html and "\\SUBJECT" not in html
    assert 'href="SUBJECT01/' not in html
