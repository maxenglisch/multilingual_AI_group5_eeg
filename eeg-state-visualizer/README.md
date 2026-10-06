# EEG State Visualizer

EEG-Auswertung und Visualisierung für das **EMOTIV FLEX 2** (32 Kanäle,
10-20-System). Liest EmotivPRO-Exporte (Handgesten-Set und synthetischer Export)
und erzeugt daraus eine abspielbare Topografie im Browser.

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
| CSV V2 | eine Datei, entweder mit allen Streams (wie `synthetic_emotivexport`) oder nur mit Roh-EEG, CQ, EQ und Markern (wie das Handgesten-Set) |
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
gemittelt über den Zustand. Für die Balken werden die Zustände untereinander
normiert. Schlägt keiner über die Schwelle aus, bleiben alle klein. Der Score zeigt nur wie gut das Muster passt.

In der Oberfläche zeigen die Balken den Score des aktuellen Frames (ein kurzes
Fenster, deshalb schwanken sie). Das Häkchen ist das Ergebnis für das ganze
Segment, ein einzelner Frame ist für ein eigenes Urteil zu verrauscht.
