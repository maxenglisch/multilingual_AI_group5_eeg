from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
from dataclasses import dataclass
from typing import Any

VIDEO_RE=re.compile(r"^(SUBJECT\d+)\.(mp4|gif)$",re.I)


def media_is_valid(path,minimum_bytes=1024):
    path=Path(path)
    if not path.is_file() or path.stat().st_size < minimum_bytes: return False
    header=path.read_bytes()[:64]
    if path.suffix.lower()==".gif": return header.startswith((b"GIF87a",b"GIF89a"))
    if path.suffix.lower()==".mp4": return b"ftyp" in header
    return False


def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()


def scan_videos(video_dir):
    root=Path(video_dir); subjects={}
    if not root.exists(): return subjects
    for path in sorted(root.iterdir(),key=lambda p:p.name.lower()):
        match=VIDEO_RE.fullmatch(path.name)
        if not match or not media_is_valid(path): continue
        subject=match.group(1).upper(); fmt=match.group(2).lower()
        subjects.setdefault(subject,{})[fmt]={"file":path.name,"size_bytes":path.stat().st_size,
            "modified_at":datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),
            "sha256":file_sha256(path)}
    return subjects


def refresh_video_manifest(video_dir):
    root=Path(video_dir); root.mkdir(parents=True,exist_ok=True); scanned=scan_videos(root); entries={}
    for subject,formats in scanned.items():
        preferred=formats.get("mp4") or formats.get("gif")
        entries[subject]={"status":"available","file":preferred["file"],"format":Path(preferred["file"]).suffix[1:],
                          "url":f"/media/videos/{preferred['file']}","files":formats}
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"source_of_truth":"filesystem","subjects":entries}
    path=root/"video_manifest.json"; temporary=root/".video_manifest.json.tmp"
    temporary.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8"); temporary.replace(path)
    return path,payload


def preferred_video(video_dir,subject_id):
    subject=subject_id.upper()
    for suffix in (".mp4",".gif"):
        path=Path(video_dir)/f"{subject}{suffix}"
        if media_is_valid(path): return path
    return None


def ffmpeg_available():
    configured=os.environ.get("FFMPEG_BINARY") or os.environ.get("IMAGEIO_FFMPEG_EXE")
    executable=Path(configured) if configured else None
    if executable is not None and executable.is_file():
        import matplotlib
        matplotlib.rcParams["animation.ffmpeg_path"]=str(executable)
    elif shutil.which("ffmpeg") is None:return False
    try:
        from matplotlib.animation import writers
        return bool(writers.is_available("ffmpeg"))
    except Exception:return False


def pillow_available():
    try:
        from matplotlib.animation import PillowWriter
        return bool(PillowWriter.isAvailable())
    except Exception:return False


def _finite_channel_positions(info):
    import numpy as np
    indices=[];positions=[];missing=[]
    for index,channel in enumerate(info["chs"]):
        xy=np.asarray(channel["loc"][:2],dtype=float)
        if xy.shape==(2,) and np.isfinite(xy).all() and float(np.linalg.norm(xy))>1e-12:
            indices.append(index);positions.append(xy.tolist())
        else:missing.append(str(channel["ch_name"]))
    return indices,np.asarray(positions,dtype=float),missing


@dataclass(frozen=True)
class MRCPSignals:
    eeg_uv:Any;mrcp_waveform:Any;all_channel_mean:Any
    available_mrcp_channels:list[str];missing_mrcp_channels:list[str];mrcp_indices:list[int];nonfinite_count:int


def calculate_mrcp_signals(epochs,configured_mrcp_channels):
    import numpy as np
    configured=list(dict.fromkeys(str(name) for name in configured_mrcp_channels if str(name)))
    if not configured:raise ValueError("The configured MRCP channel list is empty")
    epoch_data=np.asarray(epochs.get_data(copy=False),dtype=float)
    if epoch_data.ndim!=3 or epoch_data.shape[0]<=0:raise ValueError(f"Unexpected epoch data shape: {epoch_data.shape}")
    eeg_uv=epoch_data.mean(axis=0)*1e6;nonfinite=int((~np.isfinite(eeg_uv)).sum())
    if nonfinite:eeg_uv=np.nan_to_num(eeg_uv,nan=0.0,posinf=0.0,neginf=0.0)
    names=[str(name) for name in epochs.ch_names]
    if len(names)!=eeg_uv.shape[0]:raise ValueError("EEG channel count and ch_names differ")
    available=[name for name in configured if name in names];missing=[name for name in configured if name not in names]
    if not available:raise ValueError(f"None of the configured MRCP ROI channels exist: {configured}")
    indices=[names.index(name) for name in available]
    return MRCPSignals(eeg_uv,eeg_uv[indices].mean(axis=0),eeg_uv.mean(axis=0),available,missing,indices,nonfinite)


def create_mrcp_animation(epochs,*,subject_id,fps,mrcp_channels,expected_channels=None,emg_trace=None,logger=None):
    import matplotlib
    matplotlib.use("Agg",force=True)
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.animation import FuncAnimation
    log=logger or logging.getLogger(__name__)
    if fps<=0:raise ValueError("FPS must be positive")
    if len(epochs)<=0:raise ValueError("Subject has zero valid MRCP epochs")
    times=np.asarray(epochs.times,dtype=float);signals=calculate_mrcp_signals(epochs,mrcp_channels);eeg_uv=signals.eeg_uv
    names=[str(name) for name in epochs.ch_names];warnings=[]
    if signals.nonfinite_count:warnings.append(f"Replaced {signals.nonfinite_count} non-finite EEG values with zero")
    if expected_channels:
        absent=[name for name in expected_channels if name not in names]
        if absent:warnings.append("Missing expected channels: "+", ".join(absent))
    if signals.missing_mrcp_channels:warnings.append("Missing configured MRCP channels: "+", ".join(signals.missing_mrcp_channels))
    diagnostic={"subject":subject_id,"epochs":len(epochs),"eeg_channel_count":len(names),"channel_names":names,
                "configured_mrcp_channels":list(mrcp_channels),"mrcp_channels_found":signals.available_mrcp_channels,
                "mrcp_channels_missing":signals.missing_mrcp_channels,
                "mrcp_waveform_min_uv":float(np.min(signals.mrcp_waveform)),
                "mrcp_waveform_max_uv":float(np.max(signals.mrcp_waveform)),
                "mrcp_waveform_std_uv":float(np.std(signals.mrcp_waveform)),
                "all_channel_mean_min_uv":float(np.min(signals.all_channel_mean)),
                "all_channel_mean_max_uv":float(np.max(signals.all_channel_mean)),
                "all_channel_mean_std_uv":float(np.std(signals.all_channel_mean)),
                "eeg_overall_std_uv":float(np.std(eeg_uv))}
    log.info("MRCP_DIAGNOSTIC %s",json.dumps(diagnostic,ensure_ascii=False))
    position_indices,positions,position_missing=_finite_channel_positions(epochs.info);use_topomap=len(position_indices)>=3
    if position_missing:warnings.append("Missing electrode coordinates: "+", ".join(position_missing))
    if not use_topomap:warnings.append("Fewer than three usable coordinates; channel scatter fallback used")
    duration=float(times[-1]-times[0]);requested=max(2,int(round(duration*fps))+1)
    frames=np.unique(np.linspace(0,times.size-1,requested,dtype=int));wave=signals.mrcp_waveform
    y_min,y_max=float(np.min(wave)),float(np.max(wave));span=max(y_max-y_min,1e-6);limit=max(float(np.percentile(np.abs(eeg_uv),99)),1e-6)
    fig=plt.figure(figsize=(12,7),constrained_layout=True);grid=fig.add_gridspec(2,2,height_ratios=(1.25,1.0))
    ax_wave=fig.add_subplot(grid[0,0]);ax_topo=fig.add_subplot(grid[:,1]);ax_emg=fig.add_subplot(grid[1,0])
    fig.suptitle(f"{subject_id} · movement-related EEG/EMG",fontsize=15,fontweight="bold")
    ax_wave.plot(times,wave,color="#2563eb",linewidth=2);ax_wave.axvline(0,color="#111827",linestyle="--",alpha=.65)
    marker=ax_wave.axvline(times[0],color="#f05a2a",linewidth=2);ax_wave.set(xlabel="Time from movement onset (s)",ylabel="MRCP (µV)",title="Grand-average MRCP")
    ax_wave.set_xlim(float(times[0]),float(times[-1]));ax_wave.set_ylim(y_min-.12*span,y_max+.12*span);ax_wave.grid(alpha=.2)
    emg_marker=None
    if emg_trace is not None:
        et,ev=np.asarray(emg_trace[0],float),np.asarray(emg_trace[1],float);valid=np.isfinite(et)&np.isfinite(ev);et,ev=et[valid],ev[valid]
        if et.size>=2:
            ax_emg.plot(et,ev,color="#dc2626",linewidth=1.5);ax_emg.axvline(0,color="#111827",linestyle="--",alpha=.65)
            emg_marker=ax_emg.axvline(times[0],color="#f05a2a",linewidth=2);ax_emg.set(xlabel="Time from movement onset (s)",ylabel="Envelope",title="Movement-locked EMG");ax_emg.set_xlim(float(times[0]),float(times[-1]));ax_emg.grid(alpha=.2)
        else:emg_trace=None;warnings.append("EMG trace contained fewer than two finite values")
    if emg_trace is None:ax_emg.text(.5,.5,"EMG unavailable",ha="center",va="center",transform=ax_emg.transAxes);ax_emg.set_title("Movement-locked EMG");ax_emg.set_axis_off()
    state_text=fig.text(.72,.025,"",ha="center",color="#7c3aed",fontsize=11)
    def draw_topomap(sample):
        values=eeg_uv[:,sample];ax_topo.clear();ax_topo.set_title(f"Scalp activity · t={times[sample]:+.2f} s")
        if use_topomap:
            from mne.viz import plot_topomap
            plot_topomap(values[position_indices],positions,axes=ax_topo,show=False,contours=0,sensors=True,
                         names=[names[index] for index in position_indices],cmap="RdBu_r",vlim=(-limit,limit),extrapolate="head")
        else:
            angles=np.linspace(0,2*np.pi,len(values),endpoint=False);x,y=np.cos(angles),np.sin(angles)
            ax_topo.scatter(x,y,c=values,cmap="RdBu_r",vmin=-limit,vmax=limit,s=180,edgecolors="black")
            for px,py,name in zip(x,y,names):ax_topo.text(px,py+.1,name,ha="center",fontsize=7)
            ax_topo.set_aspect("equal");ax_topo.set_axis_off()
    def update(sample):
        current=float(times[sample]);marker.set_xdata([current,current])
        if emg_marker is not None:emg_marker.set_xdata([current,current])
        state="preparation" if current<0 else "movement" if current<=1 else "post-movement"
        state_text.set_text(f"t = {current:+.2f} s  ·  {state}  ·  movement onset = 0 s");draw_topomap(sample);return marker,state_text
    animation=FuncAnimation(fig,update,frames=frames.tolist(),interval=1000/fps,repeat=False,blit=False,cache_frame_data=False)
    for warning in warnings:log.warning("%s: %s",subject_id,warning)
    return animation,fig,int(frames.size),duration,warnings


def save_animation(animation,output_directory,subject_id,*,requested_format,fps,dpi,logger=None):
    from matplotlib.animation import FFMpegWriter,PillowWriter
    log=logger or logging.getLogger(__name__);requested=requested_format.lower()
    if requested not in {"auto","gif","mp4"}:raise ValueError("Video format must be auto, gif, or mp4")
    root=Path(output_directory);root.mkdir(parents=True,exist_ok=True);fallback=None
    if requested in {"auto","mp4"} and ffmpeg_available():
        final=root/f"{subject_id}.mp4";temporary=root/f".{subject_id}.tmp.mp4"
        codec_errors=[]
        # libx264 is preferred. Some valid Windows FFmpeg distributions omit
        # it, so try common H.264 hardware/MediaFoundation writers before the
        # built-in software MPEG-4 encoder and, finally, GIF.
        for codec in ("libx264","h264_nvenc","h264_mf","mpeg4"):
            temporary.unlink(missing_ok=True)
            try:
                animation.save(str(temporary),writer=FFMpegWriter(
                    fps=fps,codec=codec,extra_args=["-pix_fmt","yuv420p"]),dpi=dpi)
                if not temporary.is_file() or temporary.stat().st_size<=0:
                    raise RuntimeError("FFmpeg produced an empty file")
                temporary.replace(final)
                note=None if codec=="libx264" else f"libx264 unavailable; used FFmpeg {codec} encoder"
                if note:log.warning(note)
                return final,"mp4",note
            except Exception as exc:
                temporary.unlink(missing_ok=True);codec_errors.append(f"{codec}: {exc}")
                log.warning("FFmpeg codec %s failed for %s: %s",codec,subject_id,exc)
        fallback="MP4 writer failed: "+" | ".join(codec_errors);log.warning("%s; falling back to GIF",fallback)
    elif requested in {"auto","mp4"}:fallback="FFmpeg unavailable, falling back to GIF";log.warning(fallback)
    if not pillow_available():raise RuntimeError("PillowWriter unavailable"+(f" ({fallback})" if fallback else ""))
    final=root/f"{subject_id}.gif";temporary=root/f".{subject_id}.tmp.gif";temporary.unlink(missing_ok=True)
    try:
        animation.save(str(temporary),writer=PillowWriter(fps=fps),dpi=dpi)
        if not temporary.is_file() or temporary.stat().st_size<=0:raise RuntimeError("PillowWriter produced an empty file")
        temporary.replace(final)
    except Exception:temporary.unlink(missing_ok=True);raise
    return final,"gif",fallback
