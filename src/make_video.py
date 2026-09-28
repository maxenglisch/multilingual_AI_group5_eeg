"""Generate a simple EEG activity animation without opening a GUI."""

from pathlib import Path
import warnings

import numpy as np

def _write_video_frames(frames, output_path, fps, imageio_module=None):
    """Write MP4, falling back to GIF; isolated for deterministic testing."""
    if imageio_module is None:
        import imageio.v2 as imageio_module
    path=Path(output_path)
    try:
        imageio_module.mimsave(path,frames,fps=fps)
        return path
    except Exception as exc:
        gif_path=path.with_suffix(".gif")
        warnings.warn(f"MP4 writing failed, writing GIF instead: {exc}")
        imageio_module.mimsave(gif_path,frames,fps=fps)
        return gif_path

def make_eeg_activity_video(raw, output_path, duration=10.0, fps=10):
    """Save an MP4 or GIF with rolling channel activity bars."""
    try:
        import imageio.v2 as imageio
    except ImportError as exc:
        raise ImportError(
            "imageio is required for video generation. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for video generation. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[video] Creating EEG activity video: {path}")

    sfreq = raw.info["sfreq"]
    n_samples = min(int(duration * sfreq), raw.n_times)
    data = raw.get_data()[:, :n_samples]
    frame_step = max(1, int(sfreq / fps))
    window = max(frame_step, int(0.5 * sfreq))
    max_activity = float(np.nanmax(np.abs(data))) if data.size else 1.0
    if not np.isfinite(max_activity) or max_activity == 0:
        max_activity = 1.0

    frames = []
    temp_dir = path.parent / "_video_frames"
    temp_dir.mkdir(exist_ok=True)

    try:
        for frame_idx, end in enumerate(range(window, n_samples + 1, frame_step)):
            chunk = data[:, max(0, end - window) : end]
            activity = np.nanmean(np.abs(chunk), axis=1)
            threshold = np.nanpercentile(activity, 80) if activity.size else 0
            colors = ["#d97706" if val >= threshold else "#2563eb" for val in activity]

            fig, ax = plt.subplots(figsize=(10, 5))
            x = np.arange(len(raw.ch_names))
            ax.vlines(x, 0, activity, color=colors, linewidth=7)
            ax.scatter(x, activity, color=colors, s=22, zorder=3)
            ax.set_xticks(x)
            ax.set_xticklabels(raw.ch_names)
            ax.set_ylim(0, max(max_activity, float(np.nanmax(activity)) * 1.1))
            ax.set_xlabel("Channel")
            ax.set_ylabel("Mean absolute amplitude")
            ax.set_title(f"EEG channel activity, t={end / sfreq:.2f}s")
            ax.grid(True, axis="y", alpha=0.25)
            fig.tight_layout()

            frame_path = temp_dir / f"frame_{frame_idx:04d}.png"
            fig.savefig(frame_path, dpi=120)
            plt.close(fig)
            frames.append(imageio.imread(frame_path))

        if not frames:
            raise ValueError("Not enough samples to create video frames")

        path = _write_video_frames(frames, path, fps, imageio)
    finally:
        for frame_file in temp_dir.glob("frame_*.png"):
            frame_file.unlink(missing_ok=True)
        temp_dir.rmdir()

    print(f"[video] Saved {path}")
    return path


def make_mrcp_eeg_emg_animation(epochs, output_path, cfg, emg_envelope=None,
                                emg_events=None, emg_sfreq=440.0, fps=8):
    """Create a -2..2 s waveform/topomap/EMG animation and always write GIF."""
    import imageio.v2 as imageio
    from PIL import Image,ImageDraw
    path=Path(output_path); path.parent.mkdir(parents=True,exist_ok=True)
    times=np.asarray(epochs.times); eeg=epochs.get_data(copy=False).mean(axis=0)*1e6
    keep=(times>=cfg["epochs"]["tmin_s"])&(times<=cfg["epochs"]["tmax_s"])
    times=times[keep]; eeg=eeg[:,keep]
    emg_times=None; emg_mean=None
    if emg_envelope is not None and emg_events is not None:
        left=int(round(cfg["epochs"]["tmin_s"]*emg_sfreq)); right=int(round(cfg["epochs"]["tmax_s"]*emg_sfreq)); chunks=[]
        for sample in emg_events[emg_events[:,2]==7711,0]:
            if sample+left>=0 and sample+right<len(emg_envelope): chunks.append(emg_envelope[sample+left:sample+right])
        if chunks:
            emg_mean=np.mean(chunks,axis=0); emg_times=np.arange(right-left)/emg_sfreq+cfg["epochs"]["tmin_s"]
    frame_times=np.linspace(times[0],times[-1],max(16,int((times[-1]-times[0])*fps)))
    coords=np.asarray([ch["loc"][:2] for ch in epochs.info["chs"]],float);coord_scale=max(np.max(np.abs(coords)),.01)
    def line(draw,box,x,y,current,color):
        l,t,r,b=box;y=np.asarray(y);lo,hi=float(np.nanmin(y)),float(np.nanmax(y));hi=hi if hi>lo else lo+1
        points=[(l+(xx-x[0])/(x[-1]-x[0])*(r-l),b-(yy-lo)/(hi-lo)*(b-t)) for xx,yy in zip(x,y)]
        draw.rectangle(box,outline="#94a3b8");draw.line(points,fill=color,width=2);cx=l+(current-x[0])/(x[-1]-x[0])*(r-l);draw.line((cx,t,cx,b),fill="black",width=2)
    frames=[]
    for current in frame_times:
        idx=int(np.argmin(np.abs(times-current)));image=Image.new("RGB",(1200,800),"white");draw=ImageDraw.Draw(image);grand=eeg.mean(axis=0)
        draw.text((40,20),"MRCP waveform (uV)",fill="black");line(draw,(40,60,580,350),times,grand,current,"#2563eb")
        draw.text((750,20),"Scalp activity (uV; standard coordinates)",fill="black");draw.ellipse((720,60,1120,440),outline="black",width=3)
        values=eeg[:,idx];limit=max(np.max(np.abs(values)),1e-9)
        for name,(x,y),value in zip(epochs.ch_names,coords,values):
            px=920+x/coord_scale*170;py=250-y/coord_scale*170;ratio=float(np.clip(value/limit,-1,1));color=(int(255*max(ratio,0)),80,int(255*max(-ratio,0)));draw.ellipse((px-12,py-12,px+12,py+12),fill=color,outline="black");draw.text((px+13,py-8),name,fill="black")
        if emg_mean is not None:draw.text((40,390),"EMG envelope (ADC units)",fill="black");line(draw,(40,430,580,720),emg_times,emg_mean,current,"#dc2626")
        else:draw.text((200,550),"EMG unavailable",fill="black")
        state="preparation" if current<0 else ("movement" if current<cfg["epochs"]["movement_end_s"] else "post-movement")
        draw.text((760,520),f"t = {current:+.2f} s",fill="black");draw.text((760,570),state,fill="#7c3aed");draw.text((760,640),"movement onset = 0 s",fill="black");frames.append(np.asarray(image))
    gif=path.with_suffix(".gif"); imageio.mimsave(gif,frames,fps=fps)
    result=_write_video_frames(frames,path,fps,imageio)
    return result if result.suffix==".mp4" else gif
