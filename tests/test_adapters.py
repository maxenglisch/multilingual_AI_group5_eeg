import numpy as np
import pandas as pd

from src.adapters import (MendeleyMrcpAdapter, SyntheticEmotionAdapter, segments_from_events,
                          segments_from_labels)
from src.config import ROOT, load_config

DEFINITIONS = load_config()["states"]["segments"]


def _events(pairs, sfreq=128):
    return np.array([[int(t * sfreq), 0, code] for t, code in pairs], dtype=int)


def test_segments_follow_the_trial_structure():
    events = _events([(0.0, 771), (1.5, 7711), (6.5, 7712), (8.5, 1000),
                      (10.0, 771), (11.5, 7711), (16.5, 7712), (18.5, 1000), (20.0, 32766)])
    seg = segments_from_events(events, 128, DEFINITIONS)
    assert seg["label"].tolist() == ["preparation", "movement", "post_movement", "rest",
                                     "preparation", "movement", "post_movement"]
    rest = seg[seg["label"] == "rest"].iloc[0]
    assert (rest["start_s"], rest["stop_s"], rest["baseline"]) == (8.5, 10.0, True)
    assert seg[seg["label"] == "movement"]["expected_state"].eq("motorik_rechts").all()


def test_unterminated_and_short_sections_are_dropped():
    # 7711 twice in a row: the first movement has no 7712 before the next start
    events = _events([(0.0, 771), (1.5, 7711), (3.0, 7711), (8.0, 7712), (8.5, 1000), (9.0, 771)])
    seg = segments_from_events(events, 128, DEFINITIONS)
    movement = seg[seg["label"] == "movement"]
    assert list(zip(movement["start_s"], movement["stop_s"])) == [(3.0, 8.0)]
    assert "rest" not in seg["label"].tolist()                          # 0.5 s < min_duration_s


def test_segments_from_labels():
    labels = ["a"] * 4 + ["b"] * 2 + ["a"] * 2
    seg = segments_from_labels(labels, 2.0, {"a": None, "b": "x"}, {"a"})
    assert seg[["start_s", "stop_s", "label", "trial"]].values.tolist() == [
        [0.0, 2.0, "a", 1], [2.0, 3.0, "b", 1], [3.0, 4.0, "a", 2]]
    assert seg["baseline"].tolist() == [True, False, True]


def test_synthetic_adapter_reads_the_repository_file():
    cfg = load_config(ROOT / "config" / "synthetic_emotion.yaml")
    (key, recording, error), = list(SyntheticEmotionAdapter(cfg).recordings())
    assert error is None
    assert recording.raw.info["sfreq"] == 128.0 and len(recording.raw.ch_names) == 32
    assert len(recording.segments) == 7 and recording.segments["baseline"].sum() == 1
    assert recording.warnings == []
    # microvolts in the CSV, volts in MNE
    assert 1e-6 < recording.raw.get_data().std() < 1e-4


def test_mendeley_adapter_on_a_small_fabricated_recording(tmp_path):
    sfreq, seconds = 128, 24
    n = sfreq * seconds
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({"Triggers": np.zeros(n, int)})
    for column in range(38):
        frame[str(column)] = rng.normal(0, 5, n).round(3) if 2 <= column <= 33 else 0
    for t, code in [(0.0, 771), (1.5, 7711), (6.5, 7712), (8.5, 1000), (10.0, 771),
                    (11.5, 7711), (16.5, 7712), (18.5, 1000), (20.0, 771), (21.5, 7711)]:
        frame.loc[int(t * sfreq), "Triggers"] = code
    folder = tmp_path / "SUBJECT01"; folder.mkdir()
    frame.to_csv(folder / "SUBJECT01_Trial_01_EEG.csv", index=False)

    adapter = MendeleyMrcpAdapter(load_config(), tmp_path)
    assert adapter.subjects() == ["SUBJECT01"]
    (key, recording, error), = list(adapter.recordings("SUBJECT01"))
    assert error is None and key == "SUBJECT01_Trial_01"
    assert recording.raw.ch_names[12] == "C3"                           # column "14"
    assert recording.segments["label"].value_counts().to_dict() == {
        "preparation": 3, "movement": 2, "post_movement": 2, "rest": 2}
