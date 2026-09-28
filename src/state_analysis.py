"""Band-power state analysis on top of the MRCP pipeline's loading and CAR.

For every recording: CAR and a 1-45 Hz band-pass (eeg_processing), band power
per frame with a signal-based quality gate (bandpower), a resting baseline
from the sections marked ``baseline``, and the states.json scores for every
labelled section (states). Where configured, the movement-minus-rest change
per hemisphere (motor lateralization) and a playback JSON are written too.
"""
from __future__ import annotations

from pathlib import Path
import logging

import numpy as np
import pandas as pd

from .adapters import make_adapter
from .bandpower import compute_bandpower
from .config import states_definitions_path
from .eeg_processing import preprocess_bandpower
from .playback import build_playback, write_playback
from .states import QualityGateError, StateScorer, load_definitions

logger = logging.getLogger(__name__)


def analyze_recording(recording, cfg, bands, states):
    """Scores, lateralization rows and the frame series for one recording."""
    settings = cfg["states"]
    gate = settings["quality_gate"]
    raw = preprocess_bandpower(recording.raw, cfg)
    series = compute_bandpower(raw, bands, float(settings["window_s"]), float(settings["step_s"]), gate)
    segments = recording.segments
    if segments.empty:
        raise ValueError(f"{recording.key}: no labelled sections")

    baseline = np.zeros(len(series.times), bool)
    for _, seg in segments[segments["baseline"]].iterrows():
        baseline |= series.segment_mask(seg["start_s"], seg["stop_s"])
    scorer = StateScorer.from_series(series, baseline, states)

    rows = []
    state_ids = [s["id"] for s in states]
    for _, seg in segments.iterrows():
        mask = series.segment_mask(seg["start_s"], seg["stop_s"])
        n = int(mask.sum()); good = int((mask & series.frame_ok).sum())
        row = {"subject": recording.subject, "recording_key": recording.key, "label": seg["label"],
               "trial": int(seg["trial"]), "start_s": float(seg["start_s"]), "stop_s": float(seg["stop_s"]),
               "baseline": bool(seg["baseline"]),
               # pandas' string dtype turns None into NaN, which is truthy
               "expected_state": None if pd.isna(seg["expected_state"]) else str(seg["expected_state"]),
               "n_frames": n, "good_frames": good,
               "quality_ok": bool(n and good / n >= float(gate["min_good_frame_fraction"]))}
        if row["quality_ok"]:
            ranking = scorer.score_mask(series, mask)
            top = ranking[0]
            order = [s.id for s in ranking]
            row.update(top_state=top.id, top_score=round(top.score, 3), top_detected=top.detected)
            expected = row["expected_state"]
            if expected:
                hit = next(s for s in ranking if s.id == expected)
                row.update(expected_rank=order.index(expected) + 1, expected_score=round(hit.score, 3),
                           expected_z=round(hit.z, 3), expected_is_top=top.id == expected,
                           expected_detected_top=top.id == expected and top.detected)
            by_id = {s.id: s for s in ranking}
            row.update({f"z_{sid}": round(by_id[sid].z, 3) for sid in state_ids})
        rows.append(row)

    lateral = []
    spec = settings.get("lateralization")
    if spec:
        movement = np.zeros(len(series.times), bool)
        for _, seg in segments[segments["label"] == spec["segment"]].iterrows():
            movement |= series.segment_mask(seg["start_s"], seg["stop_s"])
        movement &= series.frame_ok
        rest = baseline & series.frame_ok
        for band in spec["bands"]:
            values = series.power_db[band]
            for channel in spec["channels"]:
                j = series.channels.index(channel)
                move_db, rest_db = np.nanmean(values[movement, j]), np.nanmean(values[rest, j])
                lateral.append({"subject": recording.subject, "recording_key": recording.key,
                                "band": band, "channel": channel, "movement_frames": int(movement.sum()),
                                "rest_frames": int(rest.sum()), "erd_db": float(move_db - rest_db)})
    return {"series": series, "scorer": scorer, "segments": rows, "lateralization": lateral}


def summarize_segments(segments):
    """Hit rates per section label that has an expected state."""
    frame = pd.DataFrame(segments)
    if frame.empty or "expected_state" not in frame:
        return pd.DataFrame()
    scored = frame[frame["expected_state"].notna()]
    if scored.empty:
        return pd.DataFrame()
    rows = []
    for (label, expected), part in scored.groupby(["label", "expected_state"]):
        ok = part[part["quality_ok"].astype(bool)]
        top = ok["expected_is_top"].astype(bool) if len(ok) else pd.Series(dtype=bool)
        detected = ok["expected_detected_top"].astype(bool) if len(ok) else pd.Series(dtype=bool)
        rows.append({"label": label, "expected_state": expected, "segments": len(part),
                     "quality_ok": len(ok), "expected_is_top": int(top.sum()),
                     "expected_detected_top": int(detected.sum()),
                     "top1_rate": float(top.mean()) if len(ok) else np.nan,
                     "mean_expected_rank": float(pd.to_numeric(ok["expected_rank"]).mean()) if len(ok) else np.nan,
                     "mean_expected_z": float(pd.to_numeric(ok["expected_z"]).mean()) if len(ok) else np.nan})
    return pd.DataFrame(rows)


def top_state_counts(segments):
    frame = pd.DataFrame(segments)
    if frame.empty or "top_state" not in frame:
        return pd.DataFrame()
    ok = frame[frame["quality_ok"].astype(bool)]
    top = ok["top_state"].where(ok["top_detected"].astype(bool), "(none)")
    return pd.crosstab(ok["label"], top).reset_index()


def lateralization_summary(rows, spec):
    """Subject means per band/channel and hemisphere pair, then across subjects.

    The index of a pair is left minus right ERD in dB. For right-hand movement
    a negative index means stronger desynchronisation over the left
    (contralateral) hemisphere.
    """
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(), pd.DataFrame()
    per_subject = frame.groupby(["subject", "band", "channel"], as_index=False)["erd_db"].mean()
    wide = per_subject.pivot_table(index=["subject", "band"], columns="channel", values="erd_db").reset_index()
    for left, right in spec["pairs"]:
        wide[f"{left}-{right}"] = wide[left] - wide[right]
    measures = list(spec["channels"]) + [f"{l}-{r}" for l, r in spec["pairs"]]

    from scipy.stats import ttest_1samp
    rows = []
    for band, part in wide.groupby("band"):
        for measure in measures:
            values = part[measure].dropna().to_numpy()
            if not len(values):
                continue
            test = ttest_1samp(values, 0.0) if len(values) > 1 else None
            rows.append({"band": band, "measure": measure, "kind": "pair" if "-" in measure else "channel",
                         "subjects": len(values), "mean_db": float(values.mean()),
                         "sd_db": float(values.std(ddof=1)) if len(values) > 1 else np.nan,
                         "negative_subjects": int((values < 0).sum()),
                         "t": float(test.statistic) if test else np.nan,
                         "p": float(test.pvalue) if test else np.nan})
    return wide, pd.DataFrame(rows)


def _save_signed_bars(labels, values, title, path):
    """Pillow bar chart around zero; Matplotlib is avoided as in qc.py."""
    from PIL import Image, ImageDraw
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    width, height, top, bottom = 1500, 650, 60, 560
    image = Image.new("RGB", (width, height), "white"); draw = ImageDraw.Draw(image)
    draw.text((50, 20), title, fill="black")
    values = np.nan_to_num(np.asarray(values, float))
    limit = max(float(np.abs(values).max()) if len(values) else 0.0, 1e-6)
    zero = (top + bottom) / 2; half = (bottom - top) / 2
    draw.line((40, zero, width - 20, zero), fill="#52606d")
    step = (width - 80) / max(len(values), 1)
    for i, (label, value) in enumerate(zip(labels, values)):
        x = 50 + i * step; h = value / limit * half
        draw.rectangle((x, min(zero, zero - h), x + max(3, step * .6), max(zero, zero - h)),
                       fill="#2563eb" if value < 0 else "#dc2626")
        draw.text((x, bottom + 15), str(label).replace("SUBJECT", "S"), fill="black")
    draw.text((50, height - 40), f"blue = left < right (contralateral for the right hand); scale +/-{limit:.2f} dB",
              fill="#52606d")
    image.save(path)


REPORT = """<!doctype html><html><head><meta charset="utf-8"><title>State Analysis Report</title><style>{{style}}</style></head><body>
<h1>Band-Power State Analysis</h1><h2>{{title}}</h2>
<section><h2>Overview</h2><p>{{overview}}</p>
<p>Band power from 1 s Hann windows after CAR and a {{bandpass}} Hz band-pass. States are scored as signed z-values against the
resting sections of the same recording (config/states.json). Frames fail the quality gate when {{gate}}.</p></section>
{% if accuracy %}<section><h2>Expected state per section</h2><p>top1_rate: share of quality-checked sections in which the expected
state ranks first among {{n_states}} states. Chance level is 1/{{n_states}}.</p>{{accuracy|safe}}</section>{% endif %}
{% if counts %}<section><h2>Top-ranked state per section label</h2>{{counts|safe}}</section>{% endif %}
{% if lateral %}<section><h2>Motor lateralization (movement minus rest)</h2>
<p>ERD in dB = band power during movement minus rest; negative values mean desynchronisation. Pair rows are left minus right:
for right-hand movement, a negative mean indicates stronger desynchronisation over the left (contralateral) hemisphere.
A consistently positive index would instead point to swapped hemispheres, for example in the column-to-electrode mapping.</p>
{{lateral|safe}}{% for image in images %}<img src="{{image}}" alt="{{image}}">{% endfor %}</section>{% endif %}
<section><h2>Tables</h2><ul>{% for table in tables %}<li><a href="{{table}}">{{table}}</a></li>{% endfor %}</ul></section>
{% if playback %}<section><h2>Playback</h2><p>Load a file from <code>playback/</code> in eeg_zustaende_playback.html (Messung laden).</p></section>{% endif %}
<section><h2>Warnings</h2><ul>{% for w in warnings %}<li class="warn">{{w}}</li>{% endfor %}</ul></section>
<section><h2>Methodology and limitations</h2><p>{{limits}}</p></section></body></html>"""

LIMITS = """The state scores are a transparent comparison with literature signatures, not a trained classifier, and
scores are normalised relative to the other states. The Mendeley MRCP dataset contains right-hand fist closures only; it
cannot validate emotion or cognitive states, only the motor signature and its lateralization. The synthetic dataset is
demonstration data built from the same signatures, so matching it shows that the pipeline runs end to end, not that the
signatures are valid. The valence state scores the magnitude of the asymmetry change, which is positive even for noise,
so it is favoured over signed states when nothing happens. Differences are descriptive; the t-tests across subjects are
uncorrected and exploratory."""


def write_report(out, title, overview, cfg, n_states, accuracy, counts, lateral_stats, images, warnings, playback):
    from jinja2 import Template
    from .report import STYLE
    gate = cfg["states"]["quality_gate"]
    tables = [f"../tables/{p.name}" for p in sorted((out / "tables").glob("*.csv"))]
    lateral_view = lateral_stats
    if not lateral_stats.empty:
        lateral_view = lateral_stats[lateral_stats["kind"] == "pair"].round(3)
    html = Template(REPORT).render(
        style=STYLE, title=title, overview=overview,
        bandpass="-".join(f"{v:g}" for v in cfg["states"]["bandpass"]),
        gate=(f"more than {gate['max_bad_channel_fraction']:.0%} of channels exceed "
              f"{gate['max_ptp_uv']:g} uV peak-to-peak or fall below {gate['min_std_uv']:g} uV standard deviation"),
        n_states=n_states,
        accuracy=accuracy.round(3).to_html(index=False) if not accuracy.empty else "",
        counts=counts.to_html(index=False) if not counts.empty else "",
        lateral=lateral_view.to_html(index=False) if not lateral_stats.empty else "",
        images=images, tables=tables, warnings=warnings, playback=playback, limits=LIMITS)
    path = out / "reports" / "states_report.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def _write_outputs(out, title, cfg, n_states, segments, lateral, warnings, playback, subjects):
    tables = out / "tables"; tables.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(segments).to_csv(tables / "state_segment_scores.csv", index=False)
    accuracy = summarize_segments(segments)
    accuracy.to_csv(tables / "state_accuracy.csv", index=False)
    counts = top_state_counts(segments)
    counts.to_csv(tables / "state_top_counts.csv", index=False)
    spec = cfg["states"].get("lateralization")
    lateral_stats, images = pd.DataFrame(), []
    if spec and lateral:
        pd.DataFrame(lateral).to_csv(tables / "motor_lateralization.csv", index=False)
        wide, lateral_stats = lateralization_summary(lateral, spec)
        wide.to_csv(tables / "motor_lateralization_subjects.csv", index=False)
        lateral_stats.to_csv(tables / "motor_lateralization_summary.csv", index=False)
        left, right = spec["pairs"][0]
        for band in spec["bands"]:
            part = wide[wide["band"] == band]
            name = f"lateralization_{band}_{left}-{right}.png"
            _save_signed_bars(part["subject"], part[f"{left}-{right}"],
                              f"{band}: ERD {left} minus {right} per subject (dB)", out / "figures" / name)
            images.append(f"../figures/{name}")
    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "logs" / "warnings.txt").write_text("\n".join(warnings) + ("\n" if warnings else ""), encoding="utf-8")
    n_ok = sum(1 for s in segments if s["quality_ok"])
    overview = (f"{len(subjects)} subject(s); {len({s['recording_key'] for s in segments})} recordings; "
                f"{len(segments)} labelled sections, {n_ok} pass the quality gate.")
    return write_report(out, title, overview, cfg, n_states, accuracy, counts, lateral_stats, images,
                        warnings, playback)


def run_states(args, cfg):
    """Entry point from src.main; handles one subject, a list, or all subjects."""
    from .main import subject_output_dir
    if getattr(args, "dry_run", False):
        logging.info("Dry run: state analysis skipped")
        return 0
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bands, states = load_definitions(states_definitions_path(cfg))
    adapter = make_adapter(cfg, getattr(args, "data_dir", None))
    if getattr(args, "subject", None):
        subjects = [args.subject.upper()]
    elif getattr(args, "subjects", None):
        subjects = [s.upper() for s in args.subjects]
    else:
        subjects = adapter.subjects()
    playback = getattr(args, "make_playback", None)
    if playback is None:
        playback = len(subjects) == 1
    title = cfg["dataset"].get("title", cfg["dataset"]["name"])
    root = Path(args.output_dir)

    all_segments, all_lateral, all_warnings, failed = [], [], [], []
    for subject in subjects:
        out = subject_output_dir(root, subject) / "states"
        segments, lateral, warnings = [], [], []
        for key, recording, error in adapter.recordings(subject):
            if error:
                warnings.append(error); continue
            warnings.extend(recording.warnings)
            try:
                result = analyze_recording(recording, cfg, bands, states)
            except QualityGateError as exc:
                logger.warning("%s: %s", key, exc)
                warnings.append(f"{key}: {exc}"); continue
            except Exception as exc:
                logger.exception("State analysis failed: %s", key)
                warnings.append(f"{key}: {exc}"); continue
            segments.extend(result["segments"]); lateral.extend(result["lateralization"])
            skipped = [s for s in result["segments"] if not s["quality_ok"]]
            if skipped:
                warnings.append(f"{key}: {len(skipped)} of {len(result['segments'])} sections fail the quality gate")
            if playback:
                payload = build_playback(recording, result["series"], result["scorer"], bands,
                                         result["segments"], cfg, recording.warnings)
                write_playback(payload, out / "playback" / f"{key}.json")
        if not segments:
            failed.append(subject); warnings.append(f"{subject}: no recording could be analysed")
        _write_outputs(out, f"{title} - {subject}", cfg, len(states), segments, lateral, warnings,
                       playback, [subject])
        logging.info("States %s: %d sections, output=%s", subject, len(segments), out)
        all_segments.extend(segments); all_lateral.extend(lateral); all_warnings.extend(warnings)

    if len(subjects) > 1:
        out = root / "group_analysis" / "states"
        report = _write_outputs(out, f"{title} - {len(subjects)} subjects", cfg, len(states), all_segments,
                                all_lateral, all_warnings, False, subjects)
        logging.info("States group report: %s", report)
    return 1 if len(failed) == len(subjects) else 0
