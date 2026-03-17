# DAWMind

[![CI](https://github.com/aelsen1808/flstudio-ai-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/aelsen1808/flstudio-ai-agent/actions/workflows/ci.yml)

**AI Agent for FL Studio** — Control your DAW with natural language using a hybrid approach: MIDI Script API for fast, reliable DAW operations + Computer Vision (OmniParser + Gemini) for universal plugin GUI automation.

```
  ____    ___  _      ____  __ _           _
 |  _ \  / _ \| |    / /  \/  (_)_ __   __| |
 | | | |/ /_\ \ | /\ / /| |\/| | | '_ \ / _` |
 | |_| / /_  _\ |/  V / | |  | | | | | | (_| |
 |____/\/ /_\  \_/\_/  |_|  |_|_|_| |_|\__,_|
```

> "Set the kick volume to -3dB" · "Open Serum and turn the cutoff to 50%" · "Make the snare punchier"

---

## What is DAWMind?

DAWMind is an AI agent that controls FL Studio through two complementary execution layers:

1. **API Layer** — Direct, fast, reliable control via FL Studio's built-in Python MIDI Scripting API. Handles transport, mixer, channels, plugin parameters, and more through Named Pipe IPC.

2. **Vision Layer** — Screen-based GUI automation using AI vision models + [OmniParser V2](https://github.com/microsoft/OmniParser). Controls any plugin GUI by "seeing" the screen and simulating mouse/keyboard input — just like [Claude Computer Use](https://docs.anthropic.com/en/docs/computer-use), but purpose-built for DAWs.

This hybrid approach gives you the **speed of API calls** for structural operations and the **universality of screen-based control** for any third-party plugin GUI.

### How it differs from existing projects

| Project | Approach | DAWMind Advantage |
|---------|----------|-------------------|
| [veenastudio/flstudio-mcp](https://github.com/veenastudio/flstudio-mcp) | MIDI messages, 7-bit limit | Full JSON via Named Pipes, bidirectional state |
| [calvinw/fl-studio-mcp](https://github.com/calvinw/fl-studio-mcp) | File queue + keystrokes, piano roll only | Real-time IPC, full DAW control |
| Claude Computer Use | Generic desktop, not DAW-aware | DAW-specific API + targeted vision |

---

## Architecture

```
FL Studio ←→ MIDI Script (Named Pipe/File IPC) ←→ Bridge Server (WebSocket :9500)
                                                        ↕
                                                   Orchestrator (Claude tool-use loop)
                                                        ↕
                                            ┌───────────┴───────────┐
                                            ↓                       ↓
                                       DAW Commands            Vision Pipeline
                                  (transport, mixer,      (Screenshot → OmniParser
                                   channel, plugin)        → Gemini → PyAutoGUI)
```

The **Orchestrator** receives natural language input, uses Claude's tool-use API to decide which operations to perform, and dispatches them to the appropriate layer. API commands flow through the WebSocket bridge to FL Studio's MIDI script via Named Pipe IPC. Vision commands capture the screen, detect UI elements with OmniParser, reason about actions with Gemini, and execute them with PyAutoGUI.

---

## Multi-Model Strategy

DAWMind uses specialized AI models for each part of the pipeline:

| Role | Model | Why |
|------|-------|-----|
| Planning & Orchestration | Claude Sonnet 4 | Best agentic reasoning and tool-use via Anthropic API |
| Vision Analysis | Gemini 2.5 Flash | Fast, cost-effective vision model via GCP credits |
| UI Element Detection | OmniParser V2 | Purpose-built for GUI element parsing, deployed on GCP Cloud Run with L4 GPU |
| Voice Commands | Whisper | Best open-source speech-to-text (planned) |
| Local/Offline Fallback | Ollama (Llama 3) | Free, no API cost for simple lookups (planned) |

---

## Features

### Implemented

- Full transport control (play, stop, record, tempo)
- Mixer operations (volume, pan, mute, solo per track)
- Channel rack management (select, rename, volume, pan)
- Plugin parameter read/write (any plugin loaded in the channel rack)
- Complete DAW state snapshots via IPC
- Claude tool-use orchestrator with agentic planning loop
- Gemini vision client for screenshot analysis
- OmniParser V2 integration for UI element detection
- Vision pipeline: capture → parse → reason → execute → verify
- WebSocket bridge server with REST health/state endpoints
- Rich CLI with `start`, `status`, `chat` commands
- Named Pipe IPC (Windows) with file-based fallback (cross-platform)
- Multi-model router with task-based selection

### Planned

- Voice input via Whisper
- Web dashboard for monitoring
- Plugin preset management
- Pattern/playlist editing
- Automation clip control
- Local/offline mode via Ollama

---

## Quick Start

> For full setup instructions including GCP/OmniParser deployment, see [docs/SETUP.md](docs/SETUP.md).

### Prerequisites
- **FL Studio** 20.8.4+ (Windows or macOS)
- **Python** 3.12+
- **uv** ([install](https://docs.astral.sh/uv/getting-started/installation/))
- API keys: At minimum `ANTHROPIC_API_KEY` or `GOOGLE_API_KEY`

### Installation

```bash
git clone https://github.com/aelsen1808/flstudio-ai-agent.git
cd flstudio-ai-agent
uv sync
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your API keys
```

### Install FL Studio Script

Copy the FL Studio controller script to your FL Studio settings:

**Windows:**
```bash
cp fl_script/* "%USERPROFILE%/Documents/Image-Line/FL Studio/Settings/Hardware/DAWMind/"
```

**macOS:**
```bash
cp fl_script/* ~/Documents/Image-Line/FL\ Studio/Settings/Hardware/DAWMind/
```

### Connect in FL Studio

1. Open FL Studio
2. Go to **Options → MIDI Settings**
3. In **Controller type**, select **DAWMind (user)**
4. Assign it to an input/output port

### Run DAWMind

```bash
# Terminal 1: Start the bridge server
uv run dawmind start

# Terminal 2: Chat with your DAW
uv run dawmind chat
```

### Example Commands

```
dawmind> play
Done: Start playback (1/1 steps completed)

dawmind> set tempo to 140
Done: Set tempo to 140 BPM (1/1 steps completed)

dawmind> mute track 3
Done: Toggle mute (1/1 steps completed)

dawmind> status
{'connected': True, 'daw_state_available': True, 'transport_playing': True, 'tempo': 140.0}
```

---

## Project Structure

```
flstudio-ai-agent/
├── dawmind/                     # Main Python package
│   ├── orchestrator.py          # Agent loop: plan → dispatch → verify
│   ├── cli.py                   # Rich CLI (start, status, chat)
│   ├── config.py                # TOML + env configuration
│   ├── api_layer/               # Layer 1: FL Studio API
│   │   ├── bridge_server.py     # FastAPI WebSocket ↔ Named Pipe
│   │   ├── commands.py          # Command factory functions
│   │   ├── protocol.py          # JSON wire protocol
│   │   └── state.py             # Pydantic DAW state models
│   ├── llm/                     # LLM integrations
│   │   ├── router.py            # Task-based model selection
│   │   ├── claude.py            # Anthropic Claude (planning)
│   │   ├── gemini_client.py     # Google Gemini (vision)
│   │   └── local.py             # Ollama (local inference)
│   ├── vision_layer/            # Layer 2: Screen-based control
│   │   ├── capture.py           # mss screenshot capture + caching
│   │   ├── parser.py            # OmniParser V2 integration
│   │   ├── reasoning.py         # Vision LLM action planning
│   │   ├── executor.py          # PyAutoGUI mouse/keyboard
│   │   └── verifier.py          # Before/after verification
│   └── tools/                   # Claude tool-use definitions
│       ├── transport_tools.py
│       ├── mixer_tools.py
│       ├── channel_tools.py
│       ├── plugin_tools.py
│       └── vision_tools.py
├── fl_script/                   # Runs inside FL Studio
│   ├── device_DAWMind.py        # MIDI controller script
│   └── ipc_handler.py           # Named Pipe / file IPC
├── config/dawmind.toml          # Configuration
├── tests/                       # pytest test suite
│   ├── test_bridge.py           # Bridge server unit tests
│   ├── test_commands.py         # Command creation tests
│   ├── test_state.py            # State model tests
│   └── integration/             # End-to-end integration tests
│       ├── mock_fl_studio.py    # Mock FL Studio IPC environment
│       ├── conftest.py          # Shared async fixtures
│       └── test_e2e.py          # Full pipeline tests
├── omniparser/                  # OmniParser V2 GCP deployment
├── docs/SETUP.md                # Full setup guide
└── ARCHITECTURE.md              # Detailed technical design
```

---

## API & Endpoints

When running, the bridge server exposes:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health + FL Studio connection status |
| `/api/state` | GET | Latest DAW state snapshot (JSON) |
| `/ws` | WebSocket | Real-time bidirectional command/state channel |

### WebSocket Protocol

```json
// Send command
{"id": "cmd_001", "module": "mixer", "action": "setTrackVolume", "params": {"track": 1, "volume": 0.78}}

// Receive response
{"id": "cmd_001", "status": "ok", "result": {"previous": 0.65, "current": 0.78}}

// Receive state broadcast
{"type": "state", "data": {"transport": {"playing": true, "tempo": 140.0}, ...}}
```

---

## Roadmap

- [x] **Phase 1:** Project setup, FL Studio MIDI Script, Named Pipe bridge, basic commands
- [x] **Phase 2:** Claude tool-use orchestrator, Gemini vision pipeline, OmniParser GCP deployment, full API coverage
- [ ] **Phase 3:** Vision Layer MVP — end-to-end plugin GUI automation
- [ ] **Phase 4:** Voice input (Whisper), Web dashboard
- [ ] **Phase 5:** Plugin preset management, automation clips, playlist editing

---

## Development

```bash
# Install dependencies (including dev)
uv sync --all-extras

# Run all tests
uv run pytest -v

# Run only unit tests
uv run pytest tests/test_*.py -v

# Run only integration tests
uv run pytest tests/integration/ -v

# Lint
uv run ruff check dawmind/ tests/

# Format
uv run ruff format dawmind/ tests/
```

CI runs on every push and PR via GitHub Actions — linting, formatting, and the full test suite on Python 3.12 and 3.13.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.12+ |
| Package Manager | uv |
| Server | FastAPI + Uvicorn |
| IPC | Windows Named Pipes / file fallback |
| Planning LLM | Claude Sonnet 4 (Anthropic) |
| Vision LLM | Gemini 2.5 Flash (GCP) |
| UI Parsing | OmniParser V2 (GCP Cloud Run, L4 GPU) |
| Screen Capture | mss |
| Input Simulation | PyAutoGUI |
| CLI | Rich |
| CI | GitHub Actions |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

**Built by [Andre Elsen](https://github.com/aelsen1808)** — A project exploring the intersection of AI agents and creative tools.
