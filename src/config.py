from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "dataset.yaml"

def load_config(path=None):
    with Path(path or DEFAULT_CONFIG).open(encoding="utf-8-sig") as handle:
        config = yaml.safe_load(handle)
    # Configurations written before the dataset block existed are the MRCP dataset.
    config.setdefault("dataset", {"name": "mendeley_mrcp", "adapter": "mendeley_mrcp"})
    adapter = config["dataset"].get("adapter")
    if adapter not in VALIDATORS:
        raise ValueError(f"Unknown dataset adapter {adapter!r}; expected one of {sorted(VALIDATORS)}")
    VALIDATORS[adapter](config)
    config.setdefault("analyses", ["mrcp"] if adapter == "mendeley_mrcp" else ["states"])
    unknown = set(config["analyses"]) - {"mrcp", "states"}
    if unknown:
        raise ValueError(f"Unknown analyses {sorted(unknown)}; expected mrcp and/or states")
    if "mrcp" in config["analyses"] and adapter != "mendeley_mrcp":
        raise ValueError("The mrcp analysis needs movement triggers and EMG; only the mendeley_mrcp dataset has them")
    if "states" in config["analyses"]:
        _validate_states(config)
    return config


def _validate_mendeley(config):
    eeg = config["eeg"]
    columns = [str(x) for x in eeg["channel_columns"]]
    names = list(eeg["channel_names"])
    mapping = {str(k): v for k, v in eeg["column_mapping"].items()}
    expected = int(eeg["expected_channel_count"])
    if float(eeg["sampling_rate"]) != 128.0:
        raise ValueError("This dataset configuration requires EEG sampling_rate=128")
    if len(columns) != expected or len(names) != expected:
        raise ValueError("channel_columns/channel_names must contain exactly 32 entries")
    if mapping != dict(zip(columns, names)):
        raise ValueError("column_mapping must exactly match channel_columns + channel_names")
    required_excluded = {"Triggers", "0", "1", "34", "35", "36", "37"}
    if set(map(str, eeg["excluded_columns"])) != required_excluded:
        raise ValueError(f"excluded_columns must be {sorted(required_excluded)}")
    if config["sampling_rates"] != {"eeg": 128.0, "emg": 440.0}:
        raise ValueError("sampling_rates must define EEG=128 and EMG=440")
    if config["units"] != {"eeg_input": "uV", "eeg_mne": "V", "emg": "ADC units"}:
        raise ValueError("units must explicitly define EEG uV->V and EMG ADC units")
    expected_windows = {"tmin_s", "tmax_s", "baseline_start_s", "baseline_end_s",
                        "pre_start_s", "pre_end_s", "movement_start_s", "movement_end_s",
                        "post_start_s", "post_end_s"}
    if set(config["epochs"]) != expected_windows:
        raise ValueError("epochs must contain the complete centralized feature windows")
    if {int(v) for v in config["trigger_codes"].values()} != {768, 771, 7711, 7712, 1000, 32766}:
        raise ValueError("trigger_codes are incomplete")
    codes = {int(v) for v in config["trigger_codes"].values()}
    for segment in config.get("states", {}).get("segments", []):
        stray = {int(c) for c in segment["start"] + segment["stop"]} - codes
        if stray:
            raise ValueError(f"states.segments[{segment['label']}] uses unknown trigger codes {sorted(stray)}")


def _validate_synthetic(config):
    eeg = config["eeg"]
    if str(eeg["input_unit"]) != "uV" or str(eeg["mne_unit"]) != "V":
        raise ValueError("synthetic_emotion requires EEG input in uV converted to V")
    if len(eeg["channel_names"]) != int(eeg["expected_channel_count"]):
        raise ValueError("channel_names must match expected_channel_count")
    for key in ("file", "label_column", "trigger_column"):
        if not config.get("source", {}).get(key):
            raise ValueError(f"source.{key} is required for synthetic_emotion")
    states = config.get("states", {})
    if not states.get("baseline_labels"):
        raise ValueError("states.baseline_labels must name the resting section")
    if "expected_states" not in states:
        raise ValueError("states.expected_states must map every label to a state id or null")


def _validate_states(config):
    states = config.get("states")
    if not states:
        raise ValueError("The states analysis requires a states block")
    for key in ("definitions", "bandpass", "window_s", "step_s", "playback_step_s", "quality_gate"):
        if key not in states:
            raise ValueError(f"states.{key} is required")
    lo, hi = map(float, states["bandpass"])
    nyquist = float(config["eeg"]["sampling_rate"]) / 2.0
    if not 0 < lo < hi < nyquist:
        raise ValueError(f"states.bandpass must satisfy 0 < low < high < Nyquist ({nyquist:g} Hz)")
    if float(states["step_s"]) <= 0 or float(states["window_s"]) < float(states["step_s"]):
        raise ValueError("states.window_s must be >= states.step_s > 0")
    ratio = float(states["playback_step_s"]) / float(states["step_s"])
    if abs(ratio - round(ratio)) > 1e-9 or round(ratio) < 1:
        raise ValueError("states.playback_step_s must be a whole multiple of states.step_s")
    gate = states["quality_gate"]
    for key in ("max_ptp_uv", "min_std_uv", "max_bad_channel_fraction", "min_good_frame_fraction"):
        if key not in gate:
            raise ValueError(f"states.quality_gate.{key} is required")
    if not (ROOT / "config" / states["definitions"]).is_file():
        raise ValueError(f"states.definitions not found: config/{states['definitions']}")


def states_definitions_path(config):
    return ROOT / "config" / config["states"]["definitions"]


VALIDATORS = {"mendeley_mrcp": _validate_mendeley, "synthetic_emotion": _validate_synthetic}
