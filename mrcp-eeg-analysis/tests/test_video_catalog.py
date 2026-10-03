import json
from pathlib import Path

from src.merge_003_videos import merge_videos
from src.video_utils import media_is_valid,preferred_video,refresh_video_manifest


def _mp4(path,size=2048): path.write_bytes(b"\x00\x00\x00\x18ftypmp42"+b"x"*(size-12))
def _gif(path,size=2048): path.write_bytes(b"GIF89a"+b"x"*(size-6))


def test_filesystem_manifest_prefers_mp4_and_ignores_stale_json(tmp_path):
    _gif(tmp_path/"SUBJECT01.gif");_mp4(tmp_path/"SUBJECT01.mp4")
    (tmp_path/"SUBJECT02.mp4").write_bytes(b"bad")
    path,payload=refresh_video_manifest(tmp_path)
    assert payload["source_of_truth"]=="filesystem"
    assert payload["subjects"]["SUBJECT01"]["file"]=="SUBJECT01.mp4"
    assert "SUBJECT02" not in payload["subjects"]
    assert preferred_video(tmp_path,"subject01").suffix==".mp4"
    assert json.loads(path.read_text(encoding="utf-8"))["subjects"]["SUBJECT01"]["url"]=="/media/videos/SUBJECT01.mp4"


def test_controlled_merge_copies_valid_newer_and_records_decisions(tmp_path):
    source=tmp_path/"003";target=tmp_path/"002";backup=tmp_path/"backup";source.mkdir();target.mkdir()
    _mp4(source/"SUBJECT01.mp4");_gif(source/"SUBJECT01.gif")
    (source/"SUBJECT02.mp4").write_bytes(b"invalid")
    result=merge_videos(source,target,backup)
    actions={item["file"]:item["action"] for item in result["records"]}
    assert actions=={"SUBJECT01.gif":"copied_new","SUBJECT01.mp4":"copied_new","SUBJECT02.mp4":"rejected_invalid"}
    assert media_is_valid(target/"SUBJECT01.mp4") and (target/"video_manifest.json").exists()


def test_report_rebuild_uses_portable_central_video_url(tmp_path):
    subject=tmp_path/"subject04"
    for folder in ("tables","figures","logs","reports"): (subject/folder).mkdir(parents=True,exist_ok=True)
    import pandas as pd
    pd.DataFrame([{"subject":"SUBJECT04"}]).to_csv(subject/"tables"/"dataset_inventory.csv",index=False)
    pd.DataFrame([{"detected_channels":"C3"}]).to_csv(subject/"tables"/"channel_diagnostics.csv",index=False)
    pd.DataFrame(columns=["trigger_code","count"]).to_csv(subject/"tables"/"trigger_summary.csv",index=False)
    videos=tmp_path/"videos";videos.mkdir();_mp4(videos/"SUBJECT04.mp4")
    from src.report_rebuild import rebuild_subject_report
    rebuild_subject_report(subject,tmp_path)
    html=(subject/"reports"/"mrcp_report.html").read_text(encoding="utf-8")
    assert 'src="../../videos/SUBJECT04.mp4"' in html
    assert "003" not in html
