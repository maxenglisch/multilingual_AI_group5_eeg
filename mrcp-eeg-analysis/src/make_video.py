from __future__ import annotations

from pathlib import Path
import warnings

import numpy as np

from .video_utils import create_mrcp_animation, save_animation


def _write_video_frames(frames, output_path, fps, imageio_module=None):
    if imageio_module is None:
        import imageio.v2 as imageio_module
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.tmp{path.suffix}")
    try:
        temporary.unlink(missing_ok=True)
        imageio_module.mimsave(temporary, frames, fps=fps)
        if not temporary.exists() or temporary.stat().st_size <= 0:
            raise RuntimeError("MP4 writer produced no data")
        temporary.replace(path)
        return path
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        gif_path = path.with_suffix(".gif")
        gif_temporary = gif_path.with_name(f".{gif_path.stem}.tmp.gif")
        warnings.warn(f"MP4 writing failed, writing GIF instead: {exc}", stacklevel=2)
        gif_temporary.unlink(missing_ok=True)
        imageio_module.mimsave(gif_temporary, frames, fps=fps)
        if not gif_temporary.exists() or gif_temporary.stat().st_size <= 0:
            raise RuntimeError("GIF writer produced no data")
        gif_temporary.replace(gif_path)
        return gif_path


def make_eeg_activity_video(*_args, **_kwargs):
    raise RuntimeError(
        "make_eeg_activity_video() is retired. Use `python -m src.video_generator "
        "--data-dir <SUBJECTS> --output-dir outputs --subject SUBJECT01`."
    )


def _movement_locked_emg(emg_envelope, emg_events, emg_sfreq, cfg):
    if emg_envelope is None or emg_events is None:
        return None
    lock = cfg["mrcp"]["lock"]
    spec = cfg["mrcp"][lock]
    event_code = int(spec["event_code"])
    tmin, tmax = float(spec["tmin"]), float(spec["tmax"])
    left, right = int(round(tmin * emg_sfreq)), int(round(tmax * emg_sfreq))
    chunks = []
    for sample in emg_events[emg_events[:, 2] == event_code, 0]:
        start, stop = int(sample + left), int(sample + right)
        if start >= 0 and stop <= len(emg_envelope) and stop > start:
            chunks.append(emg_envelope[start:stop])
    if not chunks:
        return None
    values = np.asarray(chunks, dtype=float).mean(axis=0)
    times = np.arange(values.size, dtype=float) / float(emg_sfreq) + tmin
    return times, values


def make_mrcp_eeg_emg_animation(
    epochs,
    output_path,
    cfg,
    emg_envelope=None,
    emg_events=None,
    emg_sfreq=440.0,
    fps=8,
):
    warnings.warn(
        "make_mrcp_eeg_emg_animation() is deprecated; use src.video_generator.",
        DeprecationWarning,
        stacklevel=2,
    )
    path = Path(output_path)
    subject_id = path.stem.upper() if path.stem.upper().startswith("SUBJECT") else (
        path.parents[1].name.upper() if len(path.parents) > 1 else "SUBJECT"
    )
    emg_trace = _movement_locked_emg(emg_envelope, emg_events, emg_sfreq, cfg)
    animation = fig = None
    try:
        animation, fig, _frames, _duration, _warnings = create_mrcp_animation(
            epochs,
            subject_id=subject_id,
            fps=int(fps),
            mrcp_channels=[str(name) for name in cfg["mrcp"]["channels"]],
            expected_channels=[str(name) for name in cfg["eeg"].get("channel_names", [])],
            emg_trace=emg_trace,
        )
        result, _format, _fallback = save_animation(
            animation,
            path.parent,
            path.stem,
            requested_format="gif" if path.suffix.lower() == ".gif" else "mp4",
            fps=int(fps),
            dpi=100,
        )
        return result
    finally:
        if fig is not None:
            import matplotlib.pyplot as plt
            plt.close(fig)
