# EEG State Visualizer

EEG-Auswertung und Visualisierung für das **EMOTIV FLEX 2** (32 Kanäle,
10-20-System). Liest EmotivPRO-Exporte (synthetischer Export, Handgesten-Set nach
Umwandlung) und erzeugt daraus eine abspielbare Topografie im Browser.

## Der verbindliche Standard

Maßgeblich für alle Ein- und Ausgaben ist der Export in

```
../synthetic_emotivexport/
```

(der synthetische Export, auf den sich die Gruppe geeinigt hat). Aufnahmen, die
diesem Aufbau nicht entsprechen (keine Metadatenzeile, fehlende Pflichtspalten,
Text in numerischen Kanälen), werden abgelehnt. Der Ordner selbst bleibt
unverändert, erzeugte Dateien landen in `exports/`.

Kurzfassung des Formats:

| | |
|---|---|
| Zeile 1 | Metadaten als `key:value`-Paare, u. a. `title`, `sampling rate`, `samples` |
| Zeile 2 | Spaltennamen |
| CSV V2 | eine Datei, entweder mit allen Streams (wie `synthetic_emotivexport`) oder nur mit Roh-EEG, CQ, EQ und Markern |
| EEG | `EEG.<Sensor>` in Mikrovolt |
| Motion | `MOT.AccX/Y/Z`, dazu `MOT.Q0..Q3` (neuere Headsets) oder `MOT.GYROX..Z` |
| Bandleistung | `POW.<Sensor>.<Theta\|Alpha\|BetaL\|BetaH\|Gamma>` in dB |
| Metrics | `PM.<Metric>.<IsActive\|Scaled\|Raw\|Min\|Max>` |
| Qualität | `CQ.<Sensor>` 0-4, `CQ.Overall` 0-100, `EQ.OVERALL` 0-100, `EQ.SampleRateQuality` 0-1 oder -1 |
| Marker | `MarkerIndex`, `MarkerType`, `MarkerValueInt`, Sidecar `markers.json` |

## Loslegen

```bash
pip install -r requirements.txt
```

JSON für die Oberfläche erzeugen (ohne Argument: der Standard-Export):

```bash
python flex2_export_json.py
```
(synthetic_emotivexport aus dem repo wird verwendet!!!)

Dann `eeg_state_playback.html` im Browser öffnen und unter **Load recording**
die Datei aus `exports/` wählen.

Das Werkzeug nimmt auch eine eigene Aufnahme:

```bash
python flex2_export_json.py aufnahme.csv
```

## Handgesten-Set

Datensatz: [Mendeley – y23s2xg6x4](https://data.mendeley.com/datasets/y23s2xg6x4/1). Je Proband
fünf Durchgänge. Ein Auszug liegt auch im Repo unter
`../pipeline_prototype/data/raw/SUBJECT01/`.

Die CSVs besitzen keine Metadatenzeile, Spalten `0`-`37`
statt `EEG.<Sensor>`, `Triggers` statt Marker.

### Einzelne Aufnahme

```bash
python handgesture_to_emotivpro.py SUBJECT01_Trial_01_EEG.csv
python flex2_export_json.py SUBJECT01_Trial_01_EEG_emotivpro.csv
```

Konvertiert die Spalten `2`-`33` nach dem FLEX-2-Layout (wie in
`mrcp-eeg-analysis/config/dataset.yaml`), übersetzt `Triggers` in Marker und
schreibt `*.markers.json` mit den Trigger-Namen (`771` = `preparation`,
`7711` = `movement`, `7712` = `movement_end`, `1000` = `rest`, ...). Der Output liegt im selben Verzeichnis wie der input.

In einer einzelnen Aufnahme ist die Motorik nur schwach zu sehen, deshalb besser mitteln.

### Gemittelte Bewegung

```bash
python average_movement.py "<Pfad>/SUBJECTS"
python flex2_export_json.py SUBJECTS_average_emotivpro.csv
```

`average_movement.py` mittelt über alle Versuche. Als Eingabe gehen einzelne CSVs oder Ordner, Unterordner
werden mit durchsucht. Ein einzelner Proband geht mit `.../SUBJECTS/SUBJECT01`.

### Hinweise

- CQ und EQ fehlen im Datensatz, die Qualitätsprüfung läuft ohne diese Kriterien.

## Bänder der Oberfläche

Die Bänder der Oberfläche werden auf die fünf Bänder abgebildet, die EmotivPRO
liefert:

| Oberfläche | EmotivPRO | Anmerkung |
|---|---|---|
| Theta | `Theta` (4-8 Hz) | |
| Alpha | `Alpha` (8-12 Hz) | |
| Mu | `Alpha` | EmotivPRO hat kein Mu-Band |
| SMR, Low Beta | `BetaL` (12-16 Hz) | |
| High Beta | `BetaH` (16-25 Hz) | |
| Gamma | `Gamma` (25-45 Hz) | mit diesem Setup EMG-anfällig |
| Delta | - | wird nicht exportiert, bleibt unbewertet |

Die beiden Ersatzabbildungen sind kein Formalismus: Mu teilt sich das Alpha-Band
mit dem posterioren Ruhe-Alpha, deshalb schlagen die drei Motorik-Zustände auch
dann leicht an, wenn der Alpha nur global einbricht statt sensomotorisch.

## Was der Score ist und was nicht

Kein trainierter Klassifikator: Für jede Zuordnung wird gemessen, wie weit die
Bandleistung in der erwarteten Richtung vom Ruhewert abweicht (z-Wert),
gemittelt über den Zustand. Der Ruhewert kommt aus allen Segmenten mit dem Label
`neutral`, `baseline` oder `rest`. Für die Balken werden die Zustände untereinander
normiert. Schlägt keiner über die Schwelle aus, bleiben alle klein. Der Score zeigt nur wie gut das Muster passt.

In der Oberfläche zeigen die Balken den Score des aktuellen Frames (ein kurzes
Fenster, deshalb schwanken sie). Das Häkchen ist das Ergebnis für das ganze
Segment, ein einzelner Frame ist für ein eigenes Urteil zu verrauscht.
