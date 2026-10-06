"""MNE preprocessing, segment epoching and topography plots. Usage: python flex2_mne_pipeline.py [recording.csv] [--steps notch,filter,car]"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

import numpy as np

import mne

from eeg_states import StateScorer, window_mask
from flex2_export_json import source_stem
from emotivpro_io import (
    STANDARD_EXPORT,
    LINE_FREQ_HZ,
    POW_BANDS,
    BadQualitySegment,
    EmotivProCsvReader,
    EmotivProRecording,
    EmotivProSchemaValidator,
)

mne.set_log_level("ERROR")


EXPORT_DIR = Path(__file__).with_name("exports")

DEFAULT_SOURCE = str(STANDARD_EXPORT / "emotivpro_v2_all_streams_dummy.csv")


def load_flex2(path: str | os.PathLike, montage_name: str = "standard_1005",
               validate: bool = True, strict: bool = True):
    """FLEX 2 recording (EmotivPRO CSV V2) -> ``(raw, recording)``."""
    rec = EmotivProCsvReader.read(path)
    if validate:
        EmotivProSchemaValidator().validate(rec)
    raw = rec.to_mne_raw(montage_name=montage_name, strict=strict)
    return raw, rec


def apply_filter(raw, l_freq=1.0, h_freq=45.0, method="iir", iir_params=None, **kw):
    """Band-pass. The default 1-45 Hz covers theta to gamma of the export."""
    if iir_params is None and method == "iir":
        iir_params = dict(order=4, ftype="butter")
    nyquist = raw.info["sfreq"] / 2.0
    if h_freq is not None and h_freq >= nyquist:
        h_freq = None
    return raw.filter(l_freq=l_freq, h_freq=h_freq, method=method,
                      iir_params=iir_params, picks="eeg", **kw)


def apply_notch(raw, freqs=LINE_FREQ_HZ, **kw):
    """Remove mains hum. Silently skipped above the Nyquist frequency."""
    nyquist = raw.info["sfreq"] / 2.0
    wanted = [f for f in np.atleast_1d(freqs) if f < nyquist]
    if not wanted:
        return raw
    return raw.notch_filter(freqs=wanted, picks="eeg", **kw)


def apply_car(raw, ref_channels="average", projection=False, **kw):
    raw, _ = mne.set_eeg_reference(raw, ref_channels=ref_channels,
                                   projection=projection, **kw)
    return raw


def apply_resample(raw, sfreq, **kw):
    return raw.resample(sfreq=sfreq, **kw)


def apply_pyprep(raw, montage, prep_params=None, random_state=42):
    """Optional PREP pipeline (detect and interpolate bad channels)."""
    from pyprep.prep_pipeline import PrepPipeline
    if prep_params is None:
        prep_params = {"ref_chs": "eeg", "reref_chs": "eeg",
                       "line_freqs": [LINE_FREQ_HZ]}
    prep = PrepPipeline(raw, prep_params, montage, random_state=random_state)
    prep.fit()
    return prep.raw


def preprocess_raw(raw, steps=("notch", "filter", "car"), step_params=None,
                   montage=None):
    step_params = step_params or {}
    for step in steps:
        params = step_params.get(step, {})
        if step == "filter":
            raw = apply_filter(raw, **params)
        elif step == "notch":
            raw = apply_notch(raw, **params)
        elif step == "car":
            raw = apply_car(raw, **params)
        elif step == "resample":
            raw = apply_resample(raw, **params)
        elif step == "pyprep":
            raw = apply_pyprep(raw, montage, **params)
        else:
            raise ValueError(f"Unknown step: {step!r}")
    return raw


def segment_epochs(rec: EmotivProRecording, raw, tmin=0.0, tmax=None,
                   apply_gate=True, min_good_fraction=0.5):
    """Epochs from the labelled segments of a recording."""
    segments = rec.segments()
    if segments.empty:
        raise RuntimeError(f"{rec.path.name}: no segment markers found.")
    gate = rec.quality()["ok"].to_numpy()
    times = rec.times()

    rows, event_id, skipped = [], {}, []
    for _, seg in segments.iterrows():
        if apply_gate:
            inside = (times >= seg["start_s"]) & (times < seg["stop_s"])
            if inside.any() and (gate & inside).sum() / inside.sum() < min_good_fraction:
                skipped.append(f"{seg['label']} "
                               f"({seg['start_s']:.1f}-{seg['stop_s']:.1f} s)")
                continue
        rows.append([int(round(seg["start_s"] * rec.sfreq)), 0,
                     int(seg["value"]) or 1000])
        event_id.setdefault(str(seg["label"]), int(seg["value"]) or 1000)
    if skipped:
        rec.warnings.append(
            f"{rec.path.name}: segments skipped due to the quality gate: "
            f"{', '.join(skipped)}")
    if not rows:
        raise BadQualitySegment(
            f"{rec.path.name}: no segment passes the quality gate.")

    if tmax is None:
        # shortest segment sets the epoch length, minus one sample because MNE includes tmax
        shortest = float((segments["stop_s"] - segments["start_s"]).min())
        tmax = shortest - 1.0 / rec.sfreq
    return mne.Epochs(raw, np.asarray(rows, dtype=int), event_id=event_id,
                      tmin=tmin, tmax=tmax, baseline=None, preload=True,
                      verbose=False)


class Flex2Pipeline:
    """Preprocessing and segment epoching of a FLEX 2 recording."""

    def __init__(self, steps=("notch", "filter", "car"), step_params=None,
                 montage_name="standard_1005", tmin=0.0, tmax=None,
                 validate=True, quality_gate=True, min_good_fraction=0.5):
        self.steps = tuple(steps)
        self.step_params = step_params or {}
        self.montage_name = montage_name
        self.montage = mne.channels.make_standard_montage(montage_name)
        self.tmin, self.tmax = tmin, tmax
        self.validate = validate
        self.quality_gate = quality_gate
        self.min_good_fraction = min_good_fraction

        self.last_recording: EmotivProRecording | None = None
        self.last_raw = None
        self.warnings: list[str] = []

    def process_file(self, path: str | os.PathLike):
        raw, rec = load_flex2(path, self.montage_name, validate=self.validate)
        self.last_recording = rec
        raw = preprocess_raw(raw, self.steps, self.step_params, self.montage)
        self.last_raw = raw
        epochs = segment_epochs(rec, raw, self.tmin, self.tmax,
                                apply_gate=self.quality_gate,
                                min_good_fraction=self.min_good_fraction)
        self.warnings = list(rec.warnings)
        return epochs


def plot_segments(rec: EmotivProRecording, out_png, title: str | None = None,
                  bands: Sequence[str] = tuple(POW_BANDS)):
    """One figure: a row per segment with the topography of every band."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scorer = StateScorer.from_recording(rec)
    segments = rec.segments()
    if segments.empty:
        raise RuntimeError(f"{rec.path.name}: no segments to plot.")
    gate = rec.quality()["ok"].to_numpy()

    sensors = rec.pow_sensors
    info = mne.create_info(list(sensors), sfreq=rec.sfreq, ch_types="eeg")
    info.set_montage(mne.channels.make_standard_montage("standard_1005"),
                     match_case=False, on_missing="ignore")

    rest = StateScorer.baseline_mask(rec)
    band_data, band_base = {}, {}
    for band in bands:
        _, values = rec.bandpower_array(band, sensors)
        band_data[band] = values
        mean = np.nanmean(values[rest], axis=0)
        std = np.nanstd(values[rest], axis=0)
        std = np.where(np.isfinite(std) & (std > 1e-6), std,
                       np.nanstd(values, axis=0))
        band_base[band] = (mean, np.where(np.isfinite(std) & (std > 1e-6), std, 1.0))

    rows, labels = [], []
    for _, seg in segments.iterrows():
        mask = window_mask(rec, seg["start_s"], seg["stop_s"])
        good = mask & gate
        ok = mask.any() and good.sum() / mask.sum() >= 0.5
        entry = {}
        if ok:
            for band in bands:
                mean, std = band_base[band]
                entry[band] = (np.nanmean(band_data[band][good], axis=0) - mean) / std
        rows.append(entry)
        note = ""
        if ok:
            try:
                top = scorer.score_window(rec, seg["start_s"], seg["stop_s"])[0]
                note = f"  ->  {top.label} ({top.score:.0%})" if top.detected else "  ->  -"
            except BadQualitySegment:
                ok = False
        labels.append(f"{seg['label']}\n{seg['start_s']:.0f}-{seg['stop_s']:.0f} s"
                      + ("" if ok else "\nquality gate failed") + note)

    limit = max((np.nanmax(np.abs(v)) for r in rows for v in r.values()), default=1.0)
    limit = float(np.ceil(limit))

    n_rows, n_cols = len(rows), len(bands)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(2.05 * n_cols, 2.25 * n_rows),
                             squeeze=False)
    for i, (entry, label) in enumerate(zip(rows, labels)):
        for j, band in enumerate(bands):
            ax = axes[i][j]
            if band in entry:
                mne.viz.plot_topomap(entry[band], info, axes=ax, show=False,
                                     cmap="RdBu_r", vlim=(-limit, limit),
                                     contours=4, sensors=True)
            else:
                ax.text(0.5, 0.5, "no\ngate", ha="center", va="center",
                        fontsize=8, color="#b03a34", transform=ax.transAxes)
                ax.set_axis_off()
            if i == 0:
                lo, hi = POW_BANDS[band]
                ax.set_title(f"{band}\n{lo:g}-{hi:g} Hz", fontsize=9)
        axes[i][0].set_ylabel(label, fontsize=8, rotation=0, ha="right",
                              va="center", labelpad=8)
        axes[i][0].set_axis_on()
        axes[i][0].set_xticks([]); axes[i][0].set_yticks([])
        for spine in axes[i][0].spines.values():
            spine.set_visible(False)

    mappable = plt.cm.ScalarMappable(
        cmap="RdBu_r", norm=plt.Normalize(vmin=-limit, vmax=limit))
    bar = fig.colorbar(mappable, ax=axes, fraction=0.02, pad=0.02)
    bar.set_label("Band power against rest (z)", fontsize=9)
    fig.suptitle(title or f"FLEX 2 - {rec.title}", fontsize=13, fontweight="bold")

    fig.savefig(out_png, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_png


def run(path, out_png=None, steps=("notch", "filter", "car"), step_params=None):
    pipe = Flex2Pipeline(steps=steps, step_params=step_params)
    epochs = pipe.process_file(path)
    rec = pipe.last_recording

    if not rec.pow_columns:
        # no POW stream: derive band power from the preprocessed signal
        eeg = pipe.last_raw.get_data(picks="eeg").T * 1e6
        rec.derive_bandpower(signal_uv=eeg if len(eeg) == rec.n_samples else None)
        pipe.warnings = list(rec.warnings)

    if out_png is None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out_png = str(EXPORT_DIR / f"{source_stem(Path(path))}_segments.png")
    plot_segments(rec, out_png)

    print(f"{rec.path.name}  ->  {Path(out_png).name}")
    print(f"    {rec.sfreq:g} Hz, {len(rec.sensors)} channels, "
          f"{len(epochs)} of {len(rec.segments())} segments, "
          f"epoch length {epochs.tmax - epochs.tmin:.1f} s")
    for name in epochs.event_id:
        count = len(epochs[name])
        print(f"      - {name}" + ("" if count else "   (no complete epoch)"))
    for warning in pipe.warnings:
        print(f"    ! {warning}")
    return epochs, out_png


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Preprocessing and segment topographies of a FLEX 2 recording.")
    parser.add_argument("paths", nargs="*", default=[DEFAULT_SOURCE],
                        help="EmotivPRO CSV files (V2)")
    parser.add_argument("--steps", default="notch,filter,car",
                        help="comma list: notch,filter,car,resample,pyprep")
    args = parser.parse_args(argv)

    failed = 0
    for path in (args.paths or [DEFAULT_SOURCE]):
        try:
            run(path, steps=tuple(args.steps.split(",")))
        except Exception as exc:
            failed += 1
            print(f"{Path(path).name}: {type(exc).__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
