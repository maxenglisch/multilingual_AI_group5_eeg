import argparse
import json

import pandas as pd

from src.config import ROOT, load_config
from src.state_analysis import lateralization_summary, run_states


def test_synthetic_end_to_end(tmp_path):
    cfg = load_config(ROOT / "config" / "synthetic_emotion.yaml")
    args = argparse.Namespace(output_dir=str(tmp_path), data_dir=None, subject=None, subjects=None,
                              all_subjects=False, dry_run=False, make_playback=None)
    assert run_states(args, cfg) == 0
    out = tmp_path / "synthetic" / "states"
    accuracy = pd.read_csv(out / "tables" / "state_accuracy.csv")
    # The demo data is built from the same signatures: every expected state must rank first.
    assert len(accuracy) == 6 and accuracy["top1_rate"].eq(1.0).all()

    payload = json.loads((out / "playback" / "synthetic_emotion_eeg_raw.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "eeg-playback/3"
    assert set(payload["layers"]) == {"delta", "theta", "alpha", "mu", "smr", "lowbeta", "highbeta", "gamma"}
    n = len(payload["times"])
    assert all(len(layer["data"]) == n for layer in payload["layers"].values())
    assert len(payload["states_by_frame"]) == n == len(payload["quality"]["ok"])
    assert (out / "reports" / "states_report.html").is_file()


def test_lateralization_index_is_left_minus_right():
    spec = {"channels": ["C3", "C4"], "pairs": [["C3", "C4"]]}
    rows = [{"subject": s, "recording_key": f"{s}_1", "band": "mu", "channel": ch, "erd_db": v}
            for s, c3, c4 in [("S1", -2.0, -1.0), ("S2", -1.0, -0.5), ("S3", -3.0, -1.0)]
            for ch, v in (("C3", c3), ("C4", c4))]
    wide, summary = lateralization_summary(rows, spec)
    assert wide["C3-C4"].tolist() == [-1.0, -0.5, -2.0]
    pair = summary[summary["measure"] == "C3-C4"].iloc[0]
    assert pair["negative_subjects"] == 3 and pair["mean_db"] < 0 and pair["kind"] == "pair"
