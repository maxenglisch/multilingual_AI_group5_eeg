from pathlib import Path
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "dataset.yaml"

def load_config(path=None):
    with Path(path or DEFAULT_CONFIG).open(encoding="utf-8-sig") as handle:
        config = yaml.safe_load(handle)
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
    return config
