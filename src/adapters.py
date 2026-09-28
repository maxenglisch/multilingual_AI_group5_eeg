"""Dataset adapters: turn one source recording into the shared Recording form.

Every adapter returns EEG as an MNE Raw in volts (built by
:func:`src.eeg_processing.make_raw`, so channel checks and units stay the
MRCP pipeline's) plus labelled sections. Everything downstream of the
adapter - band power, state scoring, playback export - is dataset-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import logging

import numpy as np
import pandas as pd

from .channel_utils import TriggerOnlyEEGError, detect_eeg_channels
from .config import ROOT
from .data_loader import diagnose_eeg, discover_pairs, inspect_table
from .eeg_processing import make_raw

logger = logging.getLogger(__name__)

SEGMENT_COLUMNS = ["start_s", "stop_s", "label", "expected_state", "baseline", "trial"]


@dataclass
class Recording:
    subject: str
    key: str
    raw: object
    segments: pd.DataFrame
    source: Path
    warnings: list[str] = field(default_factory=list)


def segments_from_events(events, sfreq, definitions):
    """Sections between trigger codes, as configured in states.segments.

    A section opens at a start code and closes at the next stop code. If a
    start code of the same definition appears first, the open section is
    discarded rather than stretched over two trials.
    """
    samples, codes = events[:, 0], events[:, 2]
    rows = []
    for definition in definitions:
        start_codes = {int(c) for c in definition["start"]}
        stop_codes = {int(c) for c in definition["stop"]}
        trial = 0
        for i, code in enumerate(codes):
            if code not in start_codes:
                continue
            for j in range(i + 1, len(codes)):
                if codes[j] in stop_codes:
                    start, stop = samples[i] / sfreq, samples[j] / sfreq
                    if stop - start >= float(definition.get("min_duration_s", 0.0)):
                        trial += 1
                        rows.append({"start_s": float(start), "stop_s": float(stop),
                                     "label": definition["label"],
                                     "expected_state": definition.get("expected_state"),
                                     "baseline": bool(definition.get("baseline", False)),
                                     "trial": trial})
                    break
                if codes[j] in start_codes:
                    break
    frame = pd.DataFrame(rows, columns=SEGMENT_COLUMNS)
    return frame.sort_values("start_s", ignore_index=True)


def segments_from_labels(labels, sfreq, expected, baseline_labels):
    """One section per contiguous run of a per-sample label column."""
    labels = pd.Series(labels).astype(str).reset_index(drop=True)
    change = labels.ne(labels.shift()).to_numpy()
    starts = np.flatnonzero(change)
    stops = np.append(starts[1:], len(labels))
    unknown = sorted(set(labels.iloc[starts]) - set(expected))
    if unknown:
        raise ValueError(f"Labels without an expected_states entry: {unknown}")
    rows, counts = [], {}
    for start, stop in zip(starts, stops):
        label = labels.iloc[start]
        counts[label] = counts.get(label, 0) + 1
        rows.append({"start_s": start / sfreq, "stop_s": stop / sfreq, "label": label,
                     "expected_state": expected[label], "baseline": label in baseline_labels,
                     "trial": counts[label]})
    return pd.DataFrame(rows, columns=SEGMENT_COLUMNS)


class MendeleyMrcpAdapter:
    """Right-hand fist-closure dataset; reuses the MRCP loader unchanged."""

    def __init__(self, cfg, data_dir):
        if not data_dir:
            raise ValueError("--data-dir is required for the mendeley_mrcp dataset")
        self.cfg, self.data_dir = cfg, data_dir

    def subjects(self):
        pairs, _ = discover_pairs(self.data_dir)
        return sorted({pair.subject for pair in pairs})

    def recordings(self, subject):
        pairs, unmatched = discover_pairs(self.data_dir, subject)
        if unmatched:
            logger.warning("Unmatched files for %s: %s", subject, [str(p) for p in unmatched])
        sfreq = float(self.cfg["eeg"]["sampling_rate"])
        for pair in pairs:
            key = f"{pair.subject}_Trial_{pair.session}"
            if not pair.eeg_path:
                yield key, None, f"{key}: no EEG file"
                continue
            try:
                df, diag, events, _rows, _counts, warnings, _fmt = diagnose_eeg(pair.eeg_path, self.cfg)
                raw, absent = make_raw(df, diag, sfreq)
                segments = segments_from_events(events, sfreq, self.cfg["states"]["segments"])
                notes = [f"{key}: {w}" for w in warnings]
                notes += [f"{key}: no standard_1020 coordinate for {name}" for name in absent]
                yield key, Recording(pair.subject, key, raw, segments, Path(pair.eeg_path), notes), None
            except TriggerOnlyEEGError as exc:
                logger.warning("Skipping trigger-only EEG: %s file=%s", key, pair.eeg_path)
                yield key, None, f"{key}: {exc}"
            except Exception as exc:
                logger.exception("Recording failed: %s", key)
                yield key, None, f"{key}: {exc}"


class SyntheticEmotionAdapter:
    """The synthetic demo recording shipped in the repository root."""

    SUBJECT = "SYNTHETIC"

    def __init__(self, cfg, data_dir=None):
        self.cfg = cfg
        self.path = Path(data_dir or ROOT) / cfg["source"]["file"]

    def subjects(self):
        return [self.SUBJECT]

    def recordings(self, subject=None):
        key = self.path.stem
        try:
            df, _metadata = inspect_table(self.path)
            eeg = self.cfg["eeg"]
            diag = detect_eeg_channels(df.columns, int(eeg["expected_channel_count"]))
            if diag["channels"] != list(eeg["channel_names"]):
                raise ValueError(f"Channel order {diag['channels']} differs from config {eeg['channel_names']}")
            sfreq = float(eeg["sampling_rate"])
            raw, absent = make_raw(df, diag, sfreq)
            states = self.cfg["states"]
            segments = segments_from_labels(df[self.cfg["source"]["label_column"]], sfreq,
                                            states["expected_states"], set(states["baseline_labels"]))
            notes = [f"{key}: no standard_1020 coordinate for {name}" for name in absent]
            onsets = df[self.cfg["source"]["trigger_column"]].to_numpy()[
                np.round(segments["start_s"].to_numpy() * sfreq).astype(int)]
            if (onsets == 0).any():
                notes.append(f"{key}: {int((onsets == 0).sum())} label changes without a trigger code")
            yield key, Recording(self.SUBJECT, key, raw, segments, self.path, notes), None
        except Exception as exc:
            logger.exception("Recording failed: %s", key)
            yield key, None, f"{key}: {exc}"


ADAPTERS = {"mendeley_mrcp": MendeleyMrcpAdapter, "synthetic_emotion": SyntheticEmotionAdapter}


def make_adapter(cfg, data_dir):
    return ADAPTERS[cfg["dataset"]["adapter"]](cfg, data_dir)
