1) synthetic_emotion_bandpower.csv
   
Long-Format: state_id × electrode × band
Enthält is_active, intensity_0_1, baseline_power, synthetic_power und power_ratio.
im HTML pro Zustand die Elektroden farbig/highlighten

2) synthetic_emotion_eeg_raw.csv
   
Synthetische Rohdaten-Zeitreihe: 7 Zustände × 10 Sekunden × 128 Hz = 8960 Samples.
Spalten: time_s, sample_index, state_id, emotion_label, trigger_code, danach 32 Elektroden.
Trigger-Codes: 200 Neutral, 201 positive Valenz/Freude, 202 negative Valenz/Rückzug, 203 Arousal, 204 Stress, 205 Entspannung, 206 Fokus.

3) synthetic_emotion_dataset.js
   
Direktes JS-Objekt im gleichen Schema wie eure STATES-Mappings.
Manuell in eure HTML einbindbar:<script src="synthetic_emotion_dataset.js"></script><script>STATES.push(...SYNTHETIC_STATES);</script>
 In unserer aktuellen Datei liegen STATES/BANDS aber im selben Script-Block; deshalb ist die fertige Demo-HTML unten am einfachsten.

4) eeg_zustaende_synthetic_demo.html
   
Fertige Version unserer HTML mit zusätzlichen synthetischen Emotion-Zuständen.
Einfach öffnen und die neuen Chips anklicken.

Wichtig:
Die EEG-Kanalnamen wurden auf Basis unseres HTML-Mappings zugeordnet: CSV-Spalten 2..33 -> AF3..O2.
Die Skalen wurden aus Mittelwert/Standardabweichung und groben Bandpower-Schätzungen der hochgeladenen CSVs abgeleitet.