# FL Studio AI Agent – Architecture Document

## Project: `flstudio-ai-agent`
**Codename:** DAWMind  
**Author:** André Elsen  
**Created:** 2026-03-17  
**Status:** Design Phase  

---

## 1. Vision

An AI agent that controls FL Studio like browser-based AI agents control browsers – with full GUI automation capability for third-party plugins, combined with deep API-level control for native FL Studio operations. The agent can "see" FL Studio, understand its state, and take autonomous actions to mix, arrange, and tweak plugins on natural language instructions.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    DAWMind Orchestrator                       │
│              (Python · FastAPI · WebSocket Hub)               │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ LLM Router   │  │ Task Planner │  │ State Manager     │  │
│  │              │  │              │  │ (DAW State Cache)  │  │
│  │ Claude API   │  │ Break down   │  │                   │  │
│  │ GPT-4o       │  │ "make kick   │  │ Tracks, Mixer,    │  │
│  │ Whisper      │  │  punchier"   │  │ Plugins, Params   │  │
│  │ Local/Ollama │  │  into steps  │  │ Screenshot Cache   │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────────┘  │
│         │                 │                   │               │
│  ┌──────▼─────────────────▼───────────────────▼───────────┐  │
│  │              Action Dispatcher                          │  │
│  │  Routes actions to the correct execution layer          │  │
│  └──────┬──────────────────────┬──────────────────────────┘  │
│         │                      │                              │
└─────────┼──────────────────────┼──────────────────────────────┘
          │                      │
          ▼                      ▼
┌─────────────────────┐  ┌──────────────────────────────────┐
│  Layer 1: API       │  │  Layer 2: Vision                  │
│  FL Studio MIDI     │  │  Screen-Based GUI Control          │
│  Scripting API      │  │                                    │
│                     │  │  ┌────────────────────────────┐   │
│  • mixer.*          │  │  │ Screenshot Capture          │   │
│  • channels.*       │  │  │ (mss / PIL)                 │   │
│  • plugins.*        │  │  └─────────┬──────────────────┘   │
│  • transport.*      │  │            │                       │
│  • playlist.*       │  │  ┌─────────▼──────────────────┐   │
│  • patterns.*       │  │  │ OmniParser V2              │   │
│  • ui.*             │  │  │ (UI Element Detection)      │   │
│                     │  │  └─────────┬──────────────────┘   │
│  Communication:     │  │            │                       │
│  Named Pipe /       │  │  ┌─────────▼──────────────────┐   │
│  Virtual MIDI /     │  │  │ Vision LLM                  │   │
│  WebSocket Bridge   │  │  │ (Claude/GPT-4o Vision)      │   │
│                     │  │  │ → Decide: what to click     │   │
└─────────────────────┘  │  └─────────┬──────────────────┘   │
                         │            │                       │
                         │  ┌─────────▼──────────────────┐   │
                         │  │ PyAutoGUI / Win32 API       │   │
                         │  │ (Mouse + Keyboard Control)  │   │
                         │  └────────────────────────────┘   │
                         └──────────────────────────────────┘

```

---

## 3. The Two Execution Layers

### Layer 1: FL Studio API Layer (Fast, Reliable, Structured)

**What it controls:**
- Transport (play, stop, record, tempo, time signature)
- Mixer (volume, pan, mute, solo, routing, effect slots)
- Channels (add, remove, select, name, color, volume)
- Plugins (get/set parameter values by index, preset navigation)
- Playlist (track management, arrangement)
- Patterns (selection, naming)
- UI (window management, navigation, browser control)

**Communication Architecture:**

```
Orchestrator ──WebSocket──▶ Bridge Server (localhost:9500)
                                    │
                                    ▼
                           Named Pipe / Shared Memory
                                    │
                                    ▼
                           FL Studio MIDI Script
                           (device_DAWMind.py)
                                    │
                                    ▼
                           FL Studio Internal API
                           (mixer, channels, plugins, etc.)
```

The MIDI Script runs inside FL Studio's Python interpreter and has direct access to all API modules. The bridge server translates high-level commands (JSON) into API calls.

**Why not just MIDI messages?**
- MIDI is limited to 7-bit values (0-127) – not enough precision
- No way to read state back efficiently via MIDI
- Named Pipes / shared memory allow bidirectional, high-bandwidth communication

**Key API capabilities (from FL Studio API Stubs):**

| Module | Key Functions | Use Case |
|--------|--------------|----------|
| `plugins` | `getParamCount()`, `getParamName()`, `getParamValue()`, `setParamValue()`, `getPluginName()`, `nextPreset()`, `prevPreset()` | Control any plugin parameter by index |
| `mixer` | Volume, pan, mute, solo, routing, EQ | Full mixer control |
| `channels` | Add/remove/select channels, set properties | Channel rack management |
| `transport` | Play, stop, record, tempo, position | Playback control |
| `playlist` | Track management, arrangement | Arrangement editing |
| `ui` | Window management, navigation, browser | UI state and navigation |

### Layer 2: Vision Layer (Flexible, Universal, Plugin GUIs)

**Purpose:** Control anything the API can't reach – especially third-party plugin GUIs (Serum, Vital, OTT, Omnisphere, etc.)

**Pipeline:**

```
1. CAPTURE    →  Screenshot of FL Studio / Plugin window
                 Tool: mss (fast screen capture) or Win32 API
                 
2. PARSE      →  Detect UI elements (knobs, sliders, buttons, dropdowns)
                 Tool: OmniParser V2 (Microsoft, open source)
                 Outputs: Bounding boxes + semantic labels
                 
3. REASON     →  Send parsed screenshot + task to Vision LLM
                 Tool: Claude Vision / GPT-4o / Gemini
                 Output: Action plan (click X,Y / drag from A to B / type "value")
                 
4. EXECUTE    →  Perform mouse/keyboard actions
                 Tool: PyAutoGUI + Win32 SendInput API
                 
5. VERIFY     →  Take new screenshot, confirm action succeeded
                 Tool: Same as step 1-3, comparison logic
```

**Why OmniParser V2?**
- Open source (Microsoft), specifically designed for GUI agent use
- Detects interactable elements (knobs, buttons, sliders) without DOM/accessibility tree
- Works with any plugin GUI – no plugin-specific code needed
- Can be combined with any VLM (Claude, GPT-4o, local models)

**Knob/Slider Interaction Strategy:**
VST plugin knobs are the hardest UI element to automate:
- **Detection:** OmniParser identifies knob bounding boxes
- **Current value estimation:** Vision LLM estimates current knob position from screenshot
- **Interaction:** Vertical drag gestures (most VST knobs respond to vertical mouse movement)
- **Verification:** Re-screenshot and compare to confirm value changed correctly
- **Fallback:** If plugin exposes VST3 parameters → use Layer 1 `plugins.setParamValue()`

---

## 4. Multi-Model Strategy

| Model | Role | Why |
|-------|------|-----|
| **Claude Sonnet 4** | Primary reasoning, task planning, tool use | Best agentic capabilities, strong tool use |
| **GPT-4o** | Vision analysis, screenshot understanding | Strong multimodal, fast vision |
| **OmniParser V2** | UI element detection | Purpose-built for GUI parsing |
| **Whisper** | Voice commands ("make the kick louder") | Best open-source speech-to-text |
| **Local model (Ollama)** | Quick parameter lookups, caching | No API cost for simple tasks |

**Router Logic:**
```python
def route_task(task: Task) -> Model:
    if task.requires_vision:
        return GPT4O  # or Claude Vision
    if task.requires_planning:
        return CLAUDE  # best at multi-step reasoning
    if task.requires_audio_analysis:
        return WHISPER + CLAUDE
    if task.is_simple_lookup:
        return LOCAL_MODEL
```

---

## 5. State Management

The agent needs to maintain an accurate model of FL Studio's current state:

```python
@dataclass
class DAWState:
    # Transport
    is_playing: bool
    is_recording: bool
    tempo: float
    time_signature: tuple[int, int]
    song_position: float
    
    # Channels
    channels: list[Channel]  # name, plugin, volume, pan, color, muted
    selected_channel: int
    
    # Mixer
    mixer_tracks: list[MixerTrack]  # volume, pan, muted, solo, effects
    
    # Plugins (per channel/mixer slot)
    plugins: dict[str, PluginState]  # plugin_name -> {params: {name: value}}
    
    # Active Windows
    focused_window: str  # "Mixer", "Playlist", "Piano Roll", "Plugin: Serum"
    
    # Screenshot cache
    last_screenshot: bytes
    last_screenshot_time: float
    parsed_elements: list[UIElement]  # from OmniParser
```

**State Sync Strategy:**
- **Polling:** Every 500ms via `OnIdle` callback in MIDI script → push state via Named Pipe
- **Event-driven:** `OnRefresh`, `OnDirtyMixerTrack`, `OnDirtyChannel` callbacks for real-time updates
- **Screenshot refresh:** On-demand when Vision Layer is invoked, cached for 2 seconds

---

## 6. Communication Protocol

### Orchestrator ↔ Bridge Server (WebSocket JSON)

```json
// Command: Set mixer track volume
{
    "id": "cmd_001",
    "layer": "api",
    "module": "mixer",
    "action": "setTrackVolume",
    "params": {
        "track": 5,
        "volume": 0.78
    }
}

// Command: Click plugin knob
{
    "id": "cmd_002",
    "layer": "vision",
    "action": "interact",
    "target": {
        "description": "Cutoff frequency knob in Serum",
        "plugin_window": "Serum",
        "element_hint": "cutoff knob, top-left area"
    },
    "interaction": {
        "type": "drag_vertical",
        "direction": "up",
        "amount": 30
    }
}

// Response
{
    "id": "cmd_001",
    "status": "success",
    "result": {
        "previous_value": 0.65,
        "new_value": 0.78
    }
}
```

### Bridge Server ↔ FL Studio MIDI Script (Named Pipe)

```
Pipe: \\.\pipe\dawmind

Format: JSON lines (one JSON object per line)
Direction: Bidirectional

Server → FL Studio: Commands
FL Studio → Server: State updates, command results
```

---

## 7. Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| **Orchestrator** | Python 3.12 + FastAPI | Async, fast, good LLM SDK ecosystem |
| **WebSocket Server** | FastAPI WebSocket | Built-in, battle-tested |
| **Bridge Server** | Python (separate process) | Translates WS commands to Named Pipe |
| **FL Studio Script** | Python (FL internal) | Only option, runs in FL's Python interpreter |
| **IPC** | Named Pipes (Windows) | Fast, bidirectional, no network overhead |
| **Screen Capture** | `mss` library | Fastest Python screen capture (60+ FPS) |
| **UI Parsing** | OmniParser V2 | Best open-source UI element detection |
| **Mouse/Keyboard** | PyAutoGUI + ctypes Win32 | Reliable input simulation |
| **Vision LLM** | Claude Vision / GPT-4o | Screenshot understanding |
| **Task Planning** | Claude Sonnet 4 | Best reasoning for multi-step tasks |
| **Voice Input** | Whisper (OpenAI) | Optional voice commands |
| **Config** | TOML | Simple, readable config files |
| **Package Manager** | `uv` | Fast, modern Python package manager |
| **Frontend** (optional) | Web UI (Svelte/React) | Status dashboard, chat interface |

---

## 8. Project Structure

```
flstudio-ai-agent/
├── README.md
├── LICENSE                      # MIT
├── pyproject.toml               # uv/pip project config
├── .env.example                 # API keys template
│
├── dawmind/                     # Main Python package
│   ├── __init__.py
│   ├── orchestrator.py          # Main agent loop
│   ├── config.py                # Configuration loading
│   │
│   ├── llm/                     # LLM integrations
│   │   ├── __init__.py
│   │   ├── router.py            # Model selection logic
│   │   ├── claude.py            # Anthropic Claude client
│   │   ├── openai_client.py     # OpenAI GPT-4o client
│   │   └── local.py             # Ollama local model client
│   │
│   ├── api_layer/               # Layer 1: FL Studio API
│   │   ├── __init__.py
│   │   ├── bridge_server.py     # WebSocket ↔ Named Pipe bridge
│   │   ├── commands.py          # Command definitions
│   │   ├── state.py             # DAW state model
│   │   └── protocol.py          # IPC protocol handling
│   │
│   ├── vision_layer/            # Layer 2: Screen-based control
│   │   ├── __init__.py
│   │   ├── capture.py           # Screenshot capture (mss)
│   │   ├── parser.py            # OmniParser V2 integration
│   │   ├── reasoning.py         # Vision LLM decision making
│   │   ├── executor.py          # PyAutoGUI action execution
│   │   └── verifier.py          # Action verification
│   │
│   ├── tools/                   # Agent tool definitions
│   │   ├── __init__.py
│   │   ├── mixer_tools.py       # set_volume, set_pan, add_effect...
│   │   ├── channel_tools.py     # add_channel, select_channel...
│   │   ├── transport_tools.py   # play, stop, set_tempo...
│   │   ├── plugin_tools.py      # set_param, get_params, change_preset...
│   │   └── vision_tools.py      # click_element, drag_knob, read_display...
│   │
│   └── voice/                   # Optional voice input
│       ├── __init__.py
│       └── whisper_input.py     # Microphone → text via Whisper
│
├── fl_script/                   # Goes into FL Studio Settings/Hardware/
│   ├── device_DAWMind.py        # Main MIDI controller script
│   ├── pipe_client.py           # Named Pipe client for IPC
│   └── state_reporter.py        # Periodic state broadcast
│
├── config/
│   └── dawmind.toml             # Main configuration file
│
├── tests/
│   ├── test_bridge.py
│   ├── test_vision.py
│   ├── test_commands.py
│   └── test_state.py
│
└── docs/
    ├── ARCHITECTURE.md           # This file
    ├── SETUP.md                  # Installation guide
    ├── API_REFERENCE.md          # Available commands
    └── ROADMAP.md                # Development roadmap
```

---

## 9. Development Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Project setup (repo, CI, dependencies)
- [ ] FL Studio MIDI Script with Named Pipe IPC
- [ ] Bridge Server (WebSocket ↔ Named Pipe)
- [ ] Basic state reporting (transport, mixer levels)
- [ ] First API commands: play/stop, set volume, set tempo

### Phase 2: API Layer Complete (Weeks 3-4)
- [ ] Full mixer control (volume, pan, mute, solo, routing)
- [ ] Channel rack operations
- [ ] Plugin parameter read/write via `plugins` module
- [ ] Pattern/playlist operations
- [ ] Comprehensive state model with event-driven updates

### Phase 3: Vision Layer MVP (Weeks 5-7)
- [ ] Screenshot capture pipeline
- [ ] OmniParser V2 integration for UI element detection
- [ ] Vision LLM integration (GPT-4o) for action reasoning
- [ ] PyAutoGUI executor with knob/slider interaction
- [ ] Action verification loop (screenshot → compare → retry)

### Phase 4: Orchestrator & Agent Loop (Weeks 8-10)
- [ ] LLM Router (Claude for planning, GPT-4o for vision)
- [ ] Task planner: decompose natural language → action sequence
- [ ] Tool definitions for Claude tool-use
- [ ] Hybrid routing: API Layer when possible, Vision Layer as fallback
- [ ] Error recovery and retry logic

### Phase 5: Polish & Extras (Weeks 11-12)
- [ ] Voice input via Whisper
- [ ] Web dashboard UI
- [ ] Plugin preset management
- [ ] Session save/restore
- [ ] Documentation and tutorials

---

## 10. Existing Projects & How We Differ

| Project | Approach | Limitation | Our Advantage |
|---------|----------|------------|---------------|
| [veenastudio/flstudio-mcp](https://github.com/veenastudio/flstudio-mcp) | MIDI messages via virtual ports | 7-bit MIDI limits, no state readback, hacky encoding | Named Pipes for full bidirectional JSON, no MIDI constraints |
| [calvinw/fl-studio-mcp](https://github.com/calvinw/fl-studio-mcp) | File-based queue + keyboard trigger | Slow (file I/O + keystroke trigger), piano roll only | Real-time IPC, full DAW control, not just piano roll |
| [karl-andres/fl-studio-mcp](https://github.com/karl-andres/fl-studio-mcp) | MIDI + Piano Roll scripts | Similar to above, limited scope | Full agent architecture with vision |
| [REAPER MCP Server](https://github.com/itsuzef/reaper-mcp) | OSC protocol, REAPER only | Different DAW, no vision layer | FL Studio native + universal plugin GUI control |
| Claude Computer Use | Generic desktop control | Not DAW-aware, no API integration | DAW-specific + API layer for speed + Vision for plugins |

**Our key differentiator: Hybrid Architecture.**  
No existing project combines native FL Studio API access with vision-based plugin GUI automation. We get the speed and reliability of API calls for structural operations, and the universality of screen-based control for any plugin GUI.

---

## 11. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| FL Studio Python interpreter limitations (no pip, limited stdlib) | High | Keep FL script minimal, heavy logic in bridge server |
| Named Pipe blocked by FL Studio sandboxing | Medium | Fallback to file-based IPC or virtual MIDI |
| OmniParser accuracy on VST plugin GUIs | Medium | Fine-tune on DAW screenshots, manual fallback mappings |
| Knob interaction precision (vertical drag) | Medium | Implement calibration routine per plugin |
| API rate limits on LLM calls | Low | Cache decisions, batch screenshots, use local models for simple tasks |
| FL Studio API changes between versions | Low | Pin to FL Studio 2024+ API stubs, version detection |

---

## 12. Quick Start (Target)

```bash
# Install
git clone https://github.com/aelsen1808/flstudio-ai-agent.git
cd flstudio-ai-agent
uv sync

# Configure
cp .env.example .env
# Add your API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY)

# Install FL Studio script
cp fl_script/* "~/Documents/Image-Line/FL Studio/Settings/Hardware/DAWMind/"

# Start the agent
uv run dawmind

# In FL Studio: MIDI Settings → Controller type → DAWMind (user)
# The agent is now connected and listening.

# Talk to it:
# "Set the kick volume to -3dB"
# "Open Serum on channel 2 and turn the cutoff to 50%"  
# "Make the snare punchier"
```
