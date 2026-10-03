from pathlib import Path
from datetime import datetime
import json
import pandas as pd
from jinja2 import Template

LIMITS = """This is the right-hand fist Movement-Related EEG/EMG dataset and it has no emotion labels.
The system cannot identify emotion, creativity, concentration, nervousness, or sleepiness. A high
amplitude at one electrode does not prove increased brain function; eye movement, EMG, electrode
contact, reference choice, environmental noise, and movement artifact can all contribute. MRCP
interpretation depends on event timing, filtering, baseline correction, trial averaging, artifact
rejection, and cross-subject statistics. This research prototype is not medical diagnosis, and
graphical differences do not imply statistical significance."""

STYLE="""body{font:15px system-ui;max-width:1200px;margin:auto;padding:2rem;color:#17202a}section{margin:1.5rem 0;padding:1rem;border:1px solid #d9e2ec}img{max-width:100%}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border:1px solid #ccd;padding:.3rem}.warn{color:#8a4b00}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}code{word-break:break-all}"""

SINGLE="""<!doctype html><html><head><meta charset="utf-8"><title>{{subject_id}} EEG-EMG MRCP Report</title><style>{{style}}</style></head><body>
<h1>{{subject_id}} EEG-EMG MRCP Analysis Report</h1><h2>Right-Hand Fist Closure Dataset</h2>
<p><b>Generated:</b> {{generated_at}}{% if source_timestamp %} · <b>Analysis artifacts:</b> {{source_timestamp}}{% endif %}</p>
<section><h2>Dataset overview</h2><p>{{overview}}</p><p>EEG 128 Hz, 32 channels, CSV uV converted to MNE V; EMG 440 Hz in ADC units.</p><p><b>EEG channels:</b> {{channels}}</p></section>
<section><h2>Trigger definitions and frequency</h2><p>768 trial start; 771 preparation; 7711 movement start; 7712 movement end; 1000 trial end; 32766 session boundary.</p>{{trigger_plot|safe}}</section>
<section><h2>Recording inventory and numerical features</h2><ul><li><a href="../tables/dataset_inventory.csv">Recording inventory CSV</a></li><li><a href="../tables/trigger_summary.csv">Trigger summary CSV</a></li><li><a href="../tables/mrcp_epoch_features.csv">MRCP feature table</a></li></ul></section>
<div class="grid">{% for title,image in figures %}<section><h2>{{title}}</h2><img src="{{image}}" alt="{{title}}"></section>{% endfor %}</div>
<section><h2>Video</h2>{% if video %}<p>Video file used: <code>{{video_name}}</code></p>{% if video_type == 'video' %}<video controls preload="metadata" style="max-width:100%"><source src="{{video}}"></video>{% else %}<img src="{{video}}" alt="{{subject_id}} animation">{% endif %}{% else %}<p>Video unavailable.</p>{% endif %}</section>
<section><h2>QC warnings</h2><ul>{% for w in warnings %}<li class="warn">{{w}}</li>{% endfor %}</ul></section>
<section><h2>Methodology and limitations</h2><p>{{limits}}</p></section></body></html>"""

def _plotly_trigger(triggers):
    try:
        import plotly.graph_objects as go
        fig=go.Figure(go.Bar(x=[str(k) for k in triggers],y=list(triggers.values())))
        fig.update_layout(title="Trigger frequency",xaxis_title="Trigger code",yaxis_title="Count")
        return fig.to_html(full_html=False,include_plotlyjs="cdn")
    except Exception: return f"<pre>{json.dumps(triggers,indent=2)}</pre>"

def write_report(path,overview,channels,triggers,warnings,figures,subject_id="Subject",video_path=None,video_url=None,generated_at=None,source_timestamp=None):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    video=None; video_name=None; video_type=None
    if video_path:
        video_path=Path(video_path); video=video_url or f"../videos/{video_path.name}"; video_name=video_path.name
        video_type="video" if video_path.suffix.lower()==".mp4" else "image"
    html=Template(SINGLE).render(style=STYLE,overview=overview,channels=channels,trigger_plot=_plotly_trigger(triggers),warnings=warnings,figures=figures,subject_id=subject_id,video=video,video_name=video_name,video_type=video_type,generated_at=generated_at or datetime.now().strftime("%Y-%m-%d %H:%M"),source_timestamp=source_timestamp,limits=LIMITS)
    path.write_text(html,encoding="utf-8")

GROUP="""<!doctype html><html><head><meta charset="utf-8"><title>Group MRCP Report</title><style>{{style}}</style></head><body><h1>Group-Level EEG-EMG MRCP Report</h1>
<section><h2>Overview</h2><p>Total subjects: {{total}}; successful: {{success}}; failed: {{failed}}; recordings: {{recordings}}; valid epochs: {{valid}}; dropped epochs: {{dropped}}.</p></section>
<section><h2>Interactive group MRCP</h2>{{plot|safe}}</section>
<section><h2>Subject QC</h2><label>Subject: <select id="subject-select"><option value="ALL">All</option>{% for s in subjects %}<option value="{{s}}">{{s}}</option>{% endfor %}</select></label>{{qc|safe}}</section>
<div class="grid">{% for image in images %}<section><img src="{{image}}" alt="{{image}}"></section>{% endfor %}</div>
{% if motorik_images %}<section><h2>Motorik frequency analysis</h2>
<p>This dataset contains repeated right-hand fist movements and does not contain multiple emotion classes. “Valid Motor Events per Subject” shows the retained valid movement epochs. “Most Frequently Prominent Channel” counts the channel with the strongest configured MRCP change in each epoch.</p>
<p>This chart counts which motor-related EEG channel showed the strongest configured MRCP change in each valid epoch. It does not directly measure nerve usage or prove localized brain activation. EEG electrodes are not motor nerves, and the left/midline/right grouping describes scalp-channel groups rather than direct brain localization.</p>
<p>These descriptive bars alone do not establish brain-region activation or statistical significance. Results depend on filtering, baseline correction, epoch quality, and the configured metric.</p>
<div class="grid">{% for image in motorik_images %}<section><img src="{{image}}" alt="{{image}}"></section>{% endfor %}</div></section>{% endif %}
<section><h2>Tables</h2><ul>{% for table in tables %}<li><a href="{{table}}">{{table}}</a></li>{% endfor %}</ul></section>
<section><h2>EEG-EMG latency summary</h2>{{latency|safe}}</section><section><h2>Warnings</h2><ul>{% for w in warnings %}<li class="warn">{{w}}</li>{% endfor %}</ul></section>
<section><h2>Methodology and limitations</h2><p>{{limits}}</p></section><script>document.getElementById('subject-select').addEventListener('change',function(){let v=this.value;document.querySelectorAll('#subject-qc tbody tr').forEach(r=>r.style.display=(v==='ALL'||r.cells[0].textContent===v)?'':'none');});</script></body></html>"""

def write_group_report(path,qc,recordings,latencies,warnings):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); root=path.parent.parent
    timeseries=root/"tables"/"group_mrcp_timeseries.csv"; plot="<p>No group timeseries available.</p>"
    if timeseries.exists() and timeseries.stat().st_size:
        try:
            import plotly.graph_objects as go
            ts=pd.read_csv(timeseries); fig=go.Figure()
            channel_names=list(ts.channel.unique())
            for channel in channel_names:
                part=ts[ts.channel==channel];fig.add_trace(go.Scatter(x=part.time_s,y=part.group_mean_uv,name=channel,mode="lines"))
            buttons=[dict(label="All channels",method="update",args=[{"visible":[True]*len(channel_names)}])]
            buttons += [dict(label=channel,method="update",args=[{"visible":[i==index for i in range(len(channel_names))]}]) for index,channel in enumerate(channel_names)]
            fig.update_layout(title="Subject-weighted group MRCP (uV)",xaxis_title="Time (s)",yaxis_title="Amplitude (uV)",updatemenus=[dict(buttons=buttons,direction="down")])
            plot=fig.to_html(full_html=False,include_plotlyjs="cdn")
        except Exception: pass
    images=[f"../figures/{name}" for name in ("valid_epochs_per_subject.png","dropped_epochs_per_subject.png","recordings_per_subject.png","group_mrcp_selected_channels.png","group_mrcp_grand_average.png","group_mrcp_left_vs_midline_vs_right.png") if (root/"figures"/name).exists()]
    motorik_images=[f"../figures/{name}" for name in ("valid_motor_events_per_subject.png","most_frequent_mrcp_channel.png","mrcp_region_frequency.png") if (root/"figures"/name).exists()]
    tables=[f"../tables/{p.name}" for p in sorted((root/"tables").glob("*.csv"))]
    latency=latencies.describe(include="all").to_html() if not latencies.empty else "<p>No valid EEG-EMG alignment features.</p>"
    html=Template(GROUP).render(style=STYLE,total=len(qc),success=int((qc.processing_status=="success").sum()),failed=int((qc.processing_status!="success").sum()),recordings=len(recordings),valid=int(qc.valid_epoch_count.sum()),dropped=int(qc.dropped_epoch_count.sum()),plot=plot,qc=qc.to_html(index=False,table_id="subject-qc"),subjects=qc.subject_id.tolist(),latency=latency,warnings=warnings,images=images,motorik_images=motorik_images,tables=tables,limits=LIMITS)
    path.write_text(html,encoding="utf-8")


def refresh_group_report(path):
    path=Path(path); root=path.parent.parent; tables=root/"tables"
    required=[tables/"subject_qc_summary.csv",tables/"recording_qc_summary.csv"]
    missing=[str(item) for item in required if not item.exists()]
    if missing: raise FileNotFoundError("Cannot refresh group report; missing: " + " | ".join(missing))
    qc=pd.read_csv(required[0]); recordings=pd.read_csv(required[1])
    latency_path=tables/"eeg_emg_latency_features.csv"
    latencies=pd.read_csv(latency_path) if latency_path.exists() and latency_path.stat().st_size else pd.DataFrame()
    warning_path=root/"logs"/"warnings.txt"
    warnings=warning_path.read_text(encoding="utf-8").splitlines() if warning_path.exists() else []
    write_group_report(path,qc,recordings,latencies,warnings)
