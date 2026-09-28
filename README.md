# Integrated Movement-Related EEG/EMG MRCP Pipeline

This is the integrated successor to the old `002/eeg_project` prototype. The
default and only active pipeline analyzes the public right-hand fist-closure
Movement-Related EEG/EMG dataset. It is **not an emotion-recognition pipeline**
and the dataset contains no emotion labels.

The raw CSV files are read-only inputs. They are never renamed, moved, rewritten
or copied into this project. Pass the existing D-drive folder with `--data-dir`.

## Authoritative dataset configuration

`config/dataset.yaml` is the single source of truth. For this export it defines:

- EEG sampling rate: 128 Hz
- EMG sampling rate: 440 Hz
- EEG input units: uV; MNE internal units: V
- anonymous EEG source columns: `2` through `33`
- excluded columns: `Triggers, 0, 1, 34, 35, 36, 37`
- all 32 electrode names and all six trigger codes
- CAR and the 0.1-1 Hz MRCP Butterworth filter

Code must not infer EEG channels from numeric dtype, take the first 32 columns,
or invent a position-to-electrode mapping. If the configured mapping does not
match the CSV, that file fails with a diagnostic report.

## Install

From `D:\Uni\10\MUlti\002_mrcp_integrated`:

```powershell
python -m pip install -r requirements.txt
```

No Conda reinstall is required.

## Run

Analyze SUBJECT01:

```powershell
python -m src.main --data-dir "D:\Uni\10\MUlti\EEG and EMG Dataset for Analyzing Movement-Related\SUBJECTS" --output-dir outputs --subject SUBJECT01
```

Scan and diagnose the complete dataset without filtering or plotting:

```powershell
python -m src.main --data-dir "D:\Uni\10\MUlti\EEG and EMG Dataset for Analyzing Movement-Related\SUBJECTS" --output-dir outputs --dry-run
```

Generate an optional non-interactive MRCP/EEG activity video:

```powershell
python -m src.main --data-dir "D:\Uni\10\MUlti\EEG and EMG Dataset for Analyzing Movement-Related\SUBJECTS" --output-dir outputs --subject SUBJECT01 --make-video true
```

Save the validated original, CAR and MRCP-filtered MNE objects:

```powershell
python -m src.main --data-dir "D:\Uni\10\MUlti\EEG and EMG Dataset for Analyzing Movement-Related\SUBJECTS" --output-dir outputs --subject SUBJECT01 --save-fif true
```

Both options can be combined. No command calls `plt.show()` or `raw.plot()`.

Analyze every discovered subject with failure isolation and group-level output:

```powershell
python -m src.main --data-dir "D:\Uni\10\MUlti\EEG and EMG Dataset for Analyzing Movement-Related\SUBJECTS" --output-dir outputs --all-subjects
```

Analyze a selected set:

```powershell
python -m src.main --data-dir "D:\Uni\10\MUlti\EEG and EMG Dataset for Analyzing Movement-Related\SUBJECTS" --output-dir outputs --subjects SUBJECT01 SUBJECT02 SUBJECT03
```

Generate the three descriptive Motorik bar charts from existing group CSVs,
without rereading or processing raw EEG/EMG:

```powershell
python -m src.main --output-dir outputs --make-motorik-barcharts
```

This writes valid motor events per subject, the most frequently prominent
configured MRCP channel, and left/midline/right scalp-channel-group frequency.
The charts describe retained right-hand movement epochs; they do not measure
nerve use, localize brain activation, or establish statistical significance.

`--subject`, `--subjects`, and `--all-subjects` are mutually exclusive. Batch
mode never creates videos automatically. Use either `--make-video` or
`--make-video true` together with one `--subject`.

## Outputs

Subject runs write under `outputs/SUBJECT01/`:

```text
figures/   raw EEG, montage, MRCP, EMG, and EEG-EMG alignment PNGs
tables/    inventory, missing pairs, channel diagnostics, events, trigger counts
reports/   mrcp_report.html
logs/      pipeline.log and warnings.txt
videos/    mrcp_eeg_activity.mp4, or .gif if MP4 writing is unavailable
fif/       raw_original.fif, raw_car.fif, raw_mrcp_filtered.fif
```

An unfiltered full dry-run writes its inventory and diagnostics directly below
the selected output root.

Group runs also write `outputs/group_analysis/`, containing per-subject and
per-recording QC, epoch-level MRCP features, EEG-EMG latency features,
subject-weighted group timeseries, static PNGs, and an interactive HTML report.
Group means are calculated from subject-level averages so participants with
more usable epochs do not receive greater weight.

## Optional format adapters

`src/format_adapters.py` retains the useful idea of supporting EDF, BDF, GDF,
SET, FIF and MAT. It is not used by the CSV main path. Callers must explicitly
provide and validate channel names, sampling rate and units; there is no
first-32-numeric-columns fallback.

## Legacy 002 code

The former emotion, EEGEmotions-27, generic loader, dashboard, analysis and
general preprocessing modules are preserved under `legacy/` for historical
reference only. They are not imported by `src.main`. In particular,
`emotion_mapping.py` and emotion-frequency outputs are not part of MRCP runs.

## Scientific caution

This is a research signal-processing workflow, not a medical diagnostic tool.
Differences in figures are not automatically statistically significant. High
activity at one electrode cannot by itself establish creativity, emotion,
attention, disease or any other psychological state. MRCP interpretation depends
on event quality, preprocessing, artifact control and averaging across trials.

## Tests

```powershell
python -m pytest
```

`pytest.ini` keeps temporary test files inside the project so Windows user-temp
ACL problems do not affect `tmp_path` tests.

## Development note

This project was developed with assistance from AI coding tools.
All generated code was reviewed, tested, and adapted for the EEG
dataset and analysis workflow used in this project.