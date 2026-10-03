import numpy as np
from src.eeg_processing import microvolts_to_volts

def test_uv_to_v(): assert np.allclose(microvolts_to_volts([1,-2]),[1e-6,-2e-6])
