"""Playback JSON for eeg_zustaende_playback.html (schema eeg-playback/3).

One frame per ``states.playback_step_s``: the band-power frames of the state
analysis are grouped into blocks and averaged, so the head map, the quality
gate and the per-frame state scores all use the numbers the tables are built
from.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .states import definition_notes

SCHEMA = "eeg-playback/3"
DEFAULT_LAYER = "alpha"


def _round(values, digits=3):
    array = np.asarray(values, dtype=float)
    return np.round(np.where(np.isfinite(array), array, 0.0), digits).tolist()


def _blocks(series, playback_step_s):
    size = max(1, int(round(playback_step_s / series.step_s)))
    n = len(series.times) // size
    return [np.arange(i * size, (i + 1) * size) for i in range(n)]


def build_playback(recording, series, scorer, bands, segment_rows, cfg, warnings):
    blocks = _blocks(series, float(cfg["states"]["playback_step_s"]))
    n_frames = len(series.times)
    masks = []
    for block in blocks:
        mask = np.zeros(n_frames, bool)
        mask[block] = True
        masks.append(mask)
    times = np.array([series.times[b].mean() for b in blocks])
    ok = np.array([series.frame_ok[b].mean() >= 0.5 for b in blocks])

    layers = {}
    for key, band in bands.items():
        values = series.power_db[key]
        per_frame = np.full((len(blocks), len(series.channels)), np.nan)
        for i, block in enumerate(blocks):
            good = block[series.frame_ok[block]]
            if len(good):
                window = values[good]
                finite = np.isfinite(window).any(axis=0)
                per_frame[i, finite] = np.nanmean(window[:, finite], axis=0)
        base = [scorer.baseline.get((ch, key), (np.nan, 1.0)) for ch in series.channels]
        z = (per_frame - np.array([b[0] for b in base])) / np.array([b[1] for b in base])
        finite = np.abs(z[np.isfinite(z)])
        limit = max(round(float(np.percentile(finite, 98)), 1), 0.5) if finite.size else 1.0
        layers[key] = {"label": band["label"], "range": band["range"], "color": band["color"],
                       "unit": "z", "vmin": -limit, "vmax": limit, "data": _round(z, 2),
                       "raw_unit": "dB", "baseline_mean": _round([b[0] for b in base], 2),
                       "baseline_std": _round([b[1] for b in base], 3)}

    reasons = []
    for block, good in zip(blocks, ok):
        bad = [r for r in series.reason[block] if r != "ok"]
        reasons.append("ok" if good or not bad else pd.Series(bad).mode().iloc[0])
    gate = cfg["states"]["quality_gate"]
    quality = {"ok": ok.tolist(), "reason": reasons,
               "bad_channel_fraction": _round([series.bad_fraction[b].mean() for b in blocks], 3),
               "max_ptp_uv": _round([series.max_ptp_uv[b].max() for b in blocks], 1),
               "gate": (f"peak-to-peak <= {gate['max_ptp_uv']:g} uV and std >= {gate['min_std_uv']:g} uV "
                        f"per channel; at most {gate['max_bad_channel_fraction']:.0%} rejected channels")}

    state_ids = [s["id"] for s in scorer.states]
    states_by_frame = []
    for mask, good in zip(masks, ok):
        if not good:
            states_by_frame.append([None] * len(state_ids))
            continue
        scores = {s.id: s.score for s in scorer.score_mask(series, mask, sort=False)}
        states_by_frame.append([round(scores.get(sid, 0.0), 3) for sid in state_ids])

    segments = []
    for row in segment_rows:
        entry = {"start": round(row["start_s"], 3), "stop": round(row["stop_s"], 3),
                 "label": row["label"], "quality_ok": bool(row["quality_ok"])}
        if row.get("expected_state"):
            entry["expected_state"] = row["expected_state"]
        if row["quality_ok"]:
            entry["top_state"] = row["top_state"] if row["top_detected"] else None
            entry["top_score"] = row["top_score"]
        segments.append(entry)

    overall = [s.to_dict() for s in scorer.score_mask(series, np.ones(n_frames, bool))]
    raw = recording.raw
    return {
        "schema": SCHEMA,
        "meta": {"title": f"{cfg['dataset'].get('title', cfg['dataset']['name'])} - {recording.key}",
                 "source": recording.source.name, "mode": "bandpower", "unit": "z",
                 "sfreq": float(raw.info["sfreq"]), "headset": cfg["dataset"]["name"],
                 "format": f"{series.window_s:g} s windows", "duration_s": round(raw.times[-1], 3),
                 "n_frames": len(blocks), "n_channels": len(series.channels)},
        "colormap": "RdBu_r",
        "channels": series.channels,
        "times": _round(times, 3),
        "default_layer": DEFAULT_LAYER if DEFAULT_LAYER in layers else next(iter(layers)),
        "layers": layers,
        "quality": quality,
        "segments": segments,
        "detection": {"basis": "band power against the resting sections (z)",
                      "z_full": scorer.z_full, "z_detect": scorer.z_detect},
        "state_ids": state_ids,
        "state_labels": [s["label"] for s in scorer.states],
        "state_notes": [definition_notes(s) for s in scorer.states],
        "states": overall,
        "states_by_frame": states_by_frame,
        "warnings": warnings,
    }


def write_playback(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path
