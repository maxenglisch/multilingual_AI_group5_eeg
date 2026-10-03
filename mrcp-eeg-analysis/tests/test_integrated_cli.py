from pathlib import Path
import pandas as pd

from src.config import load_config
from src.main import build_parser, run, subject_output_dir


def test_authoritative_config_is_128_and_exact_mapping():
    cfg = load_config()
    eeg = cfg["eeg"]
    assert eeg["sampling_rate"] == 128.0
    assert eeg["channel_columns"] == [str(i) for i in range(2, 34)]
    assert eeg["excluded_columns"] == ["Triggers", "0", "1", "34", "35", "36", "37"]
    assert list(eeg["column_mapping"].values()) == eeg["channel_names"]


def test_optional_flags_are_off_by_default_and_parse_true():
    parser = build_parser()
    default = parser.parse_args(["--data-dir", "data"])
    enabled = parser.parse_args(["--data-dir", "data", "--make-video", "true", "--save-fif", "true"])
    assert default.make_video is False and default.save_fif is False
    assert enabled.make_video is True and enabled.save_fif is True
    assert subject_output_dir("outputs", "subject01") == Path("outputs") / "subject01"


def test_dry_run_never_creates_emotion_frequency(tmp_path):
    cfg = load_config(); raw = tmp_path / "raw"; raw.mkdir()
    eeg = {"Triggers": [771, 0]}
    for col in [str(i) for i in range(38)]: eeg[col] = [0.0, 0.0]
    pd.DataFrame(eeg).to_csv(raw / "SUBJECT99_Trial_01_EEG.csv", index=False)
    pd.DataFrame({"Triggers": [771, 0], "0": [1, 2]}).to_csv(raw / "SUBJECT99_Trial_01_EMG.csv", index=False)
    args = build_parser().parse_args(["--data-dir", str(raw), "--output-dir", str(tmp_path / "out"), "--dry-run"])
    assert run(args) == 0
    assert not list((tmp_path / "out").rglob("*emotion*"))
    diag = pd.read_csv(tmp_path / "out" / "tables" / "channel_diagnostics.csv")
    assert diag.loc[0, "detected_channels"].split("|") == cfg["eeg"]["channel_names"]
