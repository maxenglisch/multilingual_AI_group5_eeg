
from pathlib import Path
import pandas as pd
import numpy as np
import mne

SFREQ = 128
EEG_COLS = [str(i) for i in range(2, 34)]

def load_eeg_csv_as_raw(csv_path, sfreq=SFREQ):
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    missing_cols = [c for c in EEG_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Datei hat keine vollständigen EEG-Kanäle. "
            f"Shape={df.shape}, fehlende Spalten={missing_cols[:5]}"
        )

    eeg_data = df[EEG_COLS].to_numpy().T * 1e-6
    stim_data = df["Triggers"].to_numpy()[None, :]

    data = np.vstack([eeg_data, stim_data])

    ch_names = [f"EEG{i+1:02d}" for i in range(32)] + ["STI 014"]
    ch_types = ["eeg"] * 32 + ["stim"]

    info = mne.create_info(
        ch_names=ch_names,
        sfreq=sfreq,
        ch_types=ch_types
    )

    raw = mne.io.RawArray(data, info, verbose=False)
    return raw, df


def extract_events_from_df(df):
    trig = df["Triggers"].to_numpy()

    event_samples = np.where((trig != 0) & (np.r_[0, trig[:-1]] == 0))[0]
    event_ids = trig[event_samples].astype(int)

    events = np.column_stack([
        event_samples,
        np.zeros(len(event_samples), dtype=int),
        event_ids
    ])

    return events


def find_good_eeg_files(raw_dir):
    raw_dir = Path(raw_dir)
    subject_dirs = sorted([p for p in raw_dir.glob("SUBJECT*") if p.is_dir()])

    good_files = []
    bad_files = []

    for subject_dir in subject_dirs:
        eeg_files = sorted(subject_dir.glob("*_EEG.csv"))

        for csv_file in eeg_files:
            try:
                df_check = pd.read_csv(csv_file)
                df_check.columns = [str(c).strip() for c in df_check.columns]

                if all(c in df_check.columns for c in EEG_COLS):
                    good_files.append(csv_file)
                else:
                    bad_files.append(csv_file)

            except Exception:
                bad_files.append(csv_file)

    return good_files, bad_files


def build_epochs_from_files(
    eeg_files,
    event_code=7711,
    l_freq=1.0,
    h_freq=40.0,
    tmin=-1.0,
    tmax=2.0,
    baseline=(-1.0, 0.0),
):
    all_epochs = []

    for csv_file in eeg_files:
        raw, df = load_eeg_csv_as_raw(csv_file)
        events = extract_events_from_df(df)

        raw.filter(
            l_freq=l_freq,
            h_freq=h_freq,
            picks="eeg",
            verbose=False
        )

        raw.set_eeg_reference("average", verbose=False)

        epochs = mne.Epochs(
            raw,
            events,
            event_id={f"event_{event_code}": event_code},
            tmin=tmin,
            tmax=tmax,
            baseline=baseline,
            picks="eeg",
            preload=True,
            verbose=False
        )

        if len(epochs) > 0:
            all_epochs.append(epochs)

    if not all_epochs:
        raise RuntimeError("Keine gültigen Epochs gefunden.")

    return mne.concatenate_epochs(all_epochs)
