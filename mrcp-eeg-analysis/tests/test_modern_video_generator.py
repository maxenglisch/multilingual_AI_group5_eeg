from pathlib import Path
import os
import sys

import numpy as np
import pytest

from src.config import load_config
from src.video_generator import _load_emg_trace, generate_subject_video, main
from src.video_utils import calculate_mrcp_signals, create_mrcp_animation, save_animation


class DummyEpochs:
    def __init__(self, data, names):
        self._data = np.asarray(data, dtype=float)
        self.ch_names = list(names)

    def get_data(self, copy=False):
        return self._data.copy() if copy else self._data


def _valid_mp4(path, marker=b"x"):
    Path(path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + marker * 2048)


def test_mrcp_waveform_uses_roi_but_topomap_keeps_all_channels():
    # The full CAR-like mean is exactly flat, while the C3/Cz ROI is not.
    time_signal = np.linspace(0.0, 2.0, 5)
    epoch = np.stack([time_signal, time_signal, -2.0 * time_signal]) * 1e-6
    signals = calculate_mrcp_signals(DummyEpochs(epoch[None, :, :], ["C3", "Cz", "O1"]), ["C3", "Cz"])
    assert signals.eeg_uv.shape == (3, 5)
    assert np.allclose(signals.all_channel_mean, 0.0)
    assert np.allclose(signals.mrcp_waveform, time_signal)
    assert signals.available_mrcp_channels == ["C3", "Cz"]


def test_missing_roi_channels_are_reported_but_available_roi_is_used():
    data = np.ones((1, 2, 4), dtype=float) * 1e-6
    signals = calculate_mrcp_signals(DummyEpochs(data, ["C3", "O1"]), ["C3", "Cz"])
    assert signals.available_mrcp_channels == ["C3"]
    assert signals.missing_mrcp_channels == ["Cz"]


def test_real_emg_is_loaded_and_missing_emg_is_clean(tmp_path):
    import pandas as pd

    cfg = load_config()
    count = 2200
    triggers = np.zeros(count, dtype=int)
    triggers[1100] = int(cfg["mrcp"][cfg["mrcp"]["lock"]]["event_code"])
    path = tmp_path / "SUBJECT01_Trial_01_EMG.csv"
    pd.DataFrame({"Triggers": triggers, "EMG": np.sin(np.arange(count) / 20.0)}).to_csv(path, index=False)
    import logging
    trace = _load_emg_trace(path, cfg, logging.getLogger("test"))
    assert trace is not None
    assert len(trace[0]) == len(trace[1]) == 1760
    assert np.isfinite(trace[1]).all()
    assert _load_emg_trace(None, cfg, logging.getLogger("test")) is None


def test_animation_renders_headlessly_with_mne_topomap():
    if os.name == "nt" and sys.version_info >= (3, 14):
        pytest.skip("Matplotlib has an uncatchable native crash on the supported Windows/Python 3.14 build")
    import matplotlib.pyplot as plt
    import mne

    names = ["C3", "Cz", "C4", "O1"]
    info = mne.create_info(names, 16.0, "eeg")
    standard = mne.channels.make_standard_montage("standard_1020")
    positions = standard.get_positions()["ch_pos"]
    # Explicit head coordinates avoid the fragile native fiducial transform on
    # the supported Windows/Python environment, just like production make_raw.
    montage = mne.channels.make_dig_montage(
        ch_pos={name: positions[name] for name in names}, coord_frame="head")
    info.set_montage(montage)
    data = np.random.default_rng(4).normal(scale=1e-6, size=(2, len(names), 65))
    epochs = mne.EpochsArray(data, info, tmin=-2.0, verbose=False)
    animation, fig, frames, duration, warnings = create_mrcp_animation(
        epochs, subject_id="SUBJECT04", fps=2, mrcp_channels=["C3", "Cz"],
        expected_channels=names, emg_trace=None)
    animation._func(0)
    fig.canvas.draw()
    assert frames > 1 and duration == 4.0
    assert any(text.get_text() == "Grand-average MRCP" for text in fig.axes[0].texts) is False
    assert fig._suptitle.get_text() == "SUBJECT04 · movement-related EEG/EMG"
    assert not any("Fewer than three" in warning for warning in warnings)
    plt.close(fig)


def test_existing_video_skips_and_force_replaces(monkeypatch, tmp_path):
    video_dir = tmp_path / "outputs" / "videos"
    video_dir.mkdir(parents=True)
    existing = video_dir / "SUBJECT01.mp4"
    _valid_mp4(existing, b"o")
    skipped = generate_subject_video("SUBJECT01", tmp_path / "data", tmp_path / "outputs")
    assert skipped["status"] == "skipped"

    monkeypatch.setattr("src.video_generator.validate_subject", lambda *_args: {
        "valid": True, "eeg_file": "unused.csv", "emg_file": None,
    })
    monkeypatch.setattr("src.video_generator._load_subject_epochs", lambda *_args: (
        object(), None, ["C3"], ["C3"], "mock input", []))
    monkeypatch.setattr("src.video_generator.create_mrcp_animation", lambda *_args, **_kwargs: (
        object(), None, 9, 4.0, []))

    def fake_save(_animation, output, subject, **_kwargs):
        path = Path(output) / f"{subject}.mp4"
        _valid_mp4(path, b"n")
        return path, "mp4", None

    monkeypatch.setattr("src.video_generator.save_animation", fake_save)
    generated = generate_subject_video("SUBJECT01", tmp_path / "data", tmp_path / "outputs", force=True)
    assert generated["status"] == "generated"
    assert b"n" in existing.read_bytes()


def test_modern_writer_falls_back_to_gif(monkeypatch, tmp_path):
    class Animation:
        def save(self, path, writer, dpi):
            Path(path).write_bytes(b"GIF89a" + b"x" * 2048)

    monkeypatch.setattr("src.video_utils.ffmpeg_available", lambda: False)
    monkeypatch.setattr("src.video_utils.pillow_available", lambda: True)
    path, actual_format, reason = save_animation(
        Animation(), tmp_path, "SUBJECT01", requested_format="mp4", fps=2, dpi=50)
    assert path.name == "SUBJECT01.gif" and actual_format == "gif"
    assert "FFmpeg unavailable" in reason


def test_cli_list_discovers_subjects_without_generating(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("src.video_generator.discover_subjects", lambda _path: ["SUBJECT01"])
    monkeypatch.setattr("src.video_generator.validate_subject", lambda *_args: {
        "input": "input.csv", "valid": True,
    })
    assert main(["--data-dir", str(tmp_path), "--output-dir", str(tmp_path / "outputs"), "--list"]) == 0
    assert "SUBJECT01\tinput.csv" in capsys.readouterr().out


def test_legacy_module_has_no_manual_pil_renderer():
    source = (Path(__file__).parents[1] / "src" / "make_video.py").read_text(encoding="utf-8")
    assert "from PIL import" not in source
    assert "draw.ellipse" not in source
    assert "create_mrcp_animation" in source
