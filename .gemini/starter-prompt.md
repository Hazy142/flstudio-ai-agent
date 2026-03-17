# DAWMind – Starter Prompt für Antigravity Agent

> Kopiere einen der folgenden Prompts in den Antigravity Agent-Chat.
> Nutze **Planning Mode** für Feature-Arbeit, **Fast Mode** für kleine Fixes.

---

## 🎤 Option A: Whisper Voice Pipeline (nächstes großes Feature)

```
Implementiere die Whisper Voice Command Pipeline für DAWMind.

Lies zuerst die .gemini/rules und ARCHITECTURE.md um das Projekt zu verstehen.

Anforderungen:
1. Erstelle `dawmind/voice/` Package:
   - `recorder.py` – Mikrofon-Aufnahme via sounddevice/pyaudio, Voice Activity Detection (VAD) mit webrtcvad oder silero-vad, Aufnahme startet bei Sprache, stoppt nach 1.5s Stille
   - `transcriber.py` – Whisper Integration (openai-whisper oder faster-whisper für Performance), konfigurierbar über config/dawmind.toml [voice] Sektion, Modell "base" als Default
   - `pipeline.py` – Orchestriert: Aufnahme → Transkription → Text an Orchestrator.process_input()

2. Erweitere `dawmind/cli.py`:
   - Neuer `dawmind voice` Subcommand der die Voice Pipeline startet
   - Push-to-talk (Leertaste) UND Auto-Detect Modus
   - Zeige Transkription in Rich-Console an bevor sie an den Orchestrator geht

3. Erweitere `config/dawmind.toml` [voice] Sektion:
   - whisper_model = "base"  (tiny/base/small/medium)
   - vad_threshold = 0.5
   - silence_duration_ms = 1500
   - mode = "auto"  (auto/push_to_talk)
   - language = "de"  (für deutsche Befehle)

4. Dependencies in pyproject.toml hinzufügen:
   - openai-whisper oder faster-whisper
   - sounddevice
   - webrtcvad oder silero-vad

5. Tests in `tests/test_voice.py`:
   - Mock Mikrofon-Input
   - Test VAD Erkennung
   - Test Transkription mit Mock-Audio
   - Test Pipeline Integration

Beachte: Das läuft auf Windows. Teste keine Audio-Hardware direkt, nur die Logik.
```

---

## 🧪 Option B: FL Studio Live-Test auf Windows

```
Hilf mir DAWMind zum ersten Mal mit FL Studio zu verbinden und zu testen.

Lies zuerst die .gemini/rules und docs/SETUP.md.

Schritte:
1. Prüfe ob Python 3.12+ installiert ist (python --version)
2. Installiere das Projekt: pip install -e ".[dev]"
3. Prüfe ob FL Studio installiert ist und finde den MIDI Scripts Ordner:
   - Typisch: %USERPROFILE%/Documents/Image-Line/FL Studio/Settings/Hardware/
4. Kopiere fl_script/device_DAWMind.py und fl_script/ipc_handler.py dorthin:
   - Erstelle Unterordner "DAWMind" falls nötig
5. Erstelle .env Datei mit ANTHROPIC_API_KEY (frag mich nach dem Key)
6. Starte den Bridge Server: dawmind serve
7. Starte FL Studio, gehe zu MIDI Settings, aktiviere "DAWMind" als Controller
8. Teste grundlegende Befehle:
   - Schick "play" über WebSocket und prüfe ob FL Studio startet
   - Schick "get_daw_state" und prüfe ob der State zurückkommt
9. Dokumentiere was funktioniert und was nicht in einer TESTING.md
```

---

## 🚀 Option C: OmniParser auf GCP deployen

```
Deploye OmniParser V2 auf Google Cloud Run mit L4 GPU.

Lies zuerst omniparser/README.md und omniparser/deploy_gcp.sh.

Voraussetzungen:
- Google Cloud CLI (gcloud) installiert und eingeloggt
- Projekt mit Billing aktiviert (~300€ Credits verfügbar)
- Region: europe-west1 (oder nächste mit L4 GPU Verfügbarkeit)

Schritte:
1. Prüfe gcloud auth: gcloud auth list
2. Erstelle/wähle GCP Projekt: gcloud config set project <PROJECT_ID>
3. Aktiviere benötigte APIs: Cloud Run, Artifact Registry, Cloud Build
4. Baue und pushe das Docker Image via Cloud Build
5. Deploye auf Cloud Run mit L4 GPU (1 GPU, min 0 / max 1 Instanzen für Kosteneffizienz)
6. Teste den Endpoint: curl <ENDPOINT>/health und curl -X POST <ENDPOINT>/parse mit Test-Screenshot
7. Aktualisiere config/dawmind.toml vision.omniparser_endpoint mit der Cloud Run URL
8. Committe die Config-Änderung

Wichtig: Setze min-instances auf 0 damit keine Kosten anfallen wenn der Service idle ist.
Die L4 GPU kostet ~$0.70/h – bei min=0 zahlt man nur bei Nutzung.
```

---

## 🛠️ Option D: Neue FL Studio Tools hinzufügen

```
Erweitere DAWMind um Pattern/Playlist Editing Tools.

Lies zuerst die .gemini/rules um die Tool-Architektur zu verstehen.

Neue Tools (in dawmind/tools/pattern_tools.py):
1. pattern_get_length – Aktuelle Pattern-Länge in Beats
2. pattern_set_length – Pattern-Länge setzen
3. pattern_get_note_count – Anzahl Noten im Pattern
4. pattern_add_note – Note hinzufügen (channel, position, length, velocity)
5. pattern_remove_note – Note entfernen
6. pattern_select – Pattern auswählen (Index)
7. pattern_count – Anzahl Patterns im Projekt

Für jedes Tool:
1. Tool-Definition in pattern_tools.py (name, description, input_schema)
2. Command-Konstruktor in dawmind/api_layer/commands.py
3. Handler in fl_script/device_DAWMind.py (FL Studio API Calls)
4. Routing in dawmind/tools/__init__.py (PATTERN_TOOLS importieren, in ALL_TOOLS, in execute_tool())
5. Tests in tests/test_pattern_tools.py

Referenz für FL Studio Python API:
- patterns.patternCount(), patterns.patternLength(index)
- patterns.getPatternName(index), patterns.setPatternName(index, name)
- channels.getGridBit(chan, pos), channels.setGridBit(chan, pos, value)
```

---

## Tipps für den Antigravity-Agent

- **Planning Mode** für Options A, C, D verwenden – das sind komplexe Multi-File Changes
- **Fast Mode** für schnelle Fixes und kleine Anpassungen
- Nach jeder Änderung: `python -m pytest tests/ -v` laufen lassen
- Bei Problemen: `ARCHITECTURE.md` und `.gemini/rules` als Referenz nutzen
