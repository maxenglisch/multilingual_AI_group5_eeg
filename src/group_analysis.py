"""Failure-isolated multi-subject QC, features and equally weighted MRCP."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .channel_utils import TriggerOnlyEEGError
from .data_loader import diagnose_eeg, discover_pairs, inspect_csv
from .eeg_processing import make_raw, preprocess
from .emg_processing import process_emg
from .event_utils import find_trigger_column, parse_triggers
from .feature_extraction import (extract_eeg_emg_features, extract_mrcp_epoch_features,
                                 subject_weighted_group_timeseries, summarize_subject_channels)
from .mrcp_analysis import make_epochs


def discover_subject_ids(data_dir):
    pairs, _ = discover_pairs(data_dir)
    return sorted({pair.subject for pair in pairs if pair.subject.upper().startswith("SUBJECT")})


def execute_subjects(subjects, processor):
    """Run every subject despite exceptions; useful independently and in tests."""
    results = {}
    for subject in subjects:
        try: results[subject] = {"status": "success", "value": processor(subject), "error": ""}
        except Exception as exc: results[subject] = {"status": "failed", "value": None, "error": str(exc)}
    return results


def _emg_epochs(signal, events, sfreq, tmin, tmax):
    left=int(round(tmin*sfreq)); right=int(round(tmax*sfreq)); chunks=[]
    for sample in events[events[:,2]==7711,0]:
        if sample+left>=0 and sample+right<len(signal): chunks.append(signal[sample+left:sample+right])
    return np.asarray(chunks), np.arange(right-left)/sfreq+tmin


def analyze_subject(subject, data_dir, cfg):
    pairs, unmatched = discover_pairs(data_dir, subject)
    feature_frames=[]; latency_frames=[]; recording_rows=[]; epoch_arrays=[]
    times=None; channels=None; total_valid=0; total_dropped=0; warnings=[]; errors=[]
    for pair in pairs:
        key=f"{pair.subject}_Trial_{pair.session}"
        row={"subject_id":subject,"recording_key":key,"eeg_file":str(pair.eeg_path or ""),
             "emg_file":str(pair.emg_path or ""),"eeg_channel_count":0,
             "eeg_sampling_rate":cfg["sampling_rates"]["eeg"],"emg_sampling_rate":cfg["sampling_rates"]["emg"],
             **{f"trigger_{code}_count":0 for code in (768,771,7711,7712,1000,32766)},
             "valid_epoch_count":0,"dropped_epoch_count":0,"status":"missing_eeg" if not pair.eeg_path else "pending","warning":""}
        if not pair.eeg_path:
            recording_rows.append(row); continue
        try:
            df,diag,events,_event_rows,counts,event_warnings,_fmt=diagnose_eeg(pair.eeg_path,cfg)
            row["eeg_channel_count"]=len(diag["channels"])
            for code,count in counts.items():
                if code in (768,771,7711,7712,1000,32766): row[f"trigger_{code}_count"]=count
            raw,_=make_raw(df,diag,float(cfg["sampling_rates"]["eeg"])); _,_,raw_mrcp,_=preprocess(raw,cfg)
            epochs,dropped=make_epochs(raw_mrcp,events,cfg,cfg["mrcp"]["feature_channels"])
            valid=len(epochs); row.update(valid_epoch_count=valid,dropped_epoch_count=dropped,status="success")
            row["warning"]=" | ".join(event_warnings); warnings.extend(event_warnings)
            total_valid+=valid; total_dropped+=dropped
            features=extract_mrcp_epoch_features(epochs,subject,key,cfg); feature_frames.append(features)
            data=epochs.get_data(copy=False)*1e6
            if channels is None: channels=list(epochs.ch_names); times=np.asarray(epochs.times)
            if list(epochs.ch_names)==channels and np.array_equal(epochs.times,times): epoch_arrays.append(data)
            if pair.emg_path:
                emg_df,_sep,_header=inspect_csv(pair.emg_path); trigger=find_trigger_column(emg_df.columns)
                emg_events,_=parse_triggers(emg_df[trigger],float(cfg["sampling_rates"]["emg"]),{int(k):v for k,v in cfg["triggers"].items()})
                signal_cols=[c for c in emg_df.columns if c != trigger]
                if len(signal_cols)==1:
                    values=pd.to_numeric(emg_df[signal_cols[0]],errors="coerce")
                    if not values.isna().any():
                        _r,_f,_rect,envelope=process_emg(values.to_numpy(),float(cfg["sampling_rates"]["emg"]),cfg)
                        chunks,emg_times=_emg_epochs(envelope,emg_events,float(cfg["sampling_rates"]["emg"]),cfg["epochs"]["tmin_s"],cfg["epochs"]["tmax_s"])
                        latency_frames.append(extract_eeg_emg_features(epochs,chunks,emg_times,subject,key,cfg))
        except TriggerOnlyEEGError as exc:
            message="No EEG signal columns; trigger-only file"
            row.update(status="skipped_trigger_only",eeg_channel_count=0,warning=message)
            warnings.append(f"{key}: {message}")
            logging.warning(
                "Skipping trigger-only EEG: subject=%s recording_key=%s file=%s detected_columns=%s",
                subject,key,pair.eeg_path,exc.columns)
        except Exception as exc:
            row.update(status="failed",warning=str(exc)); errors.append(f"{key}: {exc}")
            logging.exception(
                "EEG recording failed: subject=%s recording_key=%s file=%s",
                subject,key,pair.eeg_path)
        recording_rows.append(row)
    features=pd.concat(feature_frames,ignore_index=True) if feature_frames else pd.DataFrame()
    latencies=pd.concat(latency_frames,ignore_index=True) if latency_frames else pd.DataFrame()
    subject_average=np.concatenate(epoch_arrays).mean(axis=0) if epoch_arrays else None
    status="success" if subject_average is not None else "failed"
    if status == "failed" and not errors:
        errors.append("No valid EEG recordings")
    qc={"subject_id":subject,"recording_count":len(pairs),"eeg_file_count":sum(bool(p.eeg_path) for p in pairs),
        "emg_file_count":sum(bool(p.emg_path) for p in pairs),"paired_recording_count":sum(bool(p.eeg_path and p.emg_path) for p in pairs),
        "missing_eeg_count":sum(not p.eeg_path for p in pairs),"missing_emg_count":sum(not p.emg_path for p in pairs),
        "valid_epoch_count":total_valid,"dropped_epoch_count":total_dropped,
        "channel_count":len(channels or []),"eeg_sampling_rate":cfg["sampling_rates"]["eeg"],
        "emg_sampling_rate":cfg["sampling_rates"]["emg"],"processing_status":status,
        "warning_count":len(warnings)+len(errors)+len(unmatched),"error_message":" | ".join(errors)}
    return {"qc":qc,"recordings":recording_rows,"features":features,"latencies":latencies,
            "subject_average":subject_average,"times":times,"channels":channels,"warnings":warnings+errors}


def _save_bar(df,column,title,path):
    from PIL import Image,ImageDraw
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);image=Image.new("RGB",(1500,650),"white");draw=ImageDraw.Draw(image);values=df[column].fillna(0).to_numpy(float);maximum=max(values.max() if len(values) else 0,1);step=1400/max(len(values),1)
    draw.text((50,20),title,fill="black")
    for i,(subject,value) in enumerate(zip(df["subject_id"],values)):
        x=60+i*step;h=value/maximum*500;draw.rectangle((x,560-h,x+max(3,step*.6),560),fill="#2563eb");draw.text((x,570),str(subject).replace("SUBJECT","S"),fill="black")
    image.save(path)


def _save_group_figures(times,channels,mean,std,cfg,figures):
    from .qc import _save_charts
    _save_charts(figures/"group_mrcp_selected_channels.png",[(times,[mean[i] for i in range(len(channels))],"Group MRCP selected channels - subject weighted","Amplitude (uV)")])
    _save_charts(figures/"group_mrcp_grand_average.png",[(times,[mean.mean(axis=0)],"Group MRCP grand average - descriptive, no significance test","Amplitude (uV)")])
    region_series=[]
    for _region,names in cfg["mrcp"]["regions"].items():
        idx=[channels.index(ch) for ch in names if ch in channels]
        if idx:region_series.append(mean[idx].mean(axis=0))
    _save_charts(figures/"group_mrcp_left_vs_midline_vs_right.png",[(times,region_series,"Left vs midline vs right MRCP","Amplitude (uV)")])


def run_group(args, cfg, single_runner):
    root=Path(args.output_dir); group=root/"group_analysis"
    for name in ("figures","tables","reports","logs","videos"): (group/name).mkdir(parents=True,exist_ok=True)
    selected=list(args.subjects or discover_subject_ids(args.data_dir))
    all_results={}
    for subject in selected:
        try:
            child=argparse.Namespace(**vars(args)); child.subject=subject; child.subjects=None; child.all_subjects=False; child.make_video=False
            single_runner(child); all_results[subject]=analyze_subject(subject,args.data_dir,cfg)
        except Exception as exc:
            logging.exception("Subject failed: %s",subject)
            all_results[subject]={"qc":{"subject_id":subject,"recording_count":0,"eeg_file_count":0,"emg_file_count":0,
                "paired_recording_count":0,"missing_eeg_count":0,"missing_emg_count":0,"valid_epoch_count":0,"dropped_epoch_count":0,
                "channel_count":0,"eeg_sampling_rate":cfg["sampling_rates"]["eeg"],"emg_sampling_rate":cfg["sampling_rates"]["emg"],
                "processing_status":"failed","warning_count":1,"error_message":str(exc)},"recordings":[],"features":pd.DataFrame(),
                "latencies":pd.DataFrame(),"subject_average":None,"times":None,"channels":None,"warnings":[str(exc)]}
    qc=pd.DataFrame([r["qc"] for r in all_results.values()]); recordings=pd.DataFrame([x for r in all_results.values() for x in r["recordings"]])
    features=pd.concat([r["features"] for r in all_results.values() if not r["features"].empty],ignore_index=True) if any(not r["features"].empty for r in all_results.values()) else pd.DataFrame()
    latencies=pd.concat([r["latencies"] for r in all_results.values() if not r["latencies"].empty],ignore_index=True) if any(not r["latencies"].empty for r in all_results.values()) else pd.DataFrame()
    qc.to_csv(group/"tables"/"subject_qc_summary.csv",index=False); recordings.to_csv(group/"tables"/"recording_qc_summary.csv",index=False)
    features.to_csv(group/"tables"/"mrcp_epoch_features.csv",index=False); summarize_subject_channels(features).to_csv(group/"tables"/"mrcp_subject_channel_summary.csv",index=False); latencies.to_csv(group/"tables"/"eeg_emg_latency_features.csv",index=False)
    _save_bar(qc,"valid_epoch_count","Valid epochs per subject",group/"figures"/"valid_epochs_per_subject.png")
    _save_bar(qc,"dropped_epoch_count","Dropped epochs per subject",group/"figures"/"dropped_epochs_per_subject.png")
    _save_bar(qc,"recording_count","Recordings per subject",group/"figures"/"recordings_per_subject.png")
    averages={s:r["subject_average"] for s,r in all_results.items() if r["subject_average"] is not None}
    if averages:
        first=next(r for r in all_results.values() if r["subject_average"] is not None); times=first["times"]; channels=first["channels"]
        mean,std=subject_weighted_group_timeseries(averages); sem=std/np.sqrt(len(averages)); rows=[]
        for i,ch in enumerate(channels):
            rows.extend({"time_s":t,"channel":ch,"group_mean_uv":mean[i,j],"group_std_uv":std[i,j],"group_sem_uv":sem[i,j],"subject_count":len(averages)} for j,t in enumerate(times))
        pd.DataFrame(rows).to_csv(group/"tables"/"group_mrcp_timeseries.csv",index=False); _save_group_figures(times,channels,mean,std,cfg,group/"figures")
    else: pd.DataFrame(columns=["time_s","channel","group_mean_uv","group_std_uv","group_sem_uv","subject_count"]).to_csv(group/"tables"/"group_mrcp_timeseries.csv",index=False)
    from .motorik_barchart import generate_motorik_barcharts
    generate_motorik_barcharts(root, update_report=False)
    all_warnings=[w for r in all_results.values() for w in r["warnings"]]
    (group/"logs"/"warnings.txt").write_text(
        "\n".join(all_warnings) + ("\n" if all_warnings else ""), encoding="utf-8")
    from .report import write_group_report
    write_group_report(group/"reports"/"group_mrcp_report.html",qc,recordings,latencies,all_warnings)
    return 0
