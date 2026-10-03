from src.feature_extraction import eeg_emg_latency

def test_eeg_minus_emg_latency(): assert eeg_emg_latency(.25,.10)==.15
