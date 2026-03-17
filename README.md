# DAWMind

**AI Agent for FL Studio** — Control your DAW with natural language. From mixer adjustments to plugin GUI automation, DAWMind bridges the gap between AI reasoning and music production.

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

DAWMind is an AI agent that controls FL Studio through two complementary layers:

1. **API Layer** — Direct, fast, reliable control via FL Studio's built-in Python MIDI Scripting API. Handles transport, mixer, channels, plugin parameters, and more.

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
┌─────────────────────────────────────────────────┐
│              DAWMind Orchestrator                │
│         (LLM Planning · Action Dispatch)        │
└────────┬────────────────────┬───────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌────────────────────────────┐
│  Layer 1: API   │  │  Layer 2: Vision            │
│                 │  │                              │
│  Named Pipe IPC │  │  Screenshot → OmniParser V2  │
│  ↕              │  │  → Gemini Flash (reasoning)  │
│  FL Studio MIDI │  │  → PyAutoGUI (execution)     │
│  Script (Python)│  │  → Verify (re-screenshot)    │
└─────────────────┘  └────────────────────────────┘
```

### Multi-Model Strategy

| Role | Model | Why |
|------|-------|-----|
| Task Planning | Claude Sonnet | Best agentic reasoning and tool-use |
| Vision Analysis | Gemini 2.5 Flash | Fast, affordable vision via GCP credits |
| UI Detection | OmniParser V2 | Purpose-built for GUI element parsing |
| Voice Commands | Whisper | Best open-source speech-to-text |
| Quick Lookups | Ollama (local) | Free, no API cost |

---

## Quick Start

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
│   ├── tools/                   # Claude tool-use definitions
│   │   ├── mixer_tools.py
│   │   ├── channel_tools.py
│   │   ├── transport_tools.py
│   │   ├── plugin_tools.py
│   │   └── vision_tools.py
│   └── voice/                   # (planned) Whisper voice input
├── fl_script/                   # Runs inside FL Studio
│   ├── device_DAWMind.py        # MIDI controller script
│   └── ipc_handler.py           # Named Pipe / file IPC
├── config/dawmind.toml          # Configuration
├── tests/                       # pytest test suite
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
- [ ] **Phase 2:** Full mixer/channel/plugin API coverage, event-driven state updates
- [ ] **Phase 3:** Vision Layer MVP — OmniParser + Gemini Flash + PyAutoGUI
- [ ] **Phase 4:** Full LLM orchestration with Claude tool-use planning
- [ ] **Phase 5:** Voice input (Whisper), Web dashboard, plugin preset management

---

## Development

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check dawmind/ tests/

# Format
uv run ruff format dawmind/ tests/
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.12+ |
| Package Manager | uv |
| Server | FastAPI + Uvicorn |
| IPC | Windows Named Pipes / file fallback |
| Screen Capture | mss |
| UI Parsing | OmniParser V2 (GCP GPU) |
| Vision LLM | Gemini 2.5 Flash (GCP) |
| Planning LLM | Claude Sonnet (Anthropic) |
| Input Simulation | PyAutoGUI |
| CLI | Rich |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

**Built by [André Elsen](https://github.com/aelsen1808)** — A project exploring the intersection of AI agents and creative tools.
