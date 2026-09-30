# Legacy Synthetic Emotion Exports

Synthetische Emotion-/Kognitionsdaten für die EEG-Zustands-Demo.  
**Nur zu Demonstrationszwecken** – nicht klinisch oder wissenschaftlich als Emotionsklassifikator validiert.

Erzeugt auf Basis von Statistiken/Skalierung der Hand-Gesture-CSVs (Emotiv Flex 2, 32 Kanäle, 128 Hz) und dem Elektroden-Mapping der HTML-Visualisierung (`AF3` … `O2`).

## Dateien

| Datei | Beschreibung |
| --- | --- |
| `synthetic_emotion_eeg_raw.csv` | Roh-Zeitreihe: 7 Zustände × 10 s × 128 Hz ≈ 8960 Samples. Spalten: `time_s`, `sample_index`, `state_id`, `emotion_label`, `trigger_code`, danach 32 Elektroden. |
| `synthetic_emotion_bandpower.csv` | Long-Format: `state_id` × Elektrode × Band. Enthält u. a. `is_active`, `intensity_0_1`, `baseline_power`, `synthetic_power`, `power_ratio` – geeignet, um in der HTML-Demo Elektroden farbig zu highlighten. |
| `synthetic_emotion_dataset.json` | Metadaten, Banddefinitionen, Elektrodenliste und Zustands-Mappings (inkl. Trigger-Codes und Erklärtexten). |
| `synthetic_emotion_dataset.js` | Gleiches Schema als JS-Objekt (`SYNTHETIC_STATES`) zum Einbinden in HTML. |
| `eeg_zustaende.html` | Basis-Visualisierung mentaler Zustände. |
| `eeg_zustaende_synthetic_demo.html` | Fertige Demo inkl. synthetischer Emotion-Zustände – lokal im Browser öffnen. |
| `README_synthetic_emotion_dataset.txt` | Ursprüngliche Kurznotiz zur Dateierzeugung. |

## Zustände (Trigger)

| Code | Label |
| --- | --- |
| 200 | Neutral / Baseline |
| 201 | Freude / positive Valenz |
| 202 | Negative Valenz / Rückzug |
| 203 | Excitement / Arousal |
| 204 | Stress / Frustration |
| 205 | Entspannung / Ruhe |
| 206 | Fokus / Engagement |

## Nutzung

1. `eeg_zustaende_synthetic_demo.html` im Browser öffnen und Zustands-Chips anklicken.  
2. Für eigene Skripte: `synthetic_emotion_eeg_raw.csv` / `synthetic_emotion_bandpower.csv` laden.  
3. Mapping-Logik und Intensitäten stehen in `synthetic_emotion_dataset.json`.

## Hinweis zur Qualität

Die Muster (z. B. frontale Alpha-Asymmetrie, Frontal-Midline-Theta) sind **literaturnah modelliert** und an die Demo angepasst. Sie ersetzen keine echten Emotion-Aufnahmen mit dem Emotiv Flex 2.
