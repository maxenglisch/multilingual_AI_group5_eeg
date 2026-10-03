import re
from src.report import write_report

def test_local_report_paths_exist(tmp_path):
    report=tmp_path/"reports"/"mrcp_report.html"; figures=tmp_path/"figures"; tables=tmp_path/"tables"
    figures.mkdir(); tables.mkdir()
    (figures/"x.png").write_bytes(b"png")
    for name in ("dataset_inventory.csv","trigger_summary.csv","mrcp_epoch_features.csv"): (tables/name).write_text("x\n")
    write_report(report,"overview","C3",{7711:1},[],[("x","../figures/x.png")])
    html=report.read_text(encoding="utf-8")
    for path in re.findall(r'(?:src|href)="(\.\./[^\"]+)"',html): assert (report.parent/path).resolve().exists()
