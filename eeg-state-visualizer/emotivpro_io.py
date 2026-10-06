"""Reads and validates EmotivPRO CSV V2 exports (all streams or raw EEG only)."""
from __future__ import annotations

import json
import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd


class EmotivProError(ValueError):
    """Base class of all format errors in this module."""


class MissingMetadataError(EmotivProError):
    """Line 1 is missing or contains no usable ``sampling rate``."""


class MissingRequiredColumnError(EmotivProError):
    """A required column is missing."""


class NonNumericDataError(EmotivProError):
    """A numeric channel contains text."""


class BadQualitySegment(EmotivProError):
    """Data is present, but the quality gate was not passed."""


class UnsupportedHeadsetLayoutWarning(UserWarning):
    """Sensor list differs from the 32 FLEX 2 channels of the standard export."""


STANDARD_EXPORT: Path = Path(__file__).resolve().parent.parent / "synthetic_emotivexport"


FLEX2_SENSORS: tuple[str, ...] = (
    "AF3", "AF4", "F3", "F1", "Fz", "F2", "F4",
    "FC3", "FC1", "FCz", "FC2", "FC4",
    "C3", "C1", "Cz", "C2", "C4",
    "CP3", "CP1", "CPz", "CP2", "CP4",
    "P3", "P1", "Pz", "P2", "P4",
    "PO3", "POz", "PO4", "O1", "O2",
)


POW_BANDS: dict[str, tuple[float, float]] = {
    "Theta": (4.0, 8.0),
    "Alpha": (8.0, 12.0),
    "BetaL": (12.0, 16.0),
    "BetaH": (16.0, 25.0),
    "Gamma": (25.0, 45.0),
}


PM_METRICS: tuple[str, ...] = (
    "Engagement", "Excitement", "Stress", "Relaxation", "Interest", "Focus",
)

PM_FIELDS: tuple[str, ...] = ("IsActive", "Scaled", "Raw", "Min", "Max")


LINE_FREQ_HZ = 50.0


NON_SENSOR_EEG_COLUMNS: frozenset[str] = frozenset({
    "EEG.Counter", "EEG.Interpolated", "EEG.RawCq",
    "EEG.Battery", "EEG.BatteryPercent", "EEG.MarkerHardware",
})


CQ_OVERALL_MIN = 60.0
EQ_SAMPLERATE_INVALID = -1.0


STIM_CH = "STI 014"

_META_SFREQ_KEYS = ("samplingrate", "samplerate", "srate", "fs")
_NORM_RE = re.compile(r"[^a-z0-9]")
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")


def _norm_key(key: str) -> str:
    return _NORM_RE.sub("", key.lower())


@dataclass
class EmotivProRecording:
    """A loaded EmotivPRO recording with all of its streams."""

    meta: Dict[str, str]
    df: pd.DataFrame
    sfreq: float
    path: Path
    format: str = "csv_v2"
    warnings: List[str] = field(default_factory=list)

    bandpower_source: str = "emotivpro"

    @property
    def eeg_columns(self) -> List[str]:
        return [c for c in self.df.columns
                if c.startswith("EEG.") and c not in NON_SENSOR_EEG_COLUMNS]

    @property
    def sensors(self) -> List[str]:
        return [c.split(".", 1)[1] for c in self.eeg_columns]

    @property
    def mot_columns(self) -> List[str]:
        return [c for c in self.df.columns if c.startswith("MOT.")]

    @property
    def pow_columns(self) -> List[str]:
        return [c for c in self.df.columns if c.startswith("POW.") and c.count(".") >= 2]

    @property
    def pm_columns(self) -> List[str]:
        return [c for c in self.df.columns if c.startswith("PM.") and c.count(".") >= 2]

    @property
    def pow_sensors(self) -> List[str]:
        seen: List[str] = []
        for c in self.pow_columns:
            sensor = c.split(".")[1]
            if sensor not in seen:
                seen.append(sensor)
        return seen

    @property
    def n_samples(self) -> int:
        return len(self.df)

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.sfreq if self.sfreq else 0.0

    @property
    def title(self) -> str:
        return self.meta.get("title") or self.path.stem

    @property
    def headset(self) -> str:
        return self.meta.get("headset type") or self.meta.get("headset") or "unknown"

    def times(self) -> np.ndarray:
        return np.arange(self.n_samples, dtype=float) / self.sfreq

    def numeric(self, columns: Sequence[str], strict: bool = True) -> pd.DataFrame:
        """Columns as numbers."""
        missing = [c for c in columns if c not in self.df.columns]
        if missing:
            raise MissingRequiredColumnError(
                f"Column(s) missing in {self.path.name}: {missing[:5]}")
        out = self.df[list(columns)].apply(pd.to_numeric, errors="coerce")
        if strict:
            broken = out.isna() & self.df[list(columns)].notna()
            if broken.to_numpy().any():
                col = broken.columns[broken.any()][0]
                row = int(broken[col].to_numpy().argmax())
                raise NonNumericDataError(
                    f"Non-numeric value in {col} at data row {row}: "
                    f"{self.df[col].iloc[row]!r}")
        return out

    def eeg_microvolts(self, strict: bool = True) -> pd.DataFrame:
        cols = self.eeg_columns
        if not cols:
            raise MissingRequiredColumnError(
                f"No EEG.<Sensor> columns found in {self.path.name}.")
        return self.numeric(cols, strict=strict)

    def marker_events(self) -> pd.DataFrame:
        """Marker events as ``sample, value, type, time_s``."""
        empty = pd.DataFrame(columns=["sample", "value", "type", "time_s"])
        if "MarkerValueInt" not in self.df.columns:
            return empty
        raw = pd.to_numeric(self.df["MarkerValueInt"], errors="coerce")
        values = raw.fillna(0.0)
        # only event rows are filled.
        if raw.isna().any():
            is_event = raw.notna()
        else:
            is_event = (values != 0) & (values != values.shift(1, fill_value=0.0))
        idx = np.flatnonzero(is_event.to_numpy())
        if idx.size == 0:
            return empty
        types = (self.df["MarkerType"].iloc[idx].astype(str).to_numpy()
                 if "MarkerType" in self.df.columns
                 else np.array(["marker"] * idx.size))
        return pd.DataFrame({
            "sample": idx.astype(int),
            "value": values.to_numpy()[idx].astype(int),
            "type": types,
            "time_s": idx / self.sfreq,
        })

    def segments(self, sidecar: str | os.PathLike | None = None) -> pd.DataFrame:
        """Labelled segments from markers (+ optional ``markers.json``)."""
        events = self.marker_events()
        if events.empty:
            return pd.DataFrame(columns=["start_s", "stop_s", "value", "label"])

        value_map: Dict[str, str] = {}
        durations: Dict[int, float] = {}
        side = self._resolve_sidecar(sidecar)
        if side is not None:
            value_map = {str(k): str(v) for k, v in (side.get("valueMap") or {}).items()}
            for m in side.get("markers") or []:
                if m.get("durationSec") is not None and m.get("valueInt") is not None:
                    durations[int(m["valueInt"])] = float(m["durationSec"])

        starts = events["time_s"].to_numpy(float)
        stops = np.append(starts[1:], self.duration_s)
        rows = []
        for start, stop, value in zip(starts, stops, events["value"].to_numpy(int)):
            if value in durations:
                stop = min(stop, start + durations[value])
            label = (value_map.get(str(value)) or self._demo_label(start)
                     or f"marker_{value}")
            rows.append({"start_s": float(start), "stop_s": float(stop),
                         "value": int(value), "label": label})
        return pd.DataFrame(rows)

    def _demo_label(self, t: float) -> str | None:
        """``Demo.State`` of the dummy export, if present."""
        if "Demo.State" not in self.df.columns:
            return None
        i = min(int(round(t * self.sfreq)), self.n_samples - 1)
        value = self.df["Demo.State"].iloc[i]
        return None if pd.isna(value) else str(value)

    def _resolve_sidecar(self, sidecar: str | os.PathLike | None) -> dict | None:
        candidates = [Path(sidecar)] if sidecar else [
            self.path.with_suffix(".markers.json"),
            self.path.parent / "markers.json",
        ]
        for cand in candidates:
            if cand.is_file():
                try:
                    return json.loads(cand.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    self.warnings.append(f"Marker sidecar unreadable: {cand.name}")
        return None

    def quality(self) -> pd.DataFrame:
        """Quality columns per sample plus the gate decision."""
        def col(name: str) -> pd.Series:
            if name in self.df.columns:
                return pd.to_numeric(self.df[name], errors="coerce")
            return pd.Series(np.nan, index=self.df.index, dtype=float)

        cq, eq, srq = col("CQ.Overall"), col("EQ.OVERALL"), col("EQ.SampleRateQuality")
        reason = np.array(["ok"] * self.n_samples, dtype=object)
        reason[(cq < CQ_OVERALL_MIN).to_numpy()] = "bad_contact_quality"
        reason[(srq == EQ_SAMPLERATE_INVALID).to_numpy()] = "sample_rate_loss"
        return pd.DataFrame({
            "cq_overall": cq.to_numpy(float),
            "eq_overall": eq.to_numpy(float),
            "eq_sample_rate": srq.to_numpy(float),
            "ok": reason == "ok",
            "reason": reason,
        })

    def bandpower_array(self, band: str, sensors: Sequence[str] | None = None,
                        ffill: bool = True) -> tuple[List[str], np.ndarray]:
        """Band power of one band as ``(sensors, array[n_samples, n_sensors])``."""
        if band not in POW_BANDS:
            raise ValueError(f"Unknown band {band!r}. Allowed: {sorted(POW_BANDS)}")
        cols, names = [], []
        for sensor in (list(sensors) if sensors else self.pow_sensors):
            col = f"POW.{sensor}.{band}"
            if col in self.df.columns:
                cols.append(col)
                names.append(sensor)
        if not cols:
            raise MissingRequiredColumnError(f"No POW columns for band {band!r}.")
        values = self.numeric(cols, strict=False)
        if ffill:
            values = values.ffill().bfill()
        return names, values.to_numpy(dtype=float)

    def derive_bandpower(self, signal_uv=None, window_s: float = 2.0,
                         update_hz: float = 8.0) -> int:
        """Compute ``POW.<Sensor>.<Band>`` from the raw EEG."""
        from scipy.signal import spectrogram

        if self.pow_columns:
            raise EmotivProError(
                f"{self.path.name}: already contains POW.* columns - "
                f"nothing to derive.")
        if signal_uv is None:
            data = self.eeg_microvolts(strict=False).ffill().bfill().to_numpy(float)
        else:
            data = np.asarray(signal_uv, dtype=float)
        sensors = self.sensors
        if data.shape != (self.n_samples, len(sensors)):
            raise ValueError(
                f"signal_uv has shape {data.shape}, expected "
                f"{(self.n_samples, len(sensors))}.")

        nwin = int(round(window_s * self.sfreq))
        hop = max(1, int(round(self.sfreq / update_hz)))
        if nwin < 8 or self.n_samples < nwin:
            raise EmotivProError(
                f"{self.path.name}: recording ({self.n_samples} samples) is shorter "
                f"than one band-power window ({nwin} samples).")
        freqs, centers, psd = spectrogram(
            data.T, fs=self.sfreq, window="hann", nperseg=nwin,
            noverlap=nwin - hop, detrend="constant", scaling="density",
            mode="psd", axis=-1)
        end = np.minimum(np.round(centers * self.sfreq + nwin / 2).astype(int) - 1,
                         self.n_samples - 1)

        columns: Dict[str, np.ndarray] = {}
        for band, (lo, hi) in POW_BANDS.items():
            sel = (freqs >= lo) & (freqs < hi)
            db = 10.0 * np.log10(np.maximum(psd[:, sel, :].mean(axis=1), 1e-12))
            for i, sensor in enumerate(sensors):
                col = np.full(self.n_samples, np.nan)
                col[end] = db[i]
                columns[f"POW.{sensor}.{band}"] = col
        self.df = pd.concat([self.df, pd.DataFrame(columns, index=self.df.index)],
                            axis=1)
        self.bandpower_source = "derived"
        self.warnings.append(
            f"{self.path.name}: no POW stream in the export - band power computed "
            f"from the raw EEG ({window_s:g} s window, {update_hz:g} Hz update). "
            f"Not an original EmotivPRO value.")
        return len(columns)

    def pm_scaled_unit(self) -> float:
        """Scale maximum of ``PM.*.Scaled`` (1.0 or 100.0)."""
        cols = [f"PM.{m}.Scaled" for m in PM_METRICS
                if f"PM.{m}.Scaled" in self.df.columns]
        if not cols:
            return 1.0
        values = self.numeric(cols, strict=False).to_numpy(dtype=float)
        peak = np.nanmax(values) if np.isfinite(values).any() else 0.0
        return 100.0 if peak > 1.5 else 1.0

    def performance_metrics(self, apply_gate: bool = True) -> pd.DataFrame:
        """PM per sample, normalised to 0..1."""
        unit = self.pm_scaled_unit()
        gate = (self.quality()["ok"].to_numpy() if apply_gate
                else np.ones(self.n_samples, bool))
        out: Dict[str, np.ndarray] = {}
        for metric in PM_METRICS:
            scaled_col, active_col = f"PM.{metric}.Scaled", f"PM.{metric}.IsActive"
            if scaled_col not in self.df.columns:
                continue
            values = pd.to_numeric(self.df[scaled_col], errors="coerce").to_numpy(float) / unit
            if active_col in self.df.columns:
                active = pd.to_numeric(self.df[active_col],
                                       errors="coerce").fillna(0).to_numpy() > 0
            else:
                active = np.ones(self.n_samples, bool)
                self.warnings.append(
                    f"{active_col} missing - PM.{metric} taken over unchecked.")
            if apply_gate:
                values = np.where(active & gate, values, np.nan)
            out[metric] = values
            out[f"{metric}.IsActive"] = active.astype(int)
        return pd.DataFrame(out, index=self.df.index)

    def to_mne_raw(self, montage_name: str = "standard_1005",
                   with_stim: bool = True, strict: bool = True):
        """Raw EEG as ``mne.io.RawArray`` in volts, with montage and markers."""
        import mne
        mne.set_log_level("ERROR")

        data = self.eeg_microvolts(strict=strict).to_numpy(dtype=float).T * 1e-6
        names, types = list(self.sensors), ["eeg"] * len(self.sensors)
        if with_stim:
            data = np.vstack([data, np.zeros((1, data.shape[1]))])
            names.append(STIM_CH)
            types.append("stim")

        info = mne.create_info(names, sfreq=self.sfreq, ch_types=types)
        raw = mne.io.RawArray(data, info, verbose=False)

        events = self.marker_events()

        # a stim channel cannot hold 0
        stim_events = events[events["value"] != 0] if not events.empty else events
        if with_stim and not stim_events.empty:
            raw.add_events(np.column_stack([
                stim_events["sample"].to_numpy(int),
                np.zeros(len(stim_events), int),
                stim_events["value"].to_numpy(int),
            ]), stim_channel=STIM_CH)
        if not events.empty:
            raw.set_annotations(mne.Annotations(
                onset=events["time_s"].to_numpy(float),
                duration=np.zeros(len(events)),
                description=[f"{t}:{v}" for t, v
                             in zip(events["type"], events["value"].astype(int))],
            ))
        try:
            raw.set_montage(mne.channels.make_standard_montage(montage_name),
                            match_case=False, on_missing="warn")
        except Exception as exc:
            self.warnings.append(f"Montage {montage_name!r} not set: {exc}")
        return raw


class EmotivProCsvReader:
    """Reads the raw structure of an EmotivPRO export."""

    @staticmethod
    def parse_metadata(path: str | os.PathLike) -> Dict[str, str]:
        path = Path(path)
        try:
            with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
                first = fh.readline().strip()
        except OSError as exc:
            raise EmotivProError(f"{path.name} not readable: {exc}") from exc
        if not first or ":" not in first:
            raise MissingMetadataError(
                f"{path.name}: line 1 is not a metadata line. Expected "
                f"key:value pairs, e.g. 'title:..., sampling rate:128, samples:...'.")
        meta: Dict[str, str] = {}
        for part in first.split(","):
            if ":" in part:
                key, value = part.split(":", 1)
                meta[key.strip()] = value.strip()
        if not meta:
            raise MissingMetadataError(
                f"{path.name}: metadata line contains no key:value pairs.")
        return meta

    @staticmethod
    def sampling_rate(meta: Dict[str, str], path: Path | None = None) -> float:
        """Sampling rate from the metadata line - never guessed."""
        normalized = {_norm_key(k): v for k, v in meta.items()}
        raw = next((normalized[k] for k in _META_SFREQ_KEYS if k in normalized), None)
        where = f"{path.name}: " if path else ""
        if raw is None:
            raise MissingMetadataError(
                f"{where}no 'sampling rate' in the metadata line. "
                f"Keys found: {sorted(meta)[:8]}")
        match = _NUM_RE.search(str(raw))
        if not match:
            raise MissingMetadataError(
                f"{where}'sampling rate' is not numeric: {raw!r}")
        sfreq = float(match.group(0))
        if not 1.0 <= sfreq <= 20000.0:
            raise MissingMetadataError(f"{where}implausible sampling rate: {sfreq} Hz")
        return sfreq

    @classmethod
    def read(cls, path: str | os.PathLike) -> EmotivProRecording:
        path = Path(path)
        if path.is_dir():
            raise EmotivProError(f"{path.name} is a folder - please pass an "
                                 f"EmotivPRO CSV file.")
        meta = cls.parse_metadata(path)
        sfreq = cls.sampling_rate(meta, path)
        try:
            df = pd.read_csv(path, skiprows=1, low_memory=False)
        except Exception as exc:
            raise EmotivProError(f"{path.name}: CSV not readable: {exc}") from exc
        if "Timestamp" not in df.columns:
            raise MissingRequiredColumnError(
                f"{path.name}: column 'Timestamp' is missing - the metadata line "
                f"was probably read as the header.")
        df = df.loc[:, ~df.columns.str.startswith("Unnamed:")]

        version = str(meta.get("version", "2")).split(".")[0]
        rec = EmotivProRecording(meta=meta, df=df, sfreq=sfreq, path=path,
                                 format=f"csv_v{version}")
        cls._check_sample_count(rec)
        return rec

    @staticmethod
    def _check_sample_count(rec: EmotivProRecording) -> None:
        declared = rec.meta.get("samples")
        if not declared:
            return
        match = _NUM_RE.search(declared)
        if match and int(float(match.group(0))) != rec.n_samples:
            rec.warnings.append(
                f"Metadata declares {int(float(match.group(0)))} samples, "
                f"{rec.n_samples} were read.")


class EmotivProSchemaValidator:
    """Checks a recording for the required format and quality."""

    def __init__(self, require_motion: bool = False, require_bandpower: bool = False,
                 require_pm: bool = False, require_quality: bool = False,
                 expected_sensors: Sequence[str] | None = FLEX2_SENSORS):
        self.require_motion = require_motion
        self.require_bandpower = require_bandpower
        self.require_pm = require_pm
        self.require_quality = require_quality
        self.expected_sensors = tuple(expected_sensors) if expected_sensors else None

    @classmethod
    def full(cls) -> "EmotivProSchemaValidator":
        return cls(require_motion=True, require_bandpower=True,
                   require_pm=True, require_quality=True)

    def validate(self, rec: EmotivProRecording) -> List[str]:
        """Check rec and return the collected warnings."""
        if not rec.eeg_columns:
            raise MissingRequiredColumnError(
                f"{rec.path.name}: no raw EEG columns in the format EEG.<Sensor>.")
        issues: List[str] = []
        issues += self._check_layout(rec)
        issues += self._check_motion(rec)
        issues += self._check_bandpower(rec)
        issues += self._check_pm(rec)
        issues += self._check_quality(rec)
        rec.warnings.extend(issues)
        return rec.warnings

    def _check_layout(self, rec: EmotivProRecording) -> List[str]:
        if not self.expected_sensors:
            return []
        found, expected = set(rec.sensors), set(self.expected_sensors)
        if found == expected:
            return []
        message = (f"{rec.path.name}: sensor list differs from the FLEX 2 standard layout "
                   f"(missing: {sorted(expected - found)[:6]}, "
                   f"additional: {sorted(found - expected)[:6]}).")
        warnings.warn(message, UnsupportedHeadsetLayoutWarning, stacklevel=2)
        return [message]

    def _check_motion(self, rec: EmotivProRecording) -> List[str]:
        cols = set(rec.mot_columns)
        if not cols:
            if self.require_motion:
                raise MissingRequiredColumnError(
                    f"{rec.path.name}: no motion columns in the format MOT.<...>.")
            return []
        required_acc = {"MOT.AccX", "MOT.AccY", "MOT.AccZ"}
        if not required_acc.issubset(cols):
            missing = sorted(required_acc - cols)
            if self.require_motion:
                raise MissingRequiredColumnError(
                    f"{rec.path.name}: required motion columns missing: {missing}")
            return [f"{rec.path.name}: motion incomplete, missing: {missing}"]
        has_quat = {"MOT.Q0", "MOT.Q1", "MOT.Q2", "MOT.Q3"}.issubset(cols)
        has_gyro = {"MOT.GYROX", "MOT.GYROY", "MOT.GYROZ"}.issubset(cols)
        if not (has_quat or has_gyro):
            return [f"{rec.path.name}: neither quaternions (MOT.Q0..Q3) nor "
                    f"gyro (MOT.GYROX..Z) present."]
        return []

    def _check_bandpower(self, rec: EmotivProRecording) -> List[str]:
        cols = rec.pow_columns
        if not cols:
            if self.require_bandpower:
                raise MissingRequiredColumnError(
                    f"{rec.path.name}: no band-power columns in the format "
                    f"POW.<Sensor>.<Band>.")
            return []
        issues: List[str] = []
        missing_bands = sorted(set(POW_BANDS) - {c.rsplit(".", 1)[1] for c in cols})
        if missing_bands:
            issues.append(f"{rec.path.name}: band-power bands missing: {missing_bands}")
        if self.expected_sensors:
            available = set(cols)
            missing = [f"POW.{s}.{b}" for s in self.expected_sensors
                       for b in POW_BANDS if f"POW.{s}.{b}" not in available]
            if missing:
                if self.require_bandpower:
                    raise MissingRequiredColumnError(
                        f"{rec.path.name}: required band-power columns missing "
                        f"({len(missing)} in total), e.g.: {missing[:5]}")
                issues.append(f"{rec.path.name}: {len(missing)} POW columns missing, "
                              f"e.g. {missing[:3]}")
        return issues

    def _check_pm(self, rec: EmotivProRecording) -> List[str]:
        cols = set(rec.pm_columns)
        if not cols:
            if self.require_pm:
                raise MissingRequiredColumnError(
                    f"{rec.path.name}: no performance-metric columns in the format "
                    f"PM.<Metric>.<Field>.")
            return []
        missing_active = [f"PM.{m}.IsActive" for m in PM_METRICS
                          if any(c.startswith(f"PM.{m}.") for c in cols)
                          and f"PM.{m}.IsActive" not in cols]
        if missing_active:
            if self.require_pm:
                raise MissingRequiredColumnError(
                    f"{rec.path.name}: PM without IsActive flag: {missing_active}")
            return [f"{rec.path.name}: PM without IsActive flag: {missing_active}"]

        issues: List[str] = []
        gate_ok = rec.quality()["ok"].to_numpy()
        if gate_ok.any():
            pm = rec.performance_metrics(apply_gate=True)
            for metric in PM_METRICS:
                if metric not in pm.columns:
                    continue
                unusable = int((gate_ok & np.isnan(pm[metric].to_numpy(float))).sum())
                if unusable:
                    issues.append(
                        f"{rec.path.name}: PM.{metric} is unusable in {unusable} samples "
                        f"({unusable / int(gate_ok.sum()):.0%} of the good data) - "
                        f"fall back to band power.")
        return issues

    def _check_quality(self, rec: EmotivProRecording) -> List[str]:
        issues: List[str] = []
        for col in ("CQ.Overall", "EQ.SampleRateQuality", "EQ.OVERALL"):
            if col not in rec.df.columns:
                if self.require_quality:
                    raise MissingRequiredColumnError(
                        f"{rec.path.name}: quality column {col} is missing.")
                issues.append(f"{rec.path.name}: quality column {col} is missing - "
                              f"the gate runs without this criterion.")
        gate = rec.quality()
        bad = int((~gate["ok"]).sum())
        if bad:
            breakdown = pd.Series(gate.loc[~gate["ok"], "reason"]).value_counts().to_dict()
            issues.append(
                f"{rec.path.name}: {bad}/{len(gate)} samples ({bad / len(gate):.0%}) "
                f"do not pass the quality gate: {breakdown}")
        return issues


__all__ = [
    "EmotivProError", "MissingMetadataError", "MissingRequiredColumnError",
    "NonNumericDataError", "BadQualitySegment", "UnsupportedHeadsetLayoutWarning",
    "EmotivProRecording", "EmotivProCsvReader", "EmotivProSchemaValidator",
    "FLEX2_SENSORS", "POW_BANDS", "PM_METRICS", "PM_FIELDS",
    "LINE_FREQ_HZ", "NON_SENSOR_EEG_COLUMNS", "CQ_OVERALL_MIN",
    "EQ_SAMPLERATE_INVALID", "STIM_CH",
]
