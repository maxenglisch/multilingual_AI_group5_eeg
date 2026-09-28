"""FIF persistence retained from the old 002 project.

Raw construction belongs to :mod:`src.eeg_processing`; this module only saves
already validated MNE objects and never guesses channels, rates, or units.
"""
from pathlib import Path


def save_raw_fif(raw, output_path, overwrite=True):
    """Save one validated MNE Raw object."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.save(path, overwrite=overwrite, verbose=False)
    return path


def save_pipeline_fifs(raw_original, raw_car, raw_mrcp, output_dir):
    """Save original, CAR and MRCP-filtered objects without modifying them."""
    root = Path(output_dir)
    return [
        save_raw_fif(raw_original, root / "raw_original.fif"),
        save_raw_fif(raw_car, root / "raw_car.fif"),
        save_raw_fif(raw_mrcp, root / "raw_mrcp_filtered.fif"),
    ]
