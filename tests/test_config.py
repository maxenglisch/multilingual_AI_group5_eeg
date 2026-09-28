import pytest
import yaml

from src.config import DEFAULT_CONFIG, ROOT, load_config


def _write(tmp_path, cfg):
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_default_config_is_mrcp_dataset_with_both_analyses():
    cfg = load_config()
    assert cfg["dataset"]["adapter"] == "mendeley_mrcp"
    assert cfg["analyses"] == ["mrcp", "states"]


def test_synthetic_config_runs_states_only():
    cfg = load_config(ROOT / "config" / "synthetic_emotion.yaml")
    assert cfg["analyses"] == ["states"]


def test_config_without_dataset_block_is_the_mrcp_dataset(tmp_path):
    cfg = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    for key in ("dataset", "analyses", "states"):
        cfg.pop(key)
    loaded = load_config(_write(tmp_path, cfg))
    assert loaded["dataset"]["adapter"] == "mendeley_mrcp"
    assert loaded["analyses"] == ["mrcp"]


def test_mrcp_is_rejected_for_the_synthetic_dataset(tmp_path):
    cfg = yaml.safe_load((ROOT / "config" / "synthetic_emotion.yaml").read_text(encoding="utf-8"))
    cfg["analyses"] = ["mrcp", "states"]
    with pytest.raises(ValueError, match="mrcp"):
        load_config(_write(tmp_path, cfg))


def test_mrcp_checks_still_apply(tmp_path):
    cfg = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    cfg["eeg"]["sampling_rate"] = 256.0
    with pytest.raises(ValueError, match="sampling_rate=128"):
        load_config(_write(tmp_path, cfg))


@pytest.mark.parametrize("key,value,message", [
    ("playback_step_s", 0.3, "whole multiple"),
    ("bandpass", [1.0, 70.0], "Nyquist"),
])
def test_invalid_states_settings(tmp_path, key, value, message):
    cfg = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    cfg["states"][key] = value
    with pytest.raises(ValueError, match=message):
        load_config(_write(tmp_path, cfg))


def test_segment_codes_must_be_known_triggers(tmp_path):
    cfg = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    cfg["states"]["segments"][0]["start"] = [999]
    with pytest.raises(ValueError, match="unknown trigger codes"):
        load_config(_write(tmp_path, cfg))
