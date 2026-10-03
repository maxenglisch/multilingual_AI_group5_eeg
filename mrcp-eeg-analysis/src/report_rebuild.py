"""Rebuild HTML reports exclusively from existing generated artifacts."""
from __future__ import annotations

from datetime import datetime
import logging
import os
from pathlib import Path

import pandas as pd
from jinja2 import Template

from .report import STYLE, write_report
from .video_utils import preferred_video

logger = logging.getLogger(__name__)
MIN_MEDIA_BYTES = 1024


def relative_url(source_html, target):
    """Return a portable URL from an HTML file to a generated artifact."""
    source_html=Path(source_html); target=Path(target)
    return Path(os.path.relpath(target, start=source_html.parent)).as_posix()


def discover_subject_dirs(output_dir):
    root=Path(output_dir)
    found=[]
    for path in root.iterdir() if root.exists() else []:
        if path.is_dir() and path.name.upper().startswith("SUBJECT") and path.name[7:].isdigit():
            found.append(path)
    return sorted(found,key=lambda p:int(p.name[7:]))


def discover_subject_video(subject_dir,output_dir=None):
    subject=Path(subject_dir).name.upper()
    if output_dir:
        central=preferred_video(Path(output_dir)/"videos",subject)
        if central: return central
    videos=Path(subject_dir)/"videos"
    if not videos.exists(): return None
    preferred=[
        videos/f"{subject}.mp4", videos/"mrcp_eeg_emg_animation.mp4", videos/"mrcp_eeg_activity.mp4",
        videos/f"{subject}.gif", videos/"mrcp_eeg_emg_animation.gif", videos/"mrcp_eeg_activity.gif",
    ]
    preferred += sorted(videos.glob("*.mp4")) + sorted(videos.glob("*.gif"))
    seen=set()
    for path in preferred:
        key=str(path).lower()
        if key not in seen and path.exists() and path.stat().st_size >= MIN_MEDIA_BYTES:
            return path
        seen.add(key)
    return None


def _read_optional(path):
    path=Path(path)
    return pd.read_csv(path) if path.exists() and path.stat().st_size else pd.DataFrame()


def rebuild_subject_report(subject_dir,output_dir=None):
    subject_dir=Path(subject_dir); subject_id=subject_dir.name.upper(); tables=subject_dir/"tables"
    inventory=_read_optional(tables/"dataset_inventory.csv")
    diagnostics=_read_optional(tables/"channel_diagnostics.csv")
    triggers=_read_optional(tables/"trigger_summary.csv")
    warnings_path=subject_dir/"logs"/"warnings.txt"
    warnings=warnings_path.read_text(encoding="utf-8").splitlines() if warnings_path.exists() else []
    overview=f"{len(inventory)} recording keys from current generated analysis artifacts"
    channels="No valid EEG diagnostic available"
    if not diagnostics.empty and "detected_channels" in diagnostics:
        valid=diagnostics["detected_channels"].dropna().astype(str)
        if len(valid): channels=valid.iloc[0]
    trigger_counts={}
    if not triggers.empty and {"trigger_code","count"}.issubset(triggers.columns):
        trigger_counts=triggers.groupby("trigger_code")["count"].sum().to_dict()
    report=subject_dir/"reports"/"mrcp_report.html"
    figures=[]
    titles={"raw_eeg.png":"Raw EEG waveform example","electrode_montage.png":"Electrode montage",
            "mrcp_9_channels.png":"MRCP channel averages","mrcp_grand_average.png":"MRCP grand average",
            "emg_movement_locked.png":"EMG movement-locked response","eeg_emg_alignment.png":"EEG-EMG alignment"}
    for name,title in titles.items():
        image=subject_dir/"figures"/name
        if image.exists(): figures.append((title,relative_url(report,image)))
    output_root=Path(output_dir) if output_dir else subject_dir.parent
    video=discover_subject_video(subject_dir,output_root)
    artifact_files=[p for folder in (subject_dir/"tables",subject_dir/"figures",subject_dir/"videos") if folder.exists() for p in folder.iterdir() if p.is_file()]
    source_timestamp=max((p.stat().st_mtime for p in artifact_files),default=None)
    source_text=datetime.fromtimestamp(source_timestamp).strftime("%Y-%m-%d %H:%M") if source_timestamp else "unknown"
    write_report(report,overview,channels,trigger_counts,warnings,figures,subject_id=subject_id,
                 video_path=video,video_url=relative_url(report,video) if video else None,source_timestamp=source_text)
    logger.info("Rebuilt %s (video=%s)",report.resolve(),video.name if video else "unavailable")
    return {"subject_id":subject_id,"directory":subject_dir,"report":report,"video":video,
            "images":len(figures),"status":"success"}


INDEX_STYLE="""
:root{--paper:#f6f3ec;--ink:#302b27;--muted:#71685f;--line:#ddd5c9;--accent:#8a5d3b;--card:#fffdf9}
*{box-sizing:border-box}body{font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;max-width:1200px;margin:auto;padding:2rem;background:var(--paper);color:var(--ink)}
h1,h2{font-family:Georgia,"Times New Roman",serif;font-weight:600}h1{font-size:2.25rem;margin:.1rem 0}.generated{color:var(--muted);margin:.25rem 0 1.5rem}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.85rem;margin:1.5rem 0}.metric,section{background:var(--card);border:1px solid var(--line);border-radius:6px}
.metric{padding:1rem}.metric .value{display:block;font:600 1.8rem Georgia,serif}.metric .label{color:var(--muted)}section{padding:1.25rem;margin:1.25rem 0}section h2{margin-top:0}
a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:2px}a:hover{color:#633f28}table{border-collapse:collapse;width:100%}th,td{padding:.58rem .65rem;border-bottom:1px solid var(--line);text-align:left}th{font-size:.82rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.available{color:#386641;font-weight:700}.unavailable{color:#9a9188}.empty{color:var(--muted);font-style:italic}@media(max-width:700px){body{padding:1rem}.table-wrap{overflow-x:auto}}
"""

INDEX="""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MRCP Analysis Summary</title><style>{{style}}</style></head><body>
<h1>MRCP Analysis Summary</h1><p class="generated">Generated {{generated}}</p>
<div class="metrics">
<div class="metric"><span class="value">{{metrics.subjects}}</span><span class="label">Subjects</span></div>
<div class="metric"><span class="value">{{metrics.reports}}</span><span class="label">With reports</span></div>
<div class="metric"><span class="value">{{metrics.videos}}</span><span class="label">With video</span></div>
<div class="metric"><span class="value">{{metrics.electrodes}}</span><span class="label">Electrode results</span></div>
<div class="metric"><span class="value">{{metrics.mrcp}}</span><span class="label">MRCP results</span></div>
<div class="metric"><span class="value">{{metrics.group_reports}}</span><span class="label">Group reports</span></div>
</div>
<section><h2>Group reports</h2>{% if group_reports %}<ul>{% for item in group_reports %}<li><a href="{{item.href}}">{{item.label}}</a></li>{% endfor %}</ul>{% else %}<p class="empty">No group reports available</p>{% endif %}</section>
<section><h2>Subjects</h2><div class="table-wrap"><table><thead><tr><th>Subject</th><th>EEG</th><th>MRCP</th><th>Electrodes</th><th>Report</th><th>Video</th><th>Images</th></tr></thead><tbody>
{% for row in rows %}<tr><td>{{row.subject_id}}</td><td class="{{'available' if row.eeg else 'unavailable'}}">{{'✓' if row.eeg else '—'}}</td><td class="{{'available' if row.mrcp else 'unavailable'}}">{{'✓' if row.mrcp else '—'}}</td><td class="{{'available' if row.electrodes else 'unavailable'}}">{{'✓' if row.electrodes else '—'}}</td><td>{% if row.report_href %}<a href="{{row.report_href}}">Open</a>{% else %}<span class="unavailable">—</span>{% endif %}</td><td>{% if row.video_href %}<a href="{{row.video_href}}">Open</a>{% else %}<span class="unavailable">—</span>{% endif %}</td><td>{{row.images}}</td></tr>{% endfor %}
</tbody></table></div></section></body></html>"""


def _subject_availability(directory):
    directory=Path(directory);tables=directory/"tables";figures=directory/"figures"
    inventory=_read_optional(tables/"dataset_inventory.csv")
    diagnostics=_read_optional(tables/"channel_diagnostics.csv")
    features=_read_optional(tables/"mrcp_epoch_features.csv")
    eeg=not inventory.empty or (figures/"raw_eeg.png").is_file()
    mrcp=not features.empty or (figures/"mrcp_grand_average.png").is_file() or (figures/"mrcp_9_channels.png").is_file()
    electrodes=(figures/"electrode_montage.png").is_file()
    if not diagnostics.empty:
        if "eeg_channel_count" in diagnostics:
            electrodes=electrodes or bool(pd.to_numeric(diagnostics["eeg_channel_count"],errors="coerce").fillna(0).gt(0).any())
        elif "detected_channels" in diagnostics:
            electrodes=electrodes or bool(diagnostics["detected_channels"].dropna().astype(str).str.len().gt(0).any())
    return {"eeg":eeg,"mrcp":mrcp,"electrodes":electrodes}


def _summary_reports(root):
    root=Path(root);items=[]
    for folder,prefix in ((root/"group_analysis"/"reports","Group"),(root/"project"/"reports","Project")):
        if not folder.is_dir():continue
        for report in sorted(folder.glob("*.html"),key=lambda item:item.name.lower()):
            words=report.stem.replace("_"," ").strip().title()
            items.append({"path":report,"label":f"{prefix}: {words}"})
    return items


def write_overview(output_dir,results):
    root=Path(output_dir); path=root/"reports"/"index.html"; path.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    for result in results:
        report=Path(result["report"]);video=result.get("video")
        availability=_subject_availability(result["directory"])
        rows.append({**result,**availability,
            "report_href":relative_url(path,report) if report.is_file() else None,
            "video_href":relative_url(path,video) if video and Path(video).is_file() else None})
    reports=_summary_reports(root)
    group_reports=[{"label":item["label"],"href":relative_url(path,item["path"])} for item in reports]
    metrics={"subjects":len(rows),"reports":sum(bool(row["report_href"]) for row in rows),
             "videos":sum(bool(row["video_href"]) for row in rows),
             "electrodes":sum(bool(row["electrodes"]) for row in rows),
             "mrcp":sum(bool(row["mrcp"]) for row in rows),"group_reports":len(group_reports)}
    path.write_text(Template(INDEX).render(style=INDEX_STYLE,generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
                    rows=rows,metrics=metrics,group_reports=group_reports),encoding="utf-8")
    logger.info("Rebuilt overview %s",path.resolve())
    return path


def existing_report_result(directory,output_root):
    directory=Path(directory);report=directory/"reports"/"mrcp_report.html"
    video=discover_subject_video(directory,output_root)
    images=len(list((directory/"figures").glob("*.png"))) if (directory/"figures").exists() else 0
    return {"subject_id":directory.name.upper(),"directory":directory,"report":report,"video":video,
            "images":images,"status":"success" if report.exists() else "missing"}


def rebuild_reports(output_dir,subject=None):
    root=Path(output_dir); dirs=discover_subject_dirs(root)
    if subject:
        wanted=subject.upper(); dirs=[path for path in dirs if path.name.upper()==wanted]
        if not dirs: raise FileNotFoundError(f"No generated artifact directory found for {wanted} under {root.resolve()}")
    if not dirs: raise FileNotFoundError(f"No subject artifact directories found under {root.resolve()}")
    results=[]; failures=[]
    for directory in dirs:
        try: results.append(rebuild_subject_report(directory,root))
        except Exception as exc:
            logger.exception("Report rebuild failed for %s",directory.name); failures.append((directory.name,str(exc)))
    rebuilt={item["subject_id"]:item for item in results}
    overview_results=[rebuilt.get(directory.name.upper()) or existing_report_result(directory,root) for directory in discover_subject_dirs(root)]
    overview=write_overview(root,overview_results)
    return {"reports":results,"overview":overview.resolve(),"success_count":len(results),
            "failure_count":len(failures),"failures":failures}
