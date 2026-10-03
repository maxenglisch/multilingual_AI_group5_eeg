import numpy as np
import pandas as pd

from src.channel_utils import TriggerOnlyEEGError, detect_eeg_channels
from src.config import load_config
from src.main import build_parser, run


def _write_subject_files(folder):
    cfg = load_config()
    samples = 700
    triggers = np.zeros(samples, dtype=int)
    triggers[350] = 7711
    valid = {"Triggers": triggers}
    for index, source in enumerate(cfg["eeg"]["channel_columns"]):
        valid[source] = np.sin(np.arange(samples) / 25 + index)
    pd.DataFrame(valid).to_csv(folder / "SUBJECT99_Trial_01_EEG.csv", index=False)
    trigger_only = folder / "SUBJECT99_Trial_02_EEG.csv"
    pd.DataFrame({"Triggers": [768, 771, 0], "0": [1, 2, 3]}).to_csv(trigger_only, index=False)
    return trigger_only, trigger_only.read_bytes()


def test_trigger_only_detection_is_explicit_and_never_positional():
    try:
        detect_eeg_channels(["Triggers", "0", "1", "34"], 32, {})
    except TriggerOnlyEEGError as exc:
        assert exc.columns == ["Triggers", "0", "1", "34"]
    else:
        raise AssertionError("Trigger-only input must not use a positional fallback")


def test_trigger_only_is_skipped_batch_continues_and_source_is_unchanged(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    trigger_only, original = _write_subject_files(raw)
    output = tmp_path / "out"
    args = build_parser().parse_args([
        "--data-dir", str(raw), "--output-dir", str(output),
        "--subjects", "SUBJECT99", "--dry-run",
    ])
    assert run(args) == 0

    diagnostics = pd.read_csv(output / "subject99" / "tables" / "channel_diagnostics.csv")
    assert set(diagnostics["status"]) == {"success", "skipped_trigger_only"}
    skipped = diagnostics.loc[diagnostics["status"] == "skipped_trigger_only"].iloc[0]
    assert skipped["eeg_channel_count"] == 0
    assert skipped["warning"] == "No EEG signal columns; trigger-only file"

    recording_qc = pd.read_csv(output / "group_analysis" / "tables" / "recording_qc_summary.csv")
    assert set(recording_qc["status"]) == {"success", "skipped_trigger_only"}
    skipped_qc = recording_qc.loc[recording_qc["status"] == "skipped_trigger_only"].iloc[0]
    assert skipped_qc["eeg_channel_count"] == 0
    assert skipped_qc["warning"] == "No EEG signal columns; trigger-only file"
    assert trigger_only.read_bytes() == original
    warning_text = (output / "subject99" / "logs" / "pipeline.log").read_text(encoding="utf-8")
    assert "subject=SUBJECT99" in warning_text
    assert "SUBJECT99_Trial_02" in warning_text
    assert str(trigger_only) in warning_text
    assert "['Triggers', '0']" in warning_text
    assert " ERROR " not in warning_text
    assert "Traceback (most recent call last)" not in warning_text
