# Anleitung: EEG-Pipeline (MRCP und Zustandsanalyse)

Die Pipeline hat zwei Analysen, die sich Einlesen, Kanalprüfung, Umrechnung
µV → V und Common Average Reference teilen:

| Analyse | Was sie macht | Abschnitt |
|---|---|---|
| `mrcp` | Movement-Related Cortical Potentials im Zeitbereich (0,1–1 Hz) mit EMG-Abgleich | 3 |
| `states` | Bewertung der mentalen Zustände aus `config/states.json` über die Bandleistung | 4 bis 10 |

Sie läuft auf zwei Datensätzen:

| Datensatz | Konfiguration | Analysen | Wofür |
|---|---|---|---|
| Movement-Related EEG/EMG (rechter Faustschluss, 40 Probanden) | `config/dataset.yaml` (Standard) | `mrcp`, `states` | echte Daten; MRCP, Motorik-Signatur und Seitenvergleich C3/C4 |
| Synthetischer Emotionsdatensatz (7 Zustände × 10 s) | `config/synthetic_emotion.yaml` | `states` | Demonstration, dass die Zustandsanalyse von der CSV bis zur Oberfläche durchläuft |

---

## 1. Einrichten

Voraussetzung: Python 3.10 oder neuer (getestet mit 3.14).

```powershell
cd C:\Users\lawan\dev\multilingual_AI_group5_eeg
python -m pip install -r requirements.txt
```

Der MRCP-Datensatz liegt nicht im Repository. Beim Aufruf wird der Ordner
`SUBJECTS` des Datensatzes mit `--data-dir` angegeben, zum Beispiel:

```text
C:\Users\lawan\Downloads\EEG and EMG Dataset for Analyzing Movement-Related\EEG and EMG Dataset for Analyzing Movement-Related\SUBJECTS
```

Die Rohdaten werden nur gelesen, nie verändert oder kopiert.

Alle Befehle in dieser Anleitung werden im Repository-Ordner ausgeführt. In
den Beispielen steht `<SUBJECTS>` für den Pfad oben (in Anführungszeichen,
weil er Leerzeichen enthält).

---

## 2. Beide Analysen zusammen

Ohne `--analysis` laufen alle Analysen, die unter `analyses` in der
Konfiguration stehen – für `config/dataset.yaml` also MRCP und Zustände:

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --all-subjects
```

Dauer: etwa 2 Minuten für 40 Probanden. Mit `--analysis mrcp` oder
`--analysis states` läuft nur eine der beiden.

### Alle Optionen

| Option | Analyse | Bedeutung |
|---|---|---|
| `--config <datei>` | beide | Datensatz-Konfiguration; ohne Angabe `config/dataset.yaml` |
| `--data-dir <ordner>` | beide | Ordner `SUBJECTS` des MRCP-Datensatzes; beim synthetischen Datensatz optional |
| `--output-dir <ordner>` | beide | Zielordner, üblich `outputs` |
| `--subject X` / `--subjects X Y` / `--all-subjects` | beide | ein, mehrere oder alle Probanden; schließen sich gegenseitig aus |
| `--analysis mrcp\|states\|all` | beide | welche Analyse; ohne Angabe die unter `analyses` in der Konfiguration |
| `--dry-run` | mrcp | nur Inventar und Diagnose, ohne Filtern und Plotten; die Zustandsanalyse wird übersprungen |
| `--make-video [true]` | mrcp | Animation aus Wellenform, Kopfkarte und EMG; nur mit `--subject` |
| `--video-fps <n>` | mrcp | Bildrate der Animation (Standard 10) |
| `--save-fif true` | mrcp | MNE-Objekte als FIF speichern |
| `--make-motorik-barcharts` | mrcp | Motorik-Balkendiagramme aus vorhandenen Gruppentabellen, ohne Rohdaten |
| `--make-playback true\|false` | states | Playback-JSON je Aufnahme; ohne Angabe nur bei einem einzelnen Probanden |

---

## 3. MRCP-Analyse

Die MRCP-Analyse (von Jinghao) mittelt das EEG um den Bewegungsbeginn
(Trigger 7711, −2 bis +2 s) nach CAR und einem Butterworth-Bandpass
0,1–1 Hz, extrahiert Merkmale je Epoche und Kanal und gleicht das EEG mit der
EMG-Hüllkurve ab.

### Befehle

Ein Proband:

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --subject SUBJECT01 --analysis mrcp
```

Alle Probanden mit Gruppenbericht:

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --all-subjects --analysis mrcp
```

Ausgewählte Probanden, ebenfalls mit Gruppenbericht:

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --subjects SUBJECT01 SUBJECT02 --analysis mrcp
```

Nur prüfen, ohne Filtern und Plotten (Inventar, Kanäle, Trigger):

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --dry-run
```

Mit Animation (nur für einen Probanden):

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --subject SUBJECT01 --analysis mrcp --make-video true
```

Mit gespeicherten MNE-Objekten:

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --subject SUBJECT01 --analysis mrcp --save-fif true
```

Motorik-Balkendiagramme aus den Tabellen eines früheren Gruppenlaufs (liest
keine Rohdaten, braucht kein `--data-dir`):

```powershell
python -m src.main --output-dir outputs --make-motorik-barcharts
```

### Ergebnisse

```text
outputs\subject01\
├─ reports\mrcp_report.html        Bericht – hier anfangen
├─ figures\  raw_eeg, electrode_montage, mrcp_9_channels, mrcp_grand_average,
│            emg_movement_locked, eeg_emg_alignment (.png)
├─ tables\   dataset_inventory, missing_pairs, channel_diagnostics, events,
│            trigger_summary, mrcp_epoch_features (.csv)
├─ logs\     pipeline.log, warnings.txt
├─ videos\   mrcp_eeg_emg_animation.gif / .mp4        mit --make-video
└─ fif\      raw_original, raw_car, raw_mrcp_filtered (.fif)   mit --save-fif

outputs\group_analysis\
├─ reports\group_mrcp_report.html  Gruppenbericht (interaktiv)
├─ tables\   subject_qc_summary, recording_qc_summary, mrcp_epoch_features,
│            mrcp_subject_channel_summary, eeg_emg_latency_features,
│            group_mrcp_timeseries, valid_motor_events_per_subject,
│            most_frequent_mrcp_channel, mrcp_region_frequency (.csv)
├─ figures\  valid/dropped_epochs_per_subject, recordings_per_subject,
│            group_mrcp_selected_channels, group_mrcp_grand_average,
│            group_mrcp_left_vs_midline_vs_right, Motorik-Balkendiagramme (.png)
└─ logs\warnings.txt
```

Die Animation wird immer als GIF geschrieben; ein MP4 entsteht zusätzlich nur,
wenn `imageio` MP4 schreiben kann.

### Wichtig zu wissen

- **Ein Einzelproband-Lauf (`--subject`) wertet nur die erste gültige Aufnahme
  voll aus.** Alle 5 Trials werden inventarisiert; gefiltert, epochiert und
  geplottet wird aber nur der erste. Die Gruppenanalyse (`--subjects` oder
  `--all-subjects`) nutzt alle Trials jedes Probanden. Für belastbare
  MRCP-Ergebnisse eines einzelnen Probanden deshalb `--subjects SUBJECT01`
  verwenden.
- **Pro Datei fehlt immer eine Epoche.** Jede Datei beginnt direkt mit dem
  ersten Durchgang; der Bewegungsbeginn liegt nach etwa 1,2 s, und das Fenster
  ab −2 s ragt vor den Dateianfang. Daher 45 statt 50 Epochen je Proband.
- Gruppenmittel werden aus den Probandenmitteln gebildet, damit Probanden mit
  mehr gültigen Epochen nicht stärker zählen.
- `--make-video` ist im Gruppenlauf abgeschaltet.

### Einstellungen

In `config/dataset.yaml`:

| Block | Inhalt |
|---|---|
| `eeg` | Abtastrate 128 Hz, Zuordnung der Spalten `2`–`33` zu den 32 Elektroden, ausgeschlossene Spalten |
| `emg` | Abtastrate 440 Hz, Hüllkurve, Erkennung des EMG-Beginns |
| `triggers` / `trigger_codes` | 768 Trial-Start, 771 Vorbereitung, 7711 Bewegungsbeginn, 7712 Bewegungsende, 1000 Trial-Ende, 32766 Sitzungsgrenze |
| `epochs` | Zeitfenster für Baseline, vor, während und nach der Bewegung |
| `mrcp` | Kanäle, Regionen links/Mitte/rechts, Bandpass 0,1–1 Hz, Ausrichtung auf `movement` (7711) oder `preparation` (771) |

`src/config.py` prüft diese Werte beim Start streng: eine andere Abtastrate,
unvollständige Trigger-Codes oder eine Spaltenzuordnung, die nicht zu den
Kanalnamen passt, brechen mit einer Fehlermeldung ab.

---

## 4. Zustandsanalyse ausführen

### Ein Proband

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --subject SUBJECT01 --analysis states
```

Schreibt für jede Aufnahme eine Playback-JSON für die Abspielansicht. Anders
als die MRCP-Analyse wertet die Zustandsanalyse auch hier alle Trials aus.
Dauer: wenige Sekunden.

### Alle Probanden mit Gruppenbericht

```powershell
python -m src.main --data-dir "<SUBJECTS>" --output-dir outputs --all-subjects --analysis states
```

Dauer: unter einer Minute. Playback-JSONs werden im Gruppenlauf nicht
geschrieben (40 × 5 Dateien), außer mit `--make-playback true`.

### Synthetischer Datensatz

```powershell
python -m src.main --config config/synthetic_emotion.yaml --output-dir outputs
```

Kein `--data-dir` nötig: die Datei `synthetic_emotion_eeg_raw.csv` liegt im
Repository. Für diesen Datensatz gibt es nur die Zustandsanalyse.

---

## 5. Ergebnisse der Zustandsanalyse

```text
outputs\
├─ subject01\
│  ├─ figures\ tables\ reports\ logs\ …      MRCP-Analyse
│  └─ states\                                 Zustandsanalyse
│     ├─ reports\states_report.html           Bericht – hier anfangen
│     ├─ tables\                              Tabellen (CSV)
│     ├─ figures\lateralization_*.png         Seitenvergleich je Band
│     ├─ playback\SUBJECT01_Trial_01.json …   für die Abspielansicht
│     └─ logs\warnings.txt                    übersprungene Aufnahmen/Abschnitte
├─ synthetic\states\…                         synthetischer Datensatz, gleicher Aufbau
└─ group_analysis\
   ├─ reports\group_mrcp_report.html          MRCP-Gruppenbericht
   └─ states\                                 Zustands-Gruppenbericht, gleicher Aufbau
```

`outputs\` ist in `.gitignore` eingetragen und wird nicht committet.

### Die Tabellen

| Datei | Inhalt |
|---|---|
| `state_segment_scores.csv` | eine Zeile je beschriftetem Abschnitt: Label, Zeit, ob das Qualitätsgate hält, bester Zustand, Rang und z-Wert des erwarteten Zustands, dazu `z_<zustand>` für jeden Zustand |
| `state_accuracy.csv` | je Abschnittstyp mit erwartetem Zustand: wie oft dieser auf Platz 1 steht (`top1_rate`), mittlerer Rang und z-Wert |
| `state_top_counts.csv` | welcher Zustand je Abschnittstyp wie oft vorne liegt; `(none)` = kein Zustand über der Erkennungsschwelle |
| `motor_lateralization.csv` | je Aufnahme, Band und Elektrode: Bandleistung Bewegung minus Ruhe in dB (negativ = Desynchronisation) |
| `motor_lateralization_subjects.csv` | dasselbe je Proband gemittelt, plus Seitenindex `C3-C4`, `FC3-FC4`, `CP3-CP4` |
| `motor_lateralization_summary.csv` | über alle Probanden: Mittelwert, Streuung, Anzahl negativer Probanden, t-Test gegen 0 |

Die beiden Lateralisierungstabellen gibt es nur für den MRCP-Datensatz.

---

## 6. Abspielansicht

1. `eeg_zustaende_playback.html` im Browser öffnen (Doppelklick genügt).
2. **Messung laden** → eine Datei aus `outputs\<proband>\states\playback\` wählen.
3. Mit ▶ abspielen oder den Schieberegler ziehen.

Was angezeigt wird:

- **Kopfkarte:** Bandleistung je Elektrode als z-Wert gegen die Ruhe; rot = höher, blau = niedriger.
- **Chips oben:** Frequenzband wechseln (Delta bis Gamma).
- **Streifen unter der Karte:** die beschrifteten Abschnitte; rot markiert Abschnitte, die das Qualitätsgate nicht bestehen.
- **Rechte Spalte:** aktueller Abschnitt, Qualitätsgate, Zustandsranking des Frames und die Elektroden mit den extremsten Werten.

Ohne geladene Datei zeigt die Seite die Referenzkarte: welche Elektroden und
Bänder zu welchem Zustand gehören.

---

## 7. Ergebnisse der Zustandsanalyse lesen

**Score:** Jede Zuordnung in `states.json` (Elektrode, Band, Richtung) wird als
z-Wert gegen die Ruheabschnitte derselben Aufnahme gemessen, mit der erwarteten
Richtung als Vorzeichen, und je Zustand gemittelt. Der stärkste Zustand bekommt
1.0, die übrigen ihren Anteil daran. Als erkannt gilt ein Zustand ab z ≥ 1 mit
Score ≥ 0.5. Das ist ein nachvollziehbarer Abgleich mit Literaturwerten, kein
trainierter Klassifikator.

**Zufallsniveau:** Bei 12 bewertbaren Zuständen liegt `top1_rate` durch Zufall
bei etwa 8 %.

**Seitenvergleich:** Bei Bewegung der rechten Hand erwartet man eine stärkere
Desynchronisation über der linken Hemisphäre, also einen negativen Index
`C3-C4`. Ist der Index über die Probanden deutlich positiv, spricht das für
vertauschte Seiten, zum Beispiel in der Spaltenzuordnung von
`config/dataset.yaml`.

**Stand mit dem MRCP-Datensatz** (40 Probanden): Während der Bewegung sinkt
die Bandleistung in Mu und Beta messbar (Mu an C3 −0,42 dB, p < 0,001), aber
beidseitig gleich (Mu `C3-C4` +0,01 dB, p = 0,94). `motorik_rechts` steht in
11 % der Bewegungsabschnitte vorne.

**Bekannte Einschränkungen:**

- Die Valenz wird über den Betrag der Asymmetrieänderung bewertet, der auch bei
  reinem Rauschen positiv ist. Sie liegt deshalb in ruhigen Abschnitten oft
  vorne.
- Mu (8–13 Hz) überlappt mit dem posterioren Alpha. Welche Seite sich bewegt,
  zeigt nur der Seitenvergleich, nicht der Score der Motorik-Zustände.
- Der synthetische Datensatz ist aus denselben Signaturen gebaut, die bewertet
  werden. Dass dort alle Zustände erkannt werden, belegt nur, dass die Pipeline
  funktioniert.

---

## 8. Konfiguration der Zustandsanalyse

Alle Einstellungen der Zustandsanalyse stehen im Block `states:` der
Datensatz-Konfiguration.

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `bandpass` | `[1.0, 45.0]` | Bandpass vor der Bandleistung (Hz) |
| `notch_hz` | `null` | Netzfilter; im MRCP-Datensatz ist kein Netzbrumm zu sehen |
| `window_s` / `step_s` | `1.0` / `0.125` | Fensterlänge und Schrittweite der Bandleistung |
| `playback_step_s` | `0.5` | Frame-Abstand in der Playback-JSON; ganzzahliges Vielfaches von `step_s` |
| `quality_gate.max_ptp_uv` | `150` | Kanal im Fenster verworfen oberhalb dieser Peak-to-Peak-Amplitude |
| `quality_gate.min_std_uv` | `0.5` | Kanal verworfen unterhalb dieser Standardabweichung (flach) |
| `quality_gate.max_bad_channel_fraction` | `0.25` | Fenster verworfen, wenn mehr Kanäle ausfallen |
| `quality_gate.min_good_frame_fraction` | `0.5` | Abschnitt nur bewertet, wenn so viele Fenster gut sind |
| `segments` | s. Datei | Abschnitte zwischen Trigger-Codes, s. unten |
| `lateralization` | s. Datei | Bänder, Elektroden und Paare des Seitenvergleichs |

### Abschnitte im MRCP-Datensatz

Ein Abschnitt beginnt bei einem `start`-Code und endet beim nächsten
`stop`-Code. Taucht vorher erneut ein `start`-Code auf, wird er verworfen.

| Label | von → bis | Rolle |
|---|---|---|
| `rest` | 1000 (Trial-Ende) → 771 (nächste Vorbereitung) | Ruhe-Baseline |
| `preparation` | 771 → 7711 | Vorbereitung |
| `movement` | 7711 → 7712 | Faustschluss, erwarteter Zustand `motorik_rechts` |
| `post_movement` | 7712 → 1000 | nach der Bewegung |

Beim synthetischen Datensatz ist jeder zusammenhängende Block von `state_id`
ein Abschnitt; `neutral_baseline` ist die Ruhe. Die erwarteten Zustände stehen
unter `expected_states` in `config/synthetic_emotion.yaml`.

---

## 9. Zustände ändern oder ergänzen

1. Zustand in `config/states.json` eintragen: `id`, `label`, `summary` und
   `mappings` mit je `el` (Elektrode), `band` (Schlüssel aus `bands`), `trend`
   (`up`, `down`, `asym`, `mix`) und `note`.
2. Denselben Zustand im Block `STATES` von `eeg_zustaende_playback.html`
   ergänzen.
3. `python -m pytest` ausführen. `tests/test_states_sync.py` meldet jede
   Abweichung zwischen beiden Dateien.

Für die Bänder gilt dasselbe: `bands` in `states.json` und `BANDS` in der HTML
müssen übereinstimmen.

---

## 10. Einen weiteren Datensatz anbinden

1. In `src/adapters.py` eine Klasse mit `subjects()` und `recordings(subject)`
   anlegen. `recordings` liefert je Aufnahme `(key, Recording, None)` oder im
   Fehlerfall `(key, None, meldung)`. Ein `Recording` enthält das EEG als MNE
   Raw in Volt (am besten über `make_raw`) und eine Abschnittstabelle mit
   `start_s`, `stop_s`, `label`, `expected_state`, `baseline`, `trial`.
2. Die Klasse in `ADAPTERS` eintragen.
3. In `src/config.py` eine Prüffunktion schreiben und in `VALIDATORS`
   eintragen.
4. Eine Konfiguration unter `config/` mit `dataset.adapter`, `analyses: [states]`,
   `eeg` und `states` anlegen.

Alles nach dem Adapter – Bandleistung, Scores, Bericht, Playback – funktioniert
dann ohne weitere Änderungen.

---

## 11. Tests

```powershell
python -m pytest
```

27 Tests: Konfiguration, Bandleistung und Qualitätsgate, Abschnitte aus
Triggern, beide Adapter, Scorer, ein vollständiger Lauf auf dem synthetischen
Datensatz und der Abgleich `states.json` ↔ HTML.

---

## 12. Häufige Meldungen

| Meldung | Ursache |
|---|---|
| `Skipping trigger-only EEG: SUBJECT13_Trial_02` | Die EEG-Datei ist im Datensatz eine Kopie der EMG-Datei. Wird übersprungen. |
| `SUBJECT29_Trial_02: only 0 of 38 resting frames pass the quality gate` | Aufnahme durchgehend verrauscht (ca. 60 µV Streuung statt 6–10). Wird übersprungen. |
| `Unmatched files for SUBJECT27` | Die Datei heißt `SUBJECT27_Trial_02_EEG-mpfV6c.csv` und passt nicht zum Namensschema. |
| `Trigger 7711: expected about 10, found 9` | Hinweis aus der MRCP-Pipeline zur Trigger-Anzahl; die Auswertung läuft weiter. |
| `n of m sections fail the quality gate` | Einzelne Abschnitte mit Artefakten; sie werden nicht bewertet. |
| `--data-dir is required for the mendeley_mrcp dataset` | Beim MRCP-Datensatz fehlt der Pfad zum Ordner `SUBJECTS`. |
