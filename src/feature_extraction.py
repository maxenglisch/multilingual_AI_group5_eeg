"""Numerical MRCP and EEG-EMG features driven entirely by dataset.yaml."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _window(times, start, end, include_end=False):
    return (times >= start) & (times <= end if include_end else times < end)


def _mean(data, mask):
    return float(np.nanmean(data[mask])) if mask.any() else np.nan


def extract_mrcp_epoch_features(epochs, subject_id, recording_key, cfg):
    """Return one row per epoch/channel, amplitudes in uV and time in seconds."""
    times = np.asarray(epochs.times)
    data_uv = epochs.get_data(copy=False) * 1e6
    win = cfg["epochs"]
    masks = {
        "baseline": _window(times, win["baseline_start_s"], win["baseline_end_s"]),
        "pre": _window(times, win["pre_start_s"], win["pre_end_s"]),
        "movement": _window(times, win["movement_start_s"], win["movement_end_s"]),
        "post": _window(times, win["post_start_s"], win["post_end_s"], True),
    }
    rows = []
    for epoch_index, epoch in enumerate(data_uv):
        for channel_index, channel in enumerate(epochs.ch_names):
            signal = epoch[channel_index]
            minimum_index = int(np.nanargmin(signal)); maximum_index = int(np.nanargmax(signal))
            pre_t = times[masks["pre"]]; pre_y = signal[masks["pre"]]
            if len(pre_t) >= 2:
                centered = pre_t - pre_t.mean()
                denominator = float(np.sum(centered ** 2))
                slope = float(np.sum(centered * (pre_y - pre_y.mean())) / denominator) if denominator else np.nan
            else:
                slope = np.nan
            pre = _mean(signal, masks["pre"]); post = _mean(signal, masks["post"])
            rows.append({
                "subject_id": subject_id, "recording_key": recording_key,
                "epoch_index": epoch_index, "channel": channel,
                "movement_onset_s": 0.0, "epoch_start_s": float(times[0]),
                "epoch_end_s": float(times[-1]),
                "baseline_mean_uv": _mean(signal, masks["baseline"]),
                "baseline_std_uv": float(np.nanstd(signal[masks["baseline"]], ddof=1 if masks["baseline"].sum()>1 else 0)),
                "pre_movement_mean_uv": pre, "post_movement_mean_uv": post,
                "minimum_amplitude_uv": float(signal[minimum_index]),
                "minimum_latency_s": float(times[minimum_index]),
                "maximum_amplitude_uv": float(signal[maximum_index]),
                "maximum_latency_s": float(times[maximum_index]),
                "pre_movement_slope_uv_per_s": slope,
                "movement_window_mean_uv": _mean(signal, masks["movement"]),
                "post_minus_pre_uv": post - pre, "epoch_valid": True,
            })
    return pd.DataFrame(rows)


def summarize_subject_channels(features):
    columns = ["subject_id", "channel", "valid_epoch_count", "baseline_mean_uv",
               "pre_movement_mean_uv", "movement_mean_uv", "post_movement_mean_uv",
               "mean_minimum_amplitude_uv", "mean_minimum_latency_s",
               "mean_pre_movement_slope_uv_per_s", "mean_post_minus_pre_uv",
               "std_post_minus_pre_uv"]
    if features.empty: return pd.DataFrame(columns=columns)
    valid = features[features["epoch_valid"] == True]
    grouped = valid.groupby(["subject_id", "channel"], as_index=False).agg(
        valid_epoch_count=("epoch_index", "count"), baseline_mean_uv=("baseline_mean_uv", "mean"),
        pre_movement_mean_uv=("pre_movement_mean_uv", "mean"),
        movement_mean_uv=("movement_window_mean_uv", "mean"),
        post_movement_mean_uv=("post_movement_mean_uv", "mean"),
        mean_minimum_amplitude_uv=("minimum_amplitude_uv", "mean"),
        mean_minimum_latency_s=("minimum_latency_s", "mean"),
        mean_pre_movement_slope_uv_per_s=("pre_movement_slope_uv_per_s", "mean"),
        mean_post_minus_pre_uv=("post_minus_pre_uv", "mean"),
        std_post_minus_pre_uv=("post_minus_pre_uv", "std"))
    return grouped[columns]


def subject_weighted_group_timeseries(subject_averages):
    """Average subject-level arrays equally, never pooling epochs across subjects."""
    if not subject_averages: raise ValueError("No subject averages")
    stack = np.stack([np.asarray(value, float) for value in subject_averages.values()])
    return stack.mean(axis=0), stack.std(axis=0, ddof=1) if len(stack) > 1 else np.zeros_like(stack[0])


def detect_emg_onset(envelope, times, cfg):
    """Detect sustained EMG onset relative to trigger; signal stays in ADC units."""
    envelope = np.asarray(envelope, float); times = np.asarray(times, float)
    params = cfg["emg"]["onset"]
    baseline = _window(times, *params["baseline_window_s"], include_end=True)
    search = _window(times, *params["search_window_s"], include_end=True)
    if not baseline.any() or not search.any(): return np.nan
    threshold = np.nanmean(envelope[baseline]) + float(params["threshold_multiplier"]) * np.nanstd(envelope[baseline])
    minimum = max(1, int(round(float(params["minimum_duration_s"]) / np.median(np.diff(times)))))
    indices = np.flatnonzero(search)
    above = envelope[indices] > threshold
    for start in range(0, len(above) - minimum + 1):
        if above[start:start + minimum].all(): return float(times[indices[start]])
    return np.nan


def eeg_emg_latency(eeg_minimum_latency_s, emg_onset_s):
    return float(eeg_minimum_latency_s - emg_onset_s) if np.isfinite(eeg_minimum_latency_s) and np.isfinite(emg_onset_s) else np.nan


def extract_eeg_emg_features(epochs, emg_chunks, emg_times, subject_id, recording_key, cfg):
    rows=[]; eeg_uv=epochs.get_data(copy=False).mean(axis=1)*1e6; win=cfg["epochs"]
    count=min(len(eeg_uv),len(emg_chunks))
    for index in range(count):
        eeg=eeg_uv[index]; minimum=int(np.nanargmin(eeg)); eeg_latency=float(epochs.times[minimum])
        emg=np.asarray(emg_chunks[index]); onset=detect_emg_onset(emg,emg_times,cfg); peak=int(np.nanargmax(emg))
        pre=_window(emg_times,win["pre_start_s"],win["pre_end_s"]); post=_window(emg_times,win["movement_start_s"],win["post_end_s"],True)
        rows.append({"subject_id":subject_id,"recording_key":recording_key,"epoch_index":index,
            "emg_onset_s":onset,"eeg_minimum_latency_s":eeg_latency,
            "eeg_emg_latency_s":eeg_emg_latency(eeg_latency,onset),
            "emg_peak_amplitude":float(emg[peak]),"emg_peak_latency_s":float(emg_times[peak]),
            "emg_mean_activity_pre":_mean(emg,pre),"emg_mean_activity_post":_mean(emg,post),
            "emg_unit":"ADC units",
            "valid_alignment":bool(np.isfinite(onset))})
    return pd.DataFrame(rows)
