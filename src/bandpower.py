"""Sliding-window band power and a signal-based quality gate.

Band power is 10*log10 of the mean one-sided power spectral density (uV^2/Hz)
inside each band, from a Hann-windowed FFT per frame. A frame is the window
centred on ``times[i]``. The gate replaces headset contact-quality streams,
which this data does not have: a channel/frame cell is rejected when its
peak-to-peak amplitude is implausible or the channel is flat, and a frame is
rejected when too many of its channels are.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


@dataclass
class BandpowerSeries:
    times: np.ndarray          # frame centres in seconds, shape (n_frames,)
    channels: list[str]
    power_db: dict             # band -> (n_frames, n_channels), NaN where the cell failed the gate
    frame_ok: np.ndarray       # (n_frames,) bool
    bad_fraction: np.ndarray   # (n_frames,) share of rejected channels
    max_ptp_uv: np.ndarray     # (n_frames,) largest peak-to-peak amplitude
    reason: np.ndarray         # (n_frames,) "ok" | "amplitude" | "flat"
    window_s: float
    step_s: float

    def segment_mask(self, start_s, stop_s):
        """Frames whose whole window lies inside [start_s, stop_s]."""
        half = self.window_s / 2.0
        eps = 1e-9
        return (self.times - half >= start_s - eps) & (self.times + half <= stop_s + eps)


def compute_bandpower(raw, bands, window_s, step_s, gate):
    """Band power per frame for every band in ``bands`` ({key: {"lo", "hi"}})."""
    sfreq = float(raw.info["sfreq"])
    data = raw.get_data() * 1e6
    n_win = int(round(window_s * sfreq))
    n_step = max(1, int(round(step_s * sfreq)))
    if data.shape[1] < n_win:
        raise ValueError(f"Recording shorter than one {window_s:g} s window")
    starts = np.arange(0, data.shape[1] - n_win + 1, n_step)
    view = sliding_window_view(data, n_win, axis=1)                       # (ch, samples, n_win), no copy
    taper = np.hanning(n_win)
    scale = sfreq * (taper ** 2).sum()
    freqs = np.fft.rfftfreq(n_win, 1.0 / sfreq)
    masks = {}
    for key, band in bands.items():
        masks[key] = (freqs >= float(band["lo"])) & (freqs < float(band["hi"]))
        if not masks[key].any():
            raise ValueError(f"Band {key} has no frequency bin at {window_s:g} s windows")

    n_frames, n_ch = len(starts), data.shape[0]
    power = {key: np.empty((n_frames, n_ch)) for key in bands}
    ptp, std = np.empty((n_frames, n_ch)), np.empty((n_frames, n_ch))
    for first in range(0, n_frames, 512):                                 # bounded memory on long files
        chunk = slice(first, min(first + 512, n_frames))
        windows = view[:, starts[chunk], :]
        windows = windows - windows.mean(axis=2, keepdims=True)
        ptp[chunk], std[chunk] = np.ptp(windows, axis=2).T, windows.std(axis=2).T
        psd = np.abs(np.fft.rfft(windows * taper, axis=2)) ** 2 / scale
        psd[..., 1:-1] *= 2.0                                             # one-sided
        for key, mask in masks.items():
            power[key][chunk] = psd[..., mask].mean(axis=2).T

    bad_amp = ptp > float(gate["max_ptp_uv"])
    bad_flat = std < float(gate["min_std_uv"])
    bad = bad_amp | bad_flat
    bad_fraction = bad.mean(axis=1)
    frame_ok = bad_fraction <= float(gate["max_bad_channel_fraction"])
    reason = np.where(frame_ok, "ok", np.where(bad_amp.sum(1) >= bad_flat.sum(1), "amplitude", "flat"))

    power_db = {}
    for key, values in power.items():
        values = 10.0 * np.log10(np.maximum(values, 1e-12))
        values[bad] = np.nan
        power_db[key] = values

    times = (starts + n_win / 2.0) / sfreq
    return BandpowerSeries(times, list(raw.ch_names), power_db, frame_ok, bad_fraction,
                           ptp.max(axis=1), reason, float(window_s), n_step / sfreq)
