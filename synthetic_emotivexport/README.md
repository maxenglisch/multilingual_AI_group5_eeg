# Synthetic EmotivPRO Export

Dummy-Daten und Import-Tools im Stil eines **EmotivPRO CSV V2**-Exports (32 Sensoren, 128 Hz).  
Ziel: Schema validieren, MNE-Import testen und Browser-Adapter entwickeln – **ohne** echte EmotivPRO-Aufnahmen.

## Schema (Kurz)

- Zeile 1: Metadata (`key:value`, u. a. `title`, `sampling rate`)  
- Zeile 2: Spaltenheader  
- Prefix-Gruppen: `EEG.*`, `MOT.*`, `CQ.*` / `EQ.*`, `POW.*`, `PM.*`, Marker-Spalten  

Details: [`schema_columns.json`](schema_columns.json), Sensorliste und Pflicht-Prefixes.

## Dateien

| Pfad | Beschreibung |
| --- | --- |
| `emotivpro_v2_all_streams_dummy.csv` | Vollständiger All-Streams-Dummy |
| `preview_first_rows.csv` | Kurzer Preview-Ausschnitt |
| `markers.csv` / `markers.json` | Marker-Beispiele |
| `dummy_raw.fif` | Beispiel nach MNE-Export |
| `epocflex_channel_mapping_dummy.json` | Kanal-Mapping-Dummy |
| `v1_split/` | Getrennte Streams (EEG/CQ/EQ, Motion, Bandpower, Performance Metrics) |
| `error_cases/` | Negativbeispiele für Parser-Tests |
| `src/emotivpro_mne_import.py` | Metadata parsen, Schema prüfen, `mne.io.RawArray` erzeugen |
| `src/emotivpro_browser_adapter.js` | Adapter Richtung Frontend |
| `src/smoke_test.py` | Smoke Test |

## Error Cases

| Datei | Erwartetes Problem |
| --- | --- |
| `missing_metadata_line.csv` | Fehlende EmotivPRO-Metadata-Zeile |
| `bad_sampling_rate_metadata.csv` | Ungültige Sampling Rate |
| `missing_required_bandpower_column.csv` | Fehlende `POW.*`-Pflichtspalte |
| `bad_numeric_motion_value.csv` | Nicht-numerischer Motion-Wert |
| `pm_metric_nulls_in_good_segment.csv` | Nulls in Performance-Metrics |

## Schnellstart (Import)

```bash
# aus Repo-Root, mit installiertem mne + pandas + numpy
python synthetic_emotivexport/src/emotivpro_mne_import.py \
  synthetic_emotivexport/emotivpro_v2_all_streams_dummy.csv
```

Optional FIF speichern:

```bash
python synthetic_emotivexport/src/emotivpro_mne_import.py \
  synthetic_emotivexport/emotivpro_v2_all_streams_dummy.csv \
  --save-fif synthetic_emotivexport/out_raw.fif
```

## Zusammenhang im Projekt

Dieser Ordner ergänzt die **Hand-Gesture-Pipeline** (`pipeline_prototype/`) und die **synthetischen Emotion-Exports** (`legacy_synthetic_exports/`): hier geht es um das **Dateiformat / Import**, nicht um Emotionslabels.
