from pathlib import Path
import numpy as np


def _validate(raw, expected_channels, expected_sfreq):
    if not expected_channels or expected_sfreq is None:
        raise ValueError("expected_channels and expected_sfreq are required")
    if list(raw.ch_names) != list(expected_channels):
        raise ValueError(f"Channel mismatch: file={raw.ch_names}, expected={expected_channels}")
    if not np.isclose(float(raw.info["sfreq"]), float(expected_sfreq)):
        raise ValueError(f"Sampling-rate mismatch: {raw.info['sfreq']} != {expected_sfreq}")
    return raw


def read_mne_format(path, expected_channels, expected_sfreq):
    import mne
    path = Path(path)
    readers = {
        ".edf": mne.io.read_raw_edf, ".bdf": mne.io.read_raw_bdf,
        ".gdf": mne.io.read_raw_gdf, ".set": mne.io.read_raw_eeglab,
        ".fif": mne.io.read_raw_fif,
    }
    if path.suffix.lower() not in readers:
        raise ValueError(f"Unsupported MNE format: {path.suffix}")
    raw = readers[path.suffix.lower()](path, preload=True, verbose=False)
    missing = [ch for ch in expected_channels if ch not in raw.ch_names]
    if missing:
        raise ValueError(f"Required channels missing: {missing}")
    raw.pick(expected_channels)
    return _validate(raw, expected_channels, expected_sfreq)


def read_mat(path, variable, channel_names, sfreq, input_unit):
    from scipy.io import loadmat
    if input_unit not in {"V", "uV"}:
        raise ValueError("input_unit must be explicitly 'V' or 'uV'")
    content = loadmat(Path(path))
    if variable not in content:
        raise ValueError(f"MAT variable not found: {variable}")
    data = np.asarray(content[variable], dtype=float)
    if data.ndim != 2:
        raise ValueError(f"Expected a 2D matrix, got {data.shape}")
    if data.shape[0] == len(channel_names):
        matrix = data
    elif data.shape[1] == len(channel_names):
        matrix = data.T
    else:
        raise ValueError(f"Neither MAT dimension equals {len(channel_names)}: {data.shape}")
    if input_unit == "uV":
        matrix = matrix * 1e-6
    import mne
    raw = mne.io.RawArray(matrix, mne.create_info(channel_names, sfreq, "eeg"), verbose=False)
    return _validate(raw, channel_names, sfreq)
