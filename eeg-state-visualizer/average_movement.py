"""Averages all movements of Hand-Gesture CSVs into one EmotivPRO recording. Usage: python average_movement.py <csv or folder> [...] [-o output.csv]"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable, List, Sequence

import numpy as np
import pandas as pd

from emotivpro_io import EmotivProRecording
from handgesture_to_emotivpro import SFREQ, add_markers, read_handgesture, write_emotivpro

ONSET = 7711

# one full cycle: rest, preparation, movement, movement_end, rest
WINDOW_S = (-3.5, 8.0)


def find_files(paths: Iterable[str | Path]) -> List[Path]:
    files: List[Path] = []
    for p in map(Path, paths):
        files += sorted(p.rglob("*_EEG.csv")) if p.is_dir() else [p]
    return files


def average(files: Sequence[Path]) -> tuple[pd.DataFrame, int]:
    """Mean of raw EEG and band power over all movement windows."""
    lo, hi = round(WINDOW_S[0] * SFREQ), round(WINDOW_S[1] * SFREQ)
    total, columns, n = None, None, 0
    offsets = defaultdict(list)

    for path in files:
        try:
            df = read_handgesture(path)
        except Exception as exc:
            print(f"    skipped {path.name}: {exc}")
            continue
        rec = EmotivProRecording(meta={}, df=df, sfreq=SFREQ, path=path)
        rec.derive_bandpower()
        cols = rec.eeg_columns + rec.pow_columns
        data = rec.df[cols].ffill().bfill().to_numpy(float)

        values = df["MarkerValueInt"].to_numpy(float)
        events = np.flatnonzero(~np.isnan(values))
        for s in events[values[events] == ONSET]:
            if s + lo < 0 or s + hi > len(df):
                continue
            block = data[s + lo:s + hi]
            total = block.copy() if total is None else total + block
            columns = columns or cols
            n += 1
            for e in events[(events >= s + lo) & (events < s + hi)]:
                offsets[(int(values[e]), e >= s)].append(e - (s + lo))

    if n == 0:
        raise ValueError("no complete movement window found")

    out = pd.DataFrame(total / n, columns=columns)
    out.insert(0, "Timestamp", np.arange(len(out)) / SFREQ)
    markers = pd.Series(np.nan, index=out.index)
    for (code, _), pos in offsets.items():
        if len(pos) >= n / 2:
            markers.iloc[int(np.median(pos))] = code
    add_markers(out, markers)
    return out, n


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Averages all movements into one EmotivPRO recording.")
    parser.add_argument("paths", nargs="+", help="Hand-Gesture EEG CSVs or folders")
    parser.add_argument("-o", "--out", default=None, help="target CSV")
    args = parser.parse_args(argv)

    files = find_files(args.paths)
    out_csv = Path(args.out or f"{Path(args.paths[0]).resolve().name}_average_emotivpro.csv")
    try:
        df, n = average(files)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")
        return 1
    write_emotivpro(df, out_csv, f"Average of {n} movements")
    print(f"{n} movements from {len(files)} files -> {out_csv.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
