import pytest
from src.channel_utils import detect_eeg_channels
from src.config import load_config

def test_explicit_mapping_selects_32_and_excludes_metadata():
    cfg=load_config(); cols=["Triggers"]+[str(i) for i in range(38)]
    d=detect_eeg_channels(cols,32,cfg["eeg"]["column_mapping"])
    assert len(d["channels"])==32 and "Triggers" in d["non_eeg"] and "TP9" not in d["channels"]

def test_no_mapping_does_not_guess_numeric_columns():
    with pytest.raises(ValueError): detect_eeg_channels([str(i) for i in range(38)],32,{})
