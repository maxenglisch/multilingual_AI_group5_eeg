"""Converts a Hand-Gesture CSV (Mendeley) to EmotivPRO CSV V2. Usage: python handgesture_to_emotivpro.py SUBJECTxx_Trial_xx_EEG.csv [output.csv]"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from emotivpro_io import FLEX2_SENSORS

SFREQ = 128

# columns 2-33 are the 32 electrodes, same as mrcp-eeg-analysis/config/dataset.yaml
COLUMN_MAP = {"0": "EEG.Counter", "1": "EEG.Interpolated",
              **{str(i + 2): f"EEG.{s}" for i, s in enumerate(FLEX2_SENSORS)}}

# trigger codes, same as mrcp-eeg-analysis/config/dataset.yaml
MARKER_LABELS = {
    768: "trial_start",
    771: "preparation",
    7711: "movement",
    7712: "movement_end",
    1000: "rest",
    32766: "session_boundary",
}


def add_markers(df: pd.DataFrame, values: pd.Series) -> None:
    """Marker columns, filled only on event rows."""
    is_event = values.notna()
    df["MarkerIndex"] = np.where(is_event, is_event.cumsum(), np.nan)
    df["MarkerType"] = np.where(is_event, "trigger", "")
    df["MarkerValueInt"] = values


def read_handgesture(path: str | Path) -> pd.DataFrame:
    """Hand-Gesture CSV with EmotivPRO column names."""
    path = Path(path)
    raw = pd.read_csv(path, encoding="utf-8-sig")
    missing = [c for c in ["Triggers", *COLUMN_MAP] if c not in raw.columns]
    if missing:
        raise ValueError(f"{path.name}: not a Hand-Gesture CSV, missing columns {missing[:5]}")

    df = raw[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)
    df.insert(0, "Timestamp", np.arange(len(df)) / SFREQ)
    triggers = raw["Triggers"].astype(int)
    add_markers(df, triggers.where(triggers != 0))
    return df


def write_emotivpro(df: pd.DataFrame, out_csv: Path, title: str) -> Path:
    """Writes the CSV plus the markers.json sidecar."""
    meta = (f"title:{title}, sampling rate:{SFREQ}, samples:{len(df)}, "
            f"headset type:EPOCFLEX, version:2.1, stream types:EEG")
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        fh.write(meta + "\n")
        df.to_csv(fh, index=False)

    sidecar = out_csv.with_suffix(".markers.json")
    sidecar.write_text(json.dumps(
        {"valueMap": {str(k): v for k, v in MARKER_LABELS.items()}}, indent=2),
        encoding="utf-8")
    return out_csv


def convert(path: str | Path, out_csv: str | Path | None = None) -> Path:
    path = Path(path)
    out_csv = Path(out_csv) if out_csv else path.with_name(f"{path.stem}_emotivpro.csv")
    return write_emotivpro(read_handgesture(path), out_csv, path.stem)


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Converts a Hand-Gesture CSV to EmotivPRO CSV V2.")
    parser.add_argument("path", help="Hand-Gesture EEG CSV")
    parser.add_argument("out", nargs="?", default=None, help="target CSV")
    args = parser.parse_args(argv)

    try:
        out = convert(args.path, args.out)
    except Exception as exc:
        print(f"{Path(args.path).name}: {type(exc).__name__}: {exc}")
        return 1
    print(f"{Path(args.path).name} -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
