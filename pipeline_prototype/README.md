# Pipeline Prototype (MNE)

Prototyp einer EEG-Preprocessing-Pipeline auf dem **Hand Gesture**-Datensatz (Emotiv Flex 2, 32 Kanäle, 128 Hz).

## Inhalt

| Pfad | Beschreibung |
| --- | --- |
| `data/raw/` | Rohdaten (`SUBJECT*/…_EEG.csv`, EMG, Docs) |
| `src/eeg_pipeline.py` | CSV → `RawArray`, Events, Filter, Average-Ref, Epochs |
| `01_check_data.ipynb` | Exploratives Notebook |
| `outputs/figures/` | Beispiel-Plots (Averaged Evoked) |
| `environment.yml` | Conda-Environment `eeg-mne` |

## Pipeline-Schritte (aktuell)

1. EEG-CSV laden (Kanäle `2`–`33` + `Triggers`)  
2. `mne.io.RawArray` (µV → V)  
3. Events aus Trigger-Flanken  
4. Bandpass 1–40 Hz  
5. Average-Referenz  
6. Epoching (z. B. Event `7711`), Baseline −1…0 s  
7. Concatenate / Average / Plot  

**Geplant / recherchiert:** Erweiterung mit **PyPREP** (Bad Channels, robustere Referenz) und vollständiges 10-10-Kanalnamen-Mapping.

## Environment

```bash
conda env create -f environment.yml
conda activate eeg-mne
```

## Herkunft der Daten

- [Mendeley – EEG/EMG Hand Gesture (MRCP)](https://data.mendeley.com/datasets/y23s2xg6x4/1)  
- Paper: [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2352340926001496)

Siehe auch die Projekt-Abschlussdoku in der Root-[`README.md`](../README.md).
