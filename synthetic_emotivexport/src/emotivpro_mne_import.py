

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

try:
    import mne
except ImportError:  
    mne = None


class EmotivProFormatError(ValueError):
    pass


def parse_metadata_line(path: str | Path) -> Dict[str, str]:
    first = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[0]
    if "title:" not in first or "sampling rate:" not in first:
        raise EmotivProFormatError(
            "EmotivPRO CSV metadata line missing. Erwartet Zeile 1 mit key:value Paaren, "
        )
    meta: Dict[str, str] = {}
   
    for part in first.split(","):
        if ":" in part:
            key, value = part.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta


def get_sampling_rate(meta: Dict[str, str], default: float | None = None) -> float:
    raw = meta.get("sampling rate") or meta.get("sample rate")
    if raw is None:
        if default is not None:
            return float(default)
        raise EmotivProFormatError("Kein 'sampling rate' Feld in der EmotivPRO-Metadatenzeile gefunden.")
    
    match = re.search(r"[-+]?\d*\.?\d+", raw)
    if not match:
        raise EmotivProFormatError(f"Sampling rate ist nicht numerisch: {raw!r}")
    return float(match.group(0))


def read_emotivpro_csv(path: str | Path) -> tuple[Dict[str, str], pd.DataFrame]:
    path = Path(path)
    meta = parse_metadata_line(path)
    try:
        df = pd.read_csv(path, skiprows=1, low_memory=False)
    except Exception as exc:
        raise EmotivProFormatError(f"CSV konnte nicht gelesen werden: {exc}") from exc
    if "Timestamp" not in df.columns:
        raise EmotivProFormatError("Spalte 'Timestamp' fehlt. Wahrscheinlich wurde die erste Header-Zeile falsch behandelt.")
    return meta, df


def columns_by_prefix(df: pd.DataFrame, prefix: str) -> List[str]:
    return [c for c in df.columns if c.startswith(prefix)]


def eeg_sensor_columns(df: pd.DataFrame) -> List[str]:
    excluded = {"EEG.Counter", "EEG.Interpolated", "EEG.RawCq", "EEG.Battery", "EEG.BatteryPercent", "EEG.MarkerHardware"}
    return [c for c in df.columns if c.startswith("EEG.") and c not in excluded]


def validate_schema(df: pd.DataFrame, require_bandpower: bool = True, require_motion: bool = True, expected_sensors: list[str] | None = None) -> List[str]:
    warnings: List[str] = []
    eeg_cols = eeg_sensor_columns(df)
    if not eeg_cols:
        raise EmotivProFormatError("Keine Roh EEG Spalten im Format EEG.<Sensor> gefunden.")
    if require_motion and not columns_by_prefix(df, "MOT."):
        raise EmotivProFormatError("Keine Motion Spalten im Format MOT.<...> gefunden.")
    pow_cols = columns_by_prefix(df, "POW.")
    if require_bandpower and not pow_cols:
        raise EmotivProFormatError("Keine Bandpower Spalten im Format POW.<Sensor>.<Band> gefunden.")
    # minimal consistency checks
    expected_bands = {"Theta", "Alpha", "BetaL", "BetaH", "Gamma"}
    seen_bands = {c.split(".")[-1] for c in pow_cols if c.count(".") >= 2}
    missing_bands = expected_bands - seen_bands
    if require_bandpower and missing_bands:
        warnings.append(f"Nicht alle Standard Bandpower Bänder gefunden: {sorted(missing_bands)}")
    if require_bandpower and expected_sensors:
        missing_pow = [f"POW.{sensor}.{band}" for sensor in expected_sensors for band in sorted(expected_bands) if f"POW.{sensor}.{band}" not in df.columns]
        if missing_pow:
            raise EmotivProFormatError(f"Bandpower Pflichtspalten fehlen: {missing_pow[:5]}")
    if "EQ.SampleRateQuality" in df.columns:
        srq = pd.to_numeric(df["EQ.SampleRateQuality"], errors="coerce")
        if (srq == -1).any():
            warnings.append("EQ.SampleRateQuality enthält -1: Datenverlust >300 ms in einem 2s Fenster möglich; Segment ausschließen oder markieren.")
    return warnings


def numeric_frame(df: pd.DataFrame, cols: List[str], strict: bool = True) -> pd.DataFrame:
    out = df[cols].apply(pd.to_numeric, errors="coerce")
    bad = out.columns[out.isna().any()].tolist()
    if bad and strict:
        example_col = bad[0]
        idx = int(out[example_col].isna().idxmax())
        raise EmotivProFormatError(f"Nicht numerischer/fehlender Wert in {example_col} bei Zeile {idx}.")
    return out


def create_mne_raw_from_emotivpro(path: str | Path, strict: bool = True):
    if mne is None:
        raise ImportError("mne ist nicht installiert.")
    meta, df = read_emotivpro_csv(path)
    sfreq = get_sampling_rate(meta)
    warnings = validate_schema(df)
    eeg_cols = eeg_sensor_columns(df)
    eeg_uv = numeric_frame(df, eeg_cols, strict=strict)
   
    data_v = eeg_uv.to_numpy(dtype=float).T * 1e-6
    ch_names = [c.replace("EEG.", "") for c in eeg_cols]
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data_v, info, verbose=False)
    
    try:
        montage = mne.channels.make_standard_montage("standard_1020")
        raw.set_montage(montage, match_case=False, on_missing="ignore")
    except Exception:
        pass
    
    if {"MarkerIndex", "MarkerType", "MarkerValueInt"}.issubset(df.columns):
        marker_rows = df[df["MarkerValueInt"].notna() & (df["MarkerValueInt"].astype(str).str.len() > 0)]
        if not marker_rows.empty:
            ts0 = pd.to_numeric(df["Timestamp"], errors="coerce").iloc[0]
            onsets = pd.to_numeric(marker_rows["Timestamp"], errors="coerce") - ts0
            desc = marker_rows["MarkerType"].astype(str) + ":" + marker_rows["MarkerValueInt"].astype(str)
            raw.set_annotations(mne.Annotations(onset=onsets.to_numpy(float), duration=[0.0]*len(marker_rows), description=desc.tolist()))
    return raw, meta, warnings


def bandpower_table(path: str | Path, fill_missing: bool = True) -> pd.DataFrame:
    _, df = read_emotivpro_csv(path)
    pow_cols = columns_by_prefix(df, "POW.")
    if not pow_cols:
        raise EmotivProFormatError("Keine POW Spalten gefunden.")
    bp = df[["Timestamp"] + pow_cols].copy()
    for c in pow_cols:
        bp[c] = pd.to_numeric(bp[c], errors="coerce")
    if fill_missing:
        bp[pow_cols] = bp[pow_cols].ffill()
    return bp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--save-fif", default=None)
    parser.add_argument("--non-strict", action="store_true", help="coerce bad numeric cells to NaN instead of failing")
    args = parser.parse_args()
    raw, meta, warnings = create_mne_raw_from_emotivpro(args.csv_path, strict=not args.non_strict)
    print(f"OK: {args.csv_path}")
    print(f"Sampling rate: {raw.info['sfreq']} Hz")
    print(f"EEG channels: {len(raw.ch_names)}")
    print(f"Samples: {raw.n_times}")
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(" -", w)
    if args.save_fif:
        raw.save(args.save_fif, overwrite=True)
        print(f"Saved: {args.save_fif}")


if __name__ == "__main__":
    main()
