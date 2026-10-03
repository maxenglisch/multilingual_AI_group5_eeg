from src.data_loader import discover_pairs

def test_trial_and_session_pairing(tmp_path):
    for name in ["SUBJECT01_Trial_01_EEG.csv","SUBJECT01_Trial_01_EMG.csv","SUBJECT02_Session_02_EEG.csv"]: (tmp_path/name).write_text("Triggers,0\n0,1\n")
    pairs,_=discover_pairs(tmp_path)
    assert len(pairs)==2 and pairs[0].eeg_path and pairs[0].emg_path and pairs[1].emg_path is None

def test_windows_style_nested_path(tmp_path):
    p=tmp_path/"SUBJECT03"/"nested"; p.mkdir(parents=True); (p/"SUBJECT03_Trial_05_EEG.csv").write_text("Triggers,0\n0,1\n")
    assert discover_pairs(tmp_path)[0][0].subject=="SUBJECT03"
