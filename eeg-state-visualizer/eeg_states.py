"""Scores mental states from states.json against EmotivPRO band power (z-score against a rest window)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import numpy as np

from emotivpro_io import (
    POW_BANDS,
    BadQualitySegment,
    EmotivProRecording,
)


UI_BAND_TO_POW: Dict[str, str | None] = {
    "delta": None,
    "theta": "Theta",
    "alpha": "Alpha",
    "mu": "Alpha",
    "smr": "BetaL",
    "lowbeta": "BetaL",
    "highbeta": "BetaH",
    "gamma": "Gamma",
}


# mu and SMR have no EmotivPRO band; scores for them also react to unspecific changes
SUBSTITUTE_BANDS: Dict[str, str] = {"mu": "Alpha", "smr": "BetaL"}


TREND_WEIGHT: Dict[str, float] = {"up": 1.0, "down": 1.0, "mix": 0.5, "asym": 0.0}


Z_FULL_SCALE = 2.0

Z_DETECT = 1.0

MIN_MAPPINGS = 2


PRE_MARKER_REST_MIN_S = 2.0

DEFAULT_STATES_PATH = Path(__file__).with_name("states.json")


BASELINE_LABELS = ("neutral", "neutral_baseline", "baseline", "rest")


def load_states(path: str | Path | None = None) -> List[dict]:
    path = Path(path or DEFAULT_STATES_PATH)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing. The file is the shared definition source of "
            f"Python and eeg_state_playback.html.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [s for s in payload["states"] if s.get("mappings")]


def substitute_band_notes(state: dict) -> List[str]:
    """Caveats that are already part of a state's definition."""
    return [f"{band.upper()} has no band of its own in EmotivPRO and is measured via "
            f"{SUBSTITUTE_BANDS[band]} - the score may respond to changes that are "
            f"not {band}-specific at all."
            for band in sorted({m["band"] for m in state.get("mappings", [])
                                if m["band"] in SUBSTITUTE_BANDS})]


@dataclass
class Evidence:
    """A single electrode/band piece of evidence within a state."""

    el: str
    band: str
    pow_band: str
    trend: str
    value_db: float
    baseline_db: float
    z: float
    contribution: float


@dataclass
class StateScore:
    """Score of a state for one time window."""

    id: str
    label: str
    score: float
    z: float
    detected: bool
    n_mappings: int
    n_available: int
    evidence: List[Evidence] = field(default_factory=list)
    asymmetry: float | None = None
    pm_metric: str | None = None
    pm_value: float | None = None
    notes: List[str] = field(default_factory=list)


class StateScorer:
    """Compares band-power topographies with the signatures from ``states.json``."""

    def __init__(self, states: Sequence[dict], baseline: Dict[tuple[str, str], tuple[float, float]],
                 z_full: float = Z_FULL_SCALE, z_detect: float = Z_DETECT):
        self.states = list(states)
        self.baseline = baseline
        self.z_full = z_full
        self.z_detect = z_detect

    @classmethod
    def from_recording(cls, rec: EmotivProRecording, states: Sequence[dict] | None = None,
                       baseline_window: tuple[float, float] | None = None,
                       states_path: str | Path | None = None) -> "StateScorer":
        """Scorer with rest values from ``rec``."""
        states = list(states) if states is not None else load_states(states_path)
        mask = cls.baseline_mask(rec, baseline_window)
        return cls(states, cls._baseline_stats(rec, mask, states))

    @staticmethod
    def baseline_mask(rec: EmotivProRecording,
                      window: tuple[float, float] | None = None) -> np.ndarray:
        """Samples of all rest segments."""
        good = rec.quality()["ok"].to_numpy()
        if window is not None:
            mask = good & window_mask(rec, *window)
            if mask.sum() >= 8:
                return mask
        segments = rec.segments()
        if not segments.empty:
            rest = np.zeros(rec.n_samples, dtype=bool)
            for _, seg in segments.iterrows():
                if str(seg["label"]).lower().startswith(BASELINE_LABELS):
                    rest |= window_mask(rec, seg["start_s"], seg["stop_s"])
            mask = good & rest
            if mask.sum() >= 8:
                return mask
            first_marker = float(segments["start_s"].min())
            if first_marker >= PRE_MARKER_REST_MIN_S:
                mask = good & window_mask(rec, 0.0, first_marker)
                if mask.sum() >= 8:
                    return mask
        if not good.any():
            raise BadQualitySegment(
                f"{rec.path.name}: not a single sample passes the quality gate - "
                f"there is no usable baseline.")
        return good

    @staticmethod
    def _baseline_stats(rec: EmotivProRecording, mask: np.ndarray,
                        states: Sequence[dict]) -> Dict[tuple[str, str], tuple[float, float]]:
        """Mean and spread per (electrode, POW band) in the rest window."""
        needed = _needed_channels(states)
        stats: Dict[tuple[str, str], tuple[float, float]] = {}
        for pow_band, sensors in needed.items():
            try:
                names, values = rec.bandpower_array(pow_band, sorted(sensors))
            except Exception:
                continue
            window = values[mask]
            if window.size == 0:
                continue
            mean = np.nanmean(window, axis=0)
            std = np.nanstd(window, axis=0)
            # a near-zero spread would give infinite z-scores
            std = np.where(np.isfinite(std) & (std > 1e-6), std,
                           np.nanstd(values, axis=0))
            std = np.where(np.isfinite(std) & (std > 1e-6), std, 1.0)
            for i, sensor in enumerate(names):
                stats[(sensor, pow_band)] = (float(mean[i]), float(std[i]))
        return stats

    def score_window(self, rec: EmotivProRecording, start_s: float, stop_s: float,
                     apply_gate: bool = True,
                     min_good_fraction: float = 0.5) -> List[StateScore]:
        """Score all states for a time window, best score first."""
        mask = window_mask(rec, start_s, stop_s)
        if not mask.any():
            raise BadQualitySegment(
                f"{rec.path.name}: window {start_s:.2f}-{stop_s:.2f} s contains "
                f"no samples.")
        if apply_gate:
            gate = rec.quality()
            good = mask & gate["ok"].to_numpy()
            fraction = good.sum() / mask.sum()
            if fraction < min_good_fraction:
                reasons = (gate.loc[mask & ~gate["ok"], "reason"]
                           .value_counts().to_dict())
                raise BadQualitySegment(
                    f"{rec.path.name}: window {start_s:.2f}-{stop_s:.2f} s passes the "
                    f"quality gate only {fraction:.0%} of the time (minimum "
                    f"{min_good_fraction:.0%}): {reasons}. Do not classify this segment.")
            mask = good
        return self.score_mask(rec, mask)

    def score_mask(self, rec: EmotivProRecording, mask: np.ndarray) -> List[StateScore]:
        return self.score_from_means(self._window_means(rec, mask),
                                     self._pm_means(rec, mask))

    def score_from_means(self, means: Dict[tuple[str, str], float],
                         pm_means: Dict[str, float] | None = None,
                         sort: bool = True) -> List[StateScore]:
        """Score band powers that are already averaged per ``(sensor, POW band)``."""
        scores = [self._score_state(state, means, pm_means or {})
                  for state in self.states]
        self._normalize(scores)
        if sort:
            scores.sort(key=lambda s: (s.score, s.z), reverse=True)
        return scores

    def _normalize(self, scores: List[StateScore]) -> None:
        """Bring the score to 0..1 - relative as soon as anything responds at all."""
        peak = max((s.z for s in scores), default=0.0)
        divisor = peak if peak >= self.z_detect else self.z_full
        for s in scores:
            s.score = float(np.clip(s.z / divisor, 0.0, 1.0))
            s.detected = bool(s.z >= self.z_detect and s.score >= 0.5
                              and s.n_available >= MIN_MAPPINGS)

    def _window_means(self, rec: EmotivProRecording,
                      mask: np.ndarray) -> Dict[tuple[str, str], float]:
        means: Dict[tuple[str, str], float] = {}
        for pow_band, sensors in _needed_channels(self.states).items():
            try:
                names, values = rec.bandpower_array(pow_band, sorted(sensors))
            except Exception:
                continue
            window = values[mask]
            if window.size == 0:
                continue
            avg = np.nanmean(window, axis=0)
            for i, sensor in enumerate(names):
                if np.isfinite(avg[i]):
                    means[(sensor, pow_band)] = float(avg[i])
        return means

    @staticmethod
    def _pm_means(rec: EmotivProRecording, mask: np.ndarray) -> Dict[str, float]:
        try:
            pm = rec.performance_metrics(apply_gate=True)
        except Exception:
            return {}
        out: Dict[str, float] = {}
        for column in pm.columns:
            if column.endswith(".IsActive"):
                continue
            values = pm[column].to_numpy(float)[mask]
            if np.isfinite(values).any():
                out[column] = float(np.nanmean(values))
        return out

    def _score_state(self, state: dict, means: Dict[tuple[str, str], float],
                     pm_means: Dict[str, float]) -> StateScore:
        evidence: List[Evidence] = []
        notes: List[str] = []
        contributions: List[float] = []
        asym_values: Dict[str, float] = {}
        asym_z: Dict[str, float] = {}

        for mapping in state["mappings"]:
            el, ui_band, trend = mapping["el"], mapping["band"], mapping["trend"]
            pow_band = UI_BAND_TO_POW.get(ui_band)
            if pow_band is None:
                notes.append(f"{ui_band.capitalize()} is not exported by EmotivPRO "
                             f"- {el} is not taken into account.")
                continue
            key = (el, pow_band)
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
                asym_values[el] = value
                asym_z[el] = z
            if trend != "asym":
                contributions.append(contribution)
            evidence.append(Evidence(el, ui_band, pow_band, trend,
                                     value, base_mean, z, contribution))

        asymmetry = None
        if asym_values:
            asymmetry, asym_contribution, asym_note = _asymmetry(
                asym_values, asym_z)
            if asym_contribution is not None:
                contributions.append(asym_contribution)
            if asym_note:
                notes.append(asym_note)

        notes.extend(substitute_band_notes(state))

        n_mappings = len(state["mappings"])
        n_available = len(evidence)
        z_mean = float(np.mean(contributions)) if contributions else 0.0

        score = float(np.clip(z_mean / self.z_full, 0.0, 1.0))
        detected = False
        if n_available < MIN_MAPPINGS:
            notes.append(f"Only {n_available} of {n_mappings} mappings measurable - "
                         f"score not reliable.")

        pm_metric = state.get("pm")
        return StateScore(
            id=state["id"], label=state["label"], score=score, z=z_mean,
            detected=detected, n_mappings=n_mappings, n_available=n_available,
            evidence=sorted(evidence, key=lambda e: -abs(e.z)),
            asymmetry=asymmetry, pm_metric=pm_metric,
            pm_value=pm_means.get(pm_metric) if pm_metric else None,
            notes=notes,
        )


def window_mask(rec: EmotivProRecording, start_s: float, stop_s: float) -> np.ndarray:
    times = rec.times()
    return (times >= start_s) & (times < stop_s)


def _needed_channels(states: Iterable[dict]) -> Dict[str, set[str]]:
    """Which ``POW.<Sensor>.<Band>`` columns the definitions need at all."""
    needed: Dict[str, set[str]] = {}
    for state in states:
        for mapping in state.get("mappings", []):
            pow_band = UI_BAND_TO_POW.get(mapping["band"])
            if pow_band in POW_BANDS:
                needed.setdefault(pow_band, set()).add(mapping["el"])
    return needed


def _asymmetry(values: Dict[str, float], z_values: Dict[str, float]
               ) -> tuple[float | None, float | None, str | None]:
    """Frontal alpha asymmetry from the ``asym`` electrodes of a state."""
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
        return None, None, ("Asymmetry not computable - no complete "
                            "electrode pair.")
    index = float(np.mean(pairs))
    contribution = abs(float(np.mean(z_pairs))) if z_pairs else 0.0
    direction = ("approach / positive affect" if index > 0
                 else "withdrawal / negative affect")
    return index, contribution, f"Asymmetry index {index:+.2f} dB - {direction}."


__all__ = [
    "Evidence", "StateScore", "StateScorer", "load_states", "window_mask",
    "UI_BAND_TO_POW", "SUBSTITUTE_BANDS", "substitute_band_notes",
    "Z_FULL_SCALE", "Z_DETECT",
    "DEFAULT_STATES_PATH",
]
