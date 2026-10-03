# Projektübersicht

Dieses Projekt bietet eine Python-basierte Pipeline zur Verarbeitung und Visualisierung von EEG-Aufzeichnungen, wobei der Schwerpunkt insbesondere auf Movement-Related Cortical Potentials (MRCPs) liegt.

Die Pipeline dient dazu, die Verarbeitung von EEG-Daten zu automatisieren und visuelle Berichte für einzelne Probanden sowie für Analysen auf Gruppenebene zu erstellen.

## Funktionen

Diese Pipeline dient der automatisierten Verarbeitung, Analyse und Visualisierung von EEG-Daten mit besonderem Schwerpunkt auf bewegungsbezogenen kortikalen Potenzialen (Movement-Related Cortical Potentials, MRCPs).

Die wichtigsten Funktionen sind:

- `Automatisierte EEG-Datenverarbeitung:` Verarbeitung der EEG-Aufzeichnungen auf Grundlage einer einheitlichen Datenkonfiguration.
- `Visualisierung von 32 EEG-Kanälen:` Darstellung der EEG-Signale zur Untersuchung der elektrischen Aktivität an verschiedenen Elektrodenpositionen.
- `Individuelle HTML-Berichte:` Automatische Erstellung von Analyseberichten für einzelne Versuchspersonen (Subjects).
- `Animierte EEG-Visualisierung:` Erstellung von MP4- oder GIF-Animationen zur zeitlichen Darstellung der EEG-Aktivität.
- `Gruppenanalyse:` Zusammenführung und Auswertung der Ergebnisse mehrerer Versuchspersonen sowie Erstellung eines gemeinsamen Gruppenberichts.
- `Zentrale Ergebnisübersicht:` Bereitstellung einer HTML-Startseite, über die individuelle Berichte und Gruppenanalysen aufgerufen werden können.

## Projektstruktur

Das Projekt ist modular aufgebaut. Der Quellcode, die Konfigurationsdateien, die Tests und die generierten Ergebnisse sind in separaten Verzeichnissen organisiert.

Die folgende Übersicht zeigt die wichtigsten Bestandteile des Projekts:

```text
mrcp-eeg-pipeline/
│
├── main.py
├── config/
│   └── dataset.yaml
│
├── src/
│   ├── data_loader.py
│   ├── eeg_processing.py
│   ├── emg_processing.py
│   ├── mrcp_analysis.py
│   ├── group_analysis.py
│   ├── video_generator.py
│   ├── report.py
│   └── report_server.py
│
├── outputs/
│   ├── reports/
│   │   └── index.html
│   ├── SUBJECT01/
│   │   ├── figures/
│   │   ├── tables/
│   │   ├── videos/
│   │   └── reports/
│   ├── group_analysis/
│   │   ├── figures/
│   │   ├── tables/
│   │   └── reports/
│   └── videos/
├── tests/
└── README.md
```

### Beschreibung der wichtigsten Verzeichnisse
- `config/`: Enthält die zentrale Konfigurationsdatei für das EEG-Dataset.
- `src/`: Enthält den Python-Quellcode für die Datenverarbeitung, MRCP-Analyse, Visualisierung und Berichtserstellung.
- `outputs/`: Speichert die generierten Analyseergebnisse, Abbildungen, Animationen und HTML-Berichte.
- `tests/`: Enthält automatisierte Tests zur Überprüfung verschiedener Funktionen der Pipeline.

Die zentrale HTML-Übersicht befindet sich unter outputs/reports/index.html. Von dort aus können die individuellen Berichte und die Gruppenanalyse aufgerufen werden.

## Installation

Für die Ausführung der Pipeline werden Python und die benötigten Python-Bibliotheken vorausgesetzt.

Wir empfehlen die Verwendung von Miniconda oder Anaconda, um eine separate Python-Umgebung einzurichten und mögliche Konflikte zwischen verschiedenen Bibliotheken zu vermeiden.

### 1. Voraussetzungen

- Python (kompatible Version gemäß Projektanforderungen)
- Miniconda oder Anaconda
- Git (optional, zum Klonen des Repositorys)

### 2. Conda-Umgebung erstellen

Zunächst wird eine neue Conda-Umgebung erstellt und aktiviert:

```powershell
conda create -n mne python=3.11
conda activate mne
```

Die Python-Version 3.11 dient hier als Beispiel und muss mit den tatsächlichen Projektanforderungen abgeglichen werden.

### 3. Abhängigkeiten installieren

Anschließend wird im Hauptverzeichnis des Projekts folgender Befehl ausgeführt:

```powershell
python -m pip install -r requirements.txt
```

Dadurch werden die in requirements.txt aufgeführten Python-Bibliotheken installiert.

### 4. Installation überprüfen

Mit dem folgenden Befehl kann überprüft werden, ob MNE-Python erfolgreich installiert wurde:

```powershell
python -c "import mne; print(mne.__version__)"
```

Anschließend kann die Pipeline gemäß den Anweisungen im Abschnitt „Verwendung“ ausgeführt werden.

## Dataset-Konfiguration

Die zentrale Konfiguration des verwendeten EEG-/EMG-Datensatzes befindet sich in:

`config/dataset.yaml`

Diese Datei dient als zentrale Quelle für die datensatzspezifischen Einstellungen der Pipeline. Dazu gehören unter anderem:

- EEG-Abtastrate: 128 Hz
- EMG-Abtastrate: 440 Hz
- EEG-Eingabeeinheit: µV
- interne Verarbeitung mit MNE in Volt
- Zuordnung der 32 EEG-Kanäle
- Definition der Trigger-Codes
- Common Average Reference (CAR)
- MRCP-Filterung im Bereich von 0,1–1 Hz

Die Pipeline verwendet diese Konfiguration, damit Kanalzuordnung, Trigger-Erkennung und Signalverarbeitung einheitlich durchgeführt werden.

Änderungen an datensatzspezifischen Parametern sollten daher zentral in `config/dataset.yaml` vorgenommen werden.

## Verwendung 

Die Pipeline kann über PowerShell ausgeführt werden. Vor der Verwendung müssen die erforderlichen Python-Bibliotheken installiert sein.

### 1. Projektverzeichnis öffnen

Zunächst wird die Conda-Umgebung aktiviert und das Projektverzeichnis geöffnet.

```powershell
conda activate mne
cd PFAD_ZUM_PROJEKT
```

### 2. MRCP-Analyse durchführen

Die Pipeline bietet verschiedene Möglichkeiten zur Verarbeitung der EEG-Daten.

**Einzelne Versuchsperson analysieren:**

```powershell
python -m src.main --data-dir "PFAD_ZU_DEN_DATEN" --subject SUBJECT01
```

**Ausgewählte Versuchspersonen analysieren:**

```powershell
python -m src.main --data-dir "PFAD_ZU_DEN_DATEN" --output-dir outputs --subjects SUBJECT01 SUBJECT02 SUBJECT03
```

**Alle Versuchspersonen analysieren:**

```powershell
python -m src.main --data-dir "PFAD_ZU_DEN_DATEN" --all-subjects
```

**Ausgabeverzeichnis festlegen:**

```powershell
python -m src.main --data-dir "PFAD_ZU_DEN_DATEN" --all-subjects --output-dir outputs
```

**Datensatz ohne vollständige Analyse überprüfen:**

```powershell
python -m src.main --data-dir "PFAD_ZU_DEN_DATEN" --output-dir outputs --dry-run
```

Mit `--dry-run` können die verfügbaren Aufzeichnungen überprüft und mögliche Probleme diagnostiziert werden, ohne die vollständige Signalverarbeitung durchzuführen.

Die Platzhalter müssen durch die tatsächlichen Verzeichnispfade ersetzt werden.

### 3. Videos generieren

Die Pipeline verfügt über eine integrierte Funktion zur Videoerstellung.

**Video während der Analyse einer Versuchsperson erstellen:**

```powershell
python -m src.main --data-dir "PFAD_ZU_DEN_DATEN" --output-dir outputs --subject SUBJECT01 --make-video true
```
**Videos unabhängig von der Hauptanalyse für alle Versuchspersonen erstellen:**

```powershell
python -m src.video_generator --data-dir "PFAD_ZU_DEN_DATEN" --output-dir outputs --all
```
Bereits vorhandene gültige Videos werden dabei normalerweise übersprungen. Mit `--force` können sie bei Bedarf neu erstellt werden.

Bei der integrierten Videoerstellung über `src.main` können zusätzlich `--video-duration` und `--video-fps` verwendet werden.

### 4. HTML-Berichte aktualisieren

Bereits vorhandene Analyseergebnisse können verwendet werden, um die HTML-Berichte neu zu erstellen.

```powershell
python -m src.main --output-dir outputs --rebuild-reports --force
```

Mit `--force` können bereits vorhandene HTML-Berichte überschrieben und aktualisiert werden.

### 5. HTML-Berichte lokal anzeigen

Für die Darstellung der generierten Berichte kann ein lokaler Webserver gestartet werden.

```powershell
python -m src.report_server --output-dir outputs --port 8000
```

Anschließend kann die vom Server angezeigte lokale Adresse im Webbrowser geöffnet werden.

Die zentrale HTML-Übersicht befindet sich unter:

`outputs/reports/index.html`

Von dort aus können die Berichte einzelner Versuchspersonen sowie die Gruppenanalyse aufgerufen werden.

## Outputs

Die Pipeline speichert die generierten Ergebnisse im Verzeichnis `outputs/`. Dabei werden individuelle Analysen, Gruppenanalysen und Videos getrennt organisiert.

### 1. Individuelle Ergebnisse

Für jede analysierte Versuchsperson wird ein eigenes Verzeichnis angelegt, beispielsweise `outputs/SUBJECT01/`.

Dieses enthält folgende Unterverzeichnisse:

- `figures/`: EEG- und EMG-Darstellungen, Elektrodenpositionen und MRCP-Diagramme
- `tables/`: CSV-Dateien mit Analyseergebnissen, Ereignissen und diagnostischen Informationen
- `reports/`: Individueller HTML-Bericht (`mrcp_report.html`)
- `logs/`: Protokolle und Warnmeldungen
- `fif/`: Optional gespeicherte EEG-Daten im MNE-FIF-Format
- `videos/`: Kompatibilitätsverzeichnis für ältere Videos

Die individuellen HTML-Berichte fassen die wichtigsten Analyseergebnisse und Visualisierungen einer Versuchsperson zusammen.

### 2. Gruppenanalyse

Bei der Verarbeitung mehrerer Versuchspersonen werden zusätzliche Ergebnisse im Verzeichnis `outputs/group_analysis/` gespeichert.

Dazu gehören:

- Grafische Darstellungen der gruppenbezogenen MRCP-Ergebnisse
- Tabellen mit Qualitätskontrollen und extrahierten Merkmalen
- Zusammenfassungen der Bewegungseignisse
- Ein gemeinsamer HTML-Bericht

Der Gruppenbericht befindet sich unter:

`outputs/group_analysis/reports/group_mrcp_report.html`

### 3. Videos

Die aktuell generierten Videos werden zentral im Verzeichnis `outputs/videos/` gespeichert.

Die Animationen kombinieren die MRCP-Signale, bewegungsbezogene EMG-Signale und die räumliche Darstellung der EEG-Aktivität auf der Kopfoberfläche.

Abhängig von den verfügbaren Programmen können MP4- oder GIF-Dateien erstellt werden.

### 4. Zentrale HTML-Übersicht

Die zentrale Startseite befindet sich unter:

`outputs/reports/index.html`

Sie ermöglicht den Zugriff auf die individuellen HTML-Berichte sowie die Ergebnisse der Gruppenanalyse.

Für die vollständige Darstellung der Videos wird empfohlen, den lokalen Webserver zu verwenden:

```powershell
python -m src.report_server --output-dir outputs --port 8000
```

Anschließend kann die Startseite unter folgender Adresse geöffnet werden:

http://127.0.0.1:8000/reports/index.html

## Tests

Das Projekt enthält automatisierte Tests zur Überprüfung wichtiger Funktionen der Pipeline.

Alle Tests befinden sich im Verzeichnis:

`tests/`

Die vollständige Testsuite kann im Hauptverzeichnis des Projekts mit folgendem Befehl ausgeführt werden:

```powershell
python -m pytest
```
