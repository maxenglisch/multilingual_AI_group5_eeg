from src.group_analysis import discover_subject_ids

def test_discovers_only_subject_files(tmp_path):
    for name in ["SUBJECT01_Trial_01_EEG.csv","SUBJECT02_Trial_01_EMG.csv","CONTROL_Trial_01_EEG.csv"]:
        folder=tmp_path/("misc" if name.startswith("CONTROL") else name.split("_")[0]); folder.mkdir(exist_ok=True); (folder/name).write_text("Triggers,0\n0,1\n")
    assert discover_subject_ids(tmp_path)==["SUBJECT01","SUBJECT02"]
