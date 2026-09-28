import mne
import numpy as np
import pytest

CHANNELS = ["AF3", "AF4", "F3", "F1", "Fz", "F2", "F4", "FC3", "FC1", "FCz", "FC2", "FC4",
            "C3", "C1", "Cz", "C2", "C4", "CP3", "CP1", "CPz", "CP2", "CP4",
            "P3", "P1", "Pz", "P2", "P4", "PO3", "POz", "PO4", "O1", "O2"]


@pytest.fixture
def make_raw():
    """Raw from microvolt data (channels x samples) at 128 Hz."""
    def build(data_uv, sfreq=128.0, channels=CHANNELS):
        info = mne.create_info(list(channels), sfreq, "eeg")
        return mne.io.RawArray(np.asarray(data_uv, float) * 1e-6, info, verbose=False)
    return build


@pytest.fixture
def gate():
    return {"max_ptp_uv": 150.0, "min_std_uv": 0.5, "max_bad_channel_fraction": 0.25,
            "min_good_frame_fraction": 0.5}
