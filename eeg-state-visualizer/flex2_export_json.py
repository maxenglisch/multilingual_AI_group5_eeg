"""Creates the playback JSON (eeg-playback/2) for eeg_state_playback.html. Usage: python flex2_export_json.py [recording.csv [output.json]]"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd

from emotivpro_io import (
    STANDARD_EXPORT,
    PM_METRICS,
    POW_BANDS,
    BadQualitySegment,
    EmotivProCsvReader,
    EmotivProRecording,
    EmotivProSchemaValidator,
)
from eeg_states import (UI_BAND_TO_POW, StateScorer, load_states,
                        substitute_band_notes, window_mask)

SCHEMA = "eeg-playback/2"

DEFAULT_SOURCE = str(STANDARD_EXPORT / "emotivpro_v2_all_streams_dummy.csv")


EXPORT_DIR = Path(__file__).with_name("exports")


BAND_LABELS: Dict[str, str] = {
    "Theta": "Theta", "Alpha": "Alpha", "BetaL": "Low Beta",
    "BetaH": "High Beta", "Gamma": "Gamma",
}

BAND_COLORS: Dict[str, str] = {
    "Theta": "#b46bff", "Alpha": "#2dd4bf", "BetaL": "#fbbf24",
    "BetaH": "#f97316", "Gamma": "#f8716a",
}

DEFAULT_LAYER = "Alpha"


def source_stem(path: Path) -> str:
    return path.stem


def _round(values, digits: int = 3):
    """Shorten nested numbers - without it the JSON would be many times larger."""
    array = np.asarray(values, dtype=float)
    array = np.where(np.isfinite(array), array, 0.0)
    return np.round(array, digits).tolist()


def export_bandpower(rec: EmotivProRecording, out_json: Path,
                     n_frames: int = 120, window_s: float | None = None,
                     baseline_window: tuple[float, float] | None = None) -> Path:
    """Band-power course, quality, PM and state scores as JSON."""
    states = load_states()
    scorer = StateScorer.from_recording(rec, states=states,
                                        baseline_window=baseline_window)

    frame_times = np.linspace(0.0, rec.duration_s, n_frames, endpoint=False)
    step = rec.duration_s / n_frames
    half = (window_s if window_s is not None else max(step, 0.5)) / 2.0
    sample_times = rec.times()
    gate = rec.quality()

    sensors = [s for s in rec.pow_sensors if s in rec.sensors] or rec.pow_sensors
    frame_masks = [(sample_times >= t - half) & (sample_times < t + half)
                   for t in frame_times]
    frame_masks = [m if m.any() else window_mask(rec, t, t + step)
                   for m, t in zip(frame_masks, frame_times)]

    layers: Dict[str, dict] = {}
    frame_means: Dict[tuple[str, str], np.ndarray] = {}
    for band in POW_BANDS:
        try:
            names, values = rec.bandpower_array(band, sensors)
        except Exception:
            continue
        per_frame = np.vstack([np.nanmean(values[m], axis=0) for m in frame_masks])
        base_mean = np.array([scorer.baseline.get((s, band), (np.nan, 1.0))[0]
                              for s in names])
        base_std = np.array([scorer.baseline.get((s, band), (np.nan, 1.0))[1]
                             for s in names])
        fallback = np.nanmean(per_frame, axis=0)
        base_mean = np.where(np.isfinite(base_mean), base_mean, fallback)
        base_std = np.where(np.isfinite(base_std) & (base_std > 1e-6), base_std, 1.0)
        z = (per_frame - base_mean) / base_std

        for i, sensor in enumerate(names):
            frame_means[(sensor, band)] = per_frame[:, i]

        limit = float(np.nanpercentile(np.abs(z), 98)) if np.isfinite(z).any() else 1.0
        limit = max(round(limit, 1), 0.5)
        layers[band] = {
            "label": BAND_LABELS.get(band, band),
            "range": f"{POW_BANDS[band][0]:g}-{POW_BANDS[band][1]:g} Hz",
            "color": BAND_COLORS.get(band, "#8b97ac"),
            "unit": "z",
            "vmin": -limit, "vmax": limit,
            "data": _round(z, 2),
            "raw_unit": "dB",
            "baseline_mean": _round(base_mean, 2),
            "baseline_std": _round(base_std, 3),
        }
    if not layers:
        raise BadQualitySegment(
            f"{rec.path.name}: no evaluable band power in POW.*.")

    channels = [s for s in sensors if (s, next(iter(layers))) in frame_means]

    pm_frames: Dict[str, dict] = {}
    try:
        pm = rec.performance_metrics(apply_gate=True)
    except Exception:
        pm = pd.DataFrame()
    for metric in PM_METRICS:
        if metric not in pm.columns:
            continue
        values = pm[metric].to_numpy(float)
        active = pm[f"{metric}.IsActive"].to_numpy(float)
        pm_frames[metric] = {
            "value": [None if not np.isfinite(v) else round(float(v), 3)
                      for v in (_nanmean_frames(values, frame_masks))],
            "active": [int(a >= 0.5) for a in _nanmean_frames(active, frame_masks)],
        }

    ok_frames = [bool(gate["ok"].to_numpy()[m].mean() >= 0.5) for m in frame_masks]
    reason_frames = [_dominant_reason(gate["reason"].to_numpy()[m], ok)
                     for m, ok in zip(frame_masks, ok_frames)]
    quality = {
        "cq_overall": _round(_nanmean_frames(gate["cq_overall"].to_numpy(float), frame_masks), 1),
        "eq_overall": _round(_nanmean_frames(gate["eq_overall"].to_numpy(float), frame_masks), 1),
        "eq_sample_rate": _round(_nanmean_frames(gate["eq_sample_rate"].to_numpy(float), frame_masks), 3),
        "ok": ok_frames,
        "reason": reason_frames,
        "cq_min": 60, "gate": "CQ.Overall >= 60 and EQ.SampleRateQuality != -1",
    }

    state_ids = [s["id"] for s in states]
    scores_by_frame: List[List[float | None]] = []
    for i, ok in enumerate(ok_frames):
        if not ok:
            scores_by_frame.append([None] * len(state_ids))
            continue
        means = {key: float(series[i]) for key, series in frame_means.items()
                 if np.isfinite(series[i])}
        pm_means = {m: v["value"][i] for m, v in pm_frames.items()
                    if v["value"][i] is not None and v["active"][i]}
        frame_scores = {s.id: s.score for s
                        in scorer.score_from_means(means, pm_means, sort=False)}
        scores_by_frame.append([round(frame_scores.get(sid, 0.0), 3)
                                for sid in state_ids])

    segments = _score_segments(rec, scorer)

    payload = {
        "schema": SCHEMA,
        "meta": {
            "title": rec.title,
            "source": rec.path.name,
            "mode": "bandpower",
            "bandpower_source": rec.bandpower_source,
            "unit": "z",
            "sfreq": rec.sfreq,
            "headset": rec.headset,
            "format": rec.format,
            "duration_s": round(rec.duration_s, 3),
            "n_frames": n_frames,
            "n_channels": len(channels),
        },
        "channels": channels,
        "times": _round(frame_times, 3),
        "default_layer": DEFAULT_LAYER if DEFAULT_LAYER in layers else next(iter(layers)),
        "layers": layers,
        "quality": quality,
        "pm": {"unit": "0..1", "note": "Only valid where active = 1.",
               "metrics": pm_frames},
        "segments": segments,
        "detection": {
            "basis": "Band-power topography against rest window (z-score)",
            "z_full": scorer.z_full,
            "z_detect": scorer.z_detect,
            "band_mapping": {k: v for k, v in UI_BAND_TO_POW.items() if v},
        },
        "state_ids": state_ids,
        "state_labels": [s["label"] for s in states],
        "state_notes": [substitute_band_notes(s) for s in states],
        "states_by_frame": scores_by_frame,
        "warnings": rec.warnings,
    }
    _write(payload, out_json)
    _report(rec, payload, out_json)
    return out_json


def _nanmean_frames(values: np.ndarray, masks: Sequence[np.ndarray]) -> np.ndarray:
    out = np.full(len(masks), np.nan)
    for i, mask in enumerate(masks):
        window = values[mask]
        if window.size and np.isfinite(window).any():
            out[i] = np.nanmean(window)
    return out


def _dominant_reason(reasons: np.ndarray, ok: bool) -> str:
    if ok or reasons.size == 0:
        return "ok"
    bad = [r for r in reasons if r != "ok"]
    return pd.Series(bad).mode().iloc[0] if bad else "ok"


def _score_segments(rec: EmotivProRecording, scorer: StateScorer) -> List[dict]:
    """Segment list with - where the quality gate holds - the best state."""
    segments = []
    for _, seg in rec.segments().iterrows():
        entry = {"start": round(float(seg["start_s"]), 3),
                 "stop": round(float(seg["stop_s"]), 3),
                 "value": int(seg["value"]), "label": str(seg["label"]),
                 "quality_ok": True}
        try:
            top = scorer.score_window(rec, seg["start_s"], seg["stop_s"])[0]
            entry["top_state"] = top.id if top.detected else None
            entry["top_score"] = round(top.score, 3)
        except BadQualitySegment as exc:
            entry["quality_ok"] = False
            entry["reason"] = str(exc)
        segments.append(entry)
    return segments


def _write(payload: dict, out_json: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _report(rec: EmotivProRecording, payload: dict, out_json: Path) -> None:
    meta = payload["meta"]
    size_kb = out_json.stat().st_size / 1024
    print(f"{rec.path.name} -> {out_json.name}  ({size_kb:.0f} KB)")
    print(f"    {meta['n_frames']} frames, {meta['n_channels']} channels, "
          f"{meta['sfreq']:g} Hz, {meta['format']}")
    for segment in payload.get("segments", []):
        if not segment["quality_ok"]:
            print(f"    [{segment['start']:.0f}-{segment['stop']:.0f}s] "
                  f"{segment['label']}: skipped (quality gate)")
        else:
            top = segment.get("top_state") or "-"
            print(f"    [{segment['start']:.0f}-{segment['stop']:.0f}s] "
                  f"{segment['label']}: {top} ({segment.get('top_score', 0):.2f})")
    for warning in payload.get("warnings", []):
        print(f"    ! {warning}")


def export(path: str | os.PathLike, out_json: str | os.PathLike | None = None,
           **kwargs) -> Path:
    rec = EmotivProCsvReader.read(path)
    EmotivProSchemaValidator().validate(rec)
    if not rec.pow_columns:
        rec.derive_bandpower()

    if out_json is None:
        out_json = EXPORT_DIR / f"{source_stem(Path(path))}.json"
    return export_bandpower(rec, Path(out_json), **kwargs)


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Creates the playback JSON for eeg_state_playback.html.")
    parser.add_argument("path", nargs="?", default=DEFAULT_SOURCE,
                        help="EmotivPRO CSV (V2)")
    parser.add_argument("out", nargs="?", default=None, help="target JSON")
    parser.add_argument("--frames", type=int, default=120,
                        help="number of frames in the course (default 120)")
    args = parser.parse_args(argv)

    try:
        export(args.path, args.out, n_frames=args.frames)
    except Exception as exc:
        print(f"{Path(args.path).name}: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
