"""Score the state definitions in config/states.json against band power.

Each mapping is an (electrode, band, trend) triple. For a window, the band
power of every mapped electrode is expressed as a z-value against a resting
baseline, signed by the expected trend, and averaged over the state. This is
a transparent match against literature signatures, not a trained classifier:
the score says "how well the pattern fits", not "this is the state".
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json

import numpy as np

#: Contribution weight per trend; "asym" is scored at state level.
TREND_WEIGHT = {"up": 1.0, "down": 1.0, "mix": 0.5, "asym": 0.0}
#: z at which a state reaches score 1.0 when nothing stronger is present
Z_FULL_SCALE = 2.0
#: z from which a state counts as detected
Z_DETECT = 1.0
#: minimum number of measurable mappings for a state to count
MIN_MAPPINGS = 2

#: Caveats that follow from a state's definition rather than from a measurement.
BAND_NOTES = {
    "mu": "Mu (8-13 Hz) overlaps posterior alpha: a global alpha drop raises all three motor "
          "states alike. Which side moved is only visible in the C3/C4 comparison "
          "(motor_lateralization.csv).",
    "gamma": "Gamma (30-45 Hz) is dominated by muscle activity with this setup.",
}


class QualityGateError(ValueError):
    """Data present, but too little of it passes the quality gate to score."""


def load_definitions(path):
    """(bands, states) from states.json; states without mappings are skipped."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["bands"], [s for s in payload["states"] if s.get("mappings")]


def definition_notes(state):
    return [BAND_NOTES[band] for band in sorted({m["band"] for m in state["mappings"]}) if band in BAND_NOTES]


@dataclass
class Evidence:
    el: str
    band: str
    trend: str
    value_db: float
    baseline_db: float
    z: float
    contribution: float

    def to_dict(self):
        return {"el": self.el, "band": self.band, "trend": self.trend,
                "value": round(self.value_db, 3), "baseline": round(self.baseline_db, 3),
                "z": round(self.z, 3), "contribution": round(self.contribution, 3)}


@dataclass
class StateScore:
    id: str
    label: str
    score: float
    z: float
    detected: bool
    n_mappings: int
    n_available: int
    evidence: list = field(default_factory=list)
    asymmetry: float | None = None
    notes: list = field(default_factory=list)

    def to_dict(self):
        out = {"id": self.id, "label": self.label, "score": round(self.score, 3),
               "z": round(self.z, 3), "detected": bool(self.detected),
               "coverage": [self.n_available, self.n_mappings],
               "evidence": [e.to_dict() for e in self.evidence]}
        if self.asymmetry is not None:
            out["asymmetry"] = round(self.asymmetry, 3)
        if self.notes:
            out["notes"] = self.notes
        return out


class StateScorer:
    """Compares band-power means with the signatures from states.json."""

    def __init__(self, states, baseline, z_full=Z_FULL_SCALE, z_detect=Z_DETECT):
        self.states = list(states)
        self.baseline = baseline            # (channel, band) -> (mean_db, std_db)
        self.z_full, self.z_detect = z_full, z_detect

    @classmethod
    def from_series(cls, series, baseline_mask, states):
        """Baseline mean/std per (channel, band) over the good frames in ``baseline_mask``."""
        mask = baseline_mask & series.frame_ok
        if mask.sum() < 2:
            raise QualityGateError(
                f"only {int(mask.sum())} of {int(baseline_mask.sum())} resting frames pass the quality gate "
                f"({series.frame_ok.mean():.0%} of all frames) - no usable baseline, recording skipped")
        stats = {}
        for band, values in series.power_db.items():
            window = values[mask]
            mean = np.nanmean(window, axis=0)
            std = np.nanstd(window, axis=0)
            # A short, very even rest window can have near-zero spread, which
            # would drive every z-value towards infinity.
            fallback = np.nanstd(values[series.frame_ok], axis=0)
            std = np.where(np.isfinite(std) & (std > 1e-6), std, fallback)
            std = np.where(np.isfinite(std) & (std > 1e-6), std, 1.0)
            for i, channel in enumerate(series.channels):
                if np.isfinite(mean[i]):
                    stats[(channel, band)] = (float(mean[i]), float(std[i]))
        return cls(states, stats)

    @staticmethod
    def window_means(series, mask):
        """Mean band power per (channel, band) over the good frames in ``mask``."""
        mask = mask & series.frame_ok
        means = {}
        if not mask.any():
            return means
        for band, values in series.power_db.items():
            window = values[mask]
            finite = np.isfinite(window).any(axis=0)
            avg = np.full(window.shape[1], np.nan)
            avg[finite] = np.nanmean(window[:, finite], axis=0)
            for i, channel in enumerate(series.channels):
                if np.isfinite(avg[i]):
                    means[(channel, band)] = float(avg[i])
        return means

    def score_mask(self, series, mask, sort=True):
        return self.score_from_means(self.window_means(series, mask), sort=sort)

    def score_from_means(self, means, sort=True):
        scores = [self._score_state(state, means) for state in self.states]
        self._normalize(scores)
        if sort:
            scores.sort(key=lambda s: (s.score, s.z), reverse=True)
        return scores

    def _normalize(self, scores):
        """Scale to 0..1 relative to the strongest state once anything crosses z_detect.

        Absolute z-values depend on how quiet the baseline was; for the bars the
        distance between states matters. If nothing crosses the detection
        threshold, scale absolutely against z_full so an uneventful window
        also looks uneventful.
        """
        peak = max((s.z for s in scores), default=0.0)
        divisor = peak if peak >= self.z_detect else self.z_full
        for s in scores:
            s.score = float(np.clip(s.z / divisor, 0.0, 1.0))
            s.detected = bool(s.z >= self.z_detect and s.score >= 0.5 and s.n_available >= MIN_MAPPINGS)

    def _score_state(self, state, means):
        evidence, notes, contributions = [], [], []
        asym_values, asym_z = {}, {}
        for mapping in state["mappings"]:
            el, band, trend = mapping["el"], mapping["band"], mapping["trend"]
            key = (el, band)
            if key not in means or key not in self.baseline:
                continue
            value = means[key]
            base_mean, base_std = self.baseline[key]
            z = (value - base_mean) / base_std
            if trend == "up":
                contribution = z
            elif trend == "down":
                contribution = -z
            elif trend == "mix":
                contribution = abs(z) * TREND_WEIGHT["mix"]
            else:
                contribution = 0.0
                asym_values[el], asym_z[el] = value, z
            if trend != "asym":
                contributions.append(contribution)
            evidence.append(Evidence(el, band, trend, value, base_mean, z, contribution))

        asymmetry = None
        if asym_values:
            asymmetry, asym_contribution, asym_note = asymmetry_index(asym_values, asym_z)
            if asym_contribution is not None:
                contributions.append(asym_contribution)
            if asym_note:
                notes.append(asym_note)
        notes.extend(definition_notes(state))

        n_mappings, n_available = len(state["mappings"]), len(evidence)
        if n_available < MIN_MAPPINGS:
            notes.append(f"Only {n_available} of {n_mappings} mappings measurable - score not reliable.")
        z_mean = float(np.mean(contributions)) if contributions else 0.0
        return StateScore(state["id"], state["label"], float(np.clip(z_mean / self.z_full, 0, 1)),
                          z_mean, False, n_mappings, n_available,
                          sorted(evidence, key=lambda e: -abs(e.z)), asymmetry, notes)


def asymmetry_index(values, z_values):
    """Frontal alpha asymmetry from the "asym" electrodes of a state.

    Pairs are formed by the digit in the name (F3/F4, AF3/AF4). ``index`` is
    right minus left in dB, proportional to ln(alpha right) - ln(alpha left);
    positive = more alpha right = left hemisphere more active = approach.
    ``contribution`` is the magnitude of the change of that difference against
    rest, in z units like every other contribution, so a head that is already
    asymmetric at rest does not score.
    """
    pairs, z_pairs = [], []
    for name, value in values.items():
        if not name[-1].isdigit() or int(name[-1]) % 2 != 0:
            continue
        left = f"{name[:-1]}{int(name[-1]) - 1}"
        if left in values:
            pairs.append(value - values[left])
            if name in z_values and left in z_values:
                z_pairs.append(z_values[name] - z_values[left])
    if not pairs:
        return None, None, "Asymmetry not computable - no complete electrode pair."
    index = float(np.mean(pairs))
    contribution = abs(float(np.mean(z_pairs))) if z_pairs else 0.0
    direction = "approach / positive affect" if index > 0 else "withdrawal / negative affect"
    return index, contribution, f"Asymmetry index {index:+.2f} dB - {direction}."
