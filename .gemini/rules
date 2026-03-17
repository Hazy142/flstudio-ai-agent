# DAWMind – Project Rules for Antigravity Agent
# These rules guide the Gemini agent on architecture, conventions, and constraints.

## Project Overview
DAWMind is an AI agent that controls FL Studio through a hybrid approach:
- **Layer 1 (API):** FL Studio MIDI Script → Named Pipe/File IPC → Bridge Server (FastAPI WebSocket :9500) → Orchestrator
- **Layer 2 (Vision):** Screenshot (mss) → OmniParser V2 (GCP Cloud Run, L4 GPU) → Gemini 2.5 Flash → PyAutoGUI

The orchestrator uses Claude's native tool-use API in an agentic loop: Claude plans → calls tools → gets results → iterates until the user's request is fulfilled.

## Architecture Rules

### IPC Layer (fl_script/)
- `fl_script/device_DAWMind.py` and `fl_script/ipc_handler.py` run INSIDE FL Studio's embedded Python interpreter.
- FL Studio Python has NO pip packages, NO asyncio, limited stdlib. Keep these files pure stdlib only.
- IPC protocol: Named Pipe (primary) with file-based fallback (`%TEMP%/dawmind_ipc/`).
- File IPC uses `.jsonl` for commands/responses and `.json` for state.
- NEVER add third-party imports to files in `fl_script/`.

### Bridge Server (dawmind/api_layer/)
- FastAPI + WebSocket on port 9500 (configurable in `config/dawmind.toml`).
- `bridge_server.py` is the entry point. It reads IPC and relays to WebSocket clients.
- `commands.py` defines the Command/CommandResponse protocol.
- `state.py` defines the DAWState, MixerTrackState, ChannelState, PluginState dataclasses.
- `protocol.py` handles message framing.

### Orchestrator (dawmind/orchestrator.py)
- This is the agentic brain. It uses Claude's tool-use API (`send_messages()`).
- The agentic loop: build message with DAW state → send to Claude → parse tool_calls → execute via `execute_tool()` → feed results back → repeat until Claude returns text (no more tool calls) or max_iterations (25).
- ActionLayer enum: API (direct FL Studio commands) or VISION (screenshot + GUI interaction).
- State is refreshed every iteration via WebSocket.

### Tool Registry (dawmind/tools/__init__.py)
- Central registry: `ALL_TOOLS` list (24 tools) with Claude-compatible JSON schemas.
- Categories: STATE (get_daw_state), TRANSPORT (play, stop, record, set_tempo), MIXER (get/set volume, pan, mute, solo), CHANNEL (get_name, set_volume, count, select), PLUGIN (get/set params), VISION (click, drag_knob, read_display, screenshot).
- `execute_tool(name, params)` routes to the correct Command constructor.
- `is_vision_tool(name)` determines if a tool needs the vision pipeline.
- To add a new tool: (1) add definition to the category file, (2) add routing in `execute_tool()`, (3) add Command constructor in `commands.py`, (4) handle in `device_DAWMind.py`.

### LLM Clients (dawmind/llm/)
- `claude.py` – Planning model. `send_messages()` for tool-use, `complete()` for simple text. Uses `ToolCall` and `AgentResponse` dataclasses.
- `gemini_client.py` – Vision model. `analyze_screenshot()` for image analysis. Retry logic with exponential backoff.
- `local.py` – Ollama client for offline fallback (placeholder).
- `router.py` – Routes between LLM backends based on `config.llm.router_strategy`.

### Vision Pipeline (dawmind/vision_layer/)
- `capture.py` – Screenshot via `mss`. Caches for `screenshot_cache_seconds`.
- `parser.py` – Sends screenshot to OmniParser V2 HTTP endpoint. Returns UI element bounding boxes.
- `reasoning.py` – Full pipeline: capture → OmniParser → annotate image → Gemini analysis → VisionAction.
- `executor.py` – Translates VisionAction to PyAutoGUI calls (click, drag, type, scroll).
- `verifier.py` – Takes a second screenshot to verify the action worked.

### OmniParser Deployment (omniparser/)
- Dockerfile for GPU-accelerated OmniParser V2 server.
- `deploy_gcp.sh` deploys to GCP Cloud Run with L4 GPU.
- `server.py` is a FastAPI app with `/parse` endpoint.
- Endpoint configured in `config/dawmind.toml` → `vision.omniparser_endpoint`.

## Coding Conventions

### Python
- Python 3.12+ required. Use modern syntax (type hints, StrEnum, dataclasses, `match`).
- Line length: 100 (configured in `pyproject.toml` via ruff).
- Linter: `ruff`. Run `ruff check .` before committing.
- Async everywhere in the dawmind package. Use `async def` for any I/O operation.
- Pydantic v2 for external-facing models, dataclasses for internal state.

### Configuration
- All config in `config/dawmind.toml`. Loaded by `dawmind/config.py`.
- API keys from environment variables: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`.
- Never hardcode API keys, endpoints, or port numbers.

### Testing
- Framework: `pytest` + `pytest-asyncio`.
- Run all tests: `python -m pytest tests/ -v`
- 276 tests currently passing. NEVER reduce test count.
- Unit tests in `tests/test_*.py` – mock all external APIs (anthropic, google, httpx).
- Integration tests in `tests/integration/` – use `mock_fl_studio.py` simulator.
- When adding features, add tests. Aim for the same patterns as existing tests.

### Git
- Main branch: `main`.
- Write descriptive commit messages. List changed components.
- Run tests before committing.

## Multi-Model Strategy
| Model | Role | Why |
|-------|------|-----|
| Claude Sonnet 4 | Planning & orchestration | Best tool-use API, strong reasoning |
| Gemini 2.5 Flash | Vision analysis | Fast, cheap (user has 300€ GCP credits) |
| OmniParser V2 | UI element detection | Open-source, GPU-accelerated on GCP |
| Whisper | Voice commands | Planned – not yet implemented |
| Ollama (local) | Offline fallback | Planned – not yet implemented |

## Current Status (Phase 2 complete)
✅ FL Studio MIDI script with IPC
✅ Bridge server (FastAPI WebSocket)
✅ Claude tool-use agentic orchestrator (24 tools)
✅ Gemini vision client with retry logic
✅ Vision pipeline (OmniParser → Gemini → VisionAction)
✅ OmniParser GCP deployment scripts
✅ 276 tests (unit + integration with mock FL Studio)
✅ CI with Python 3.12+3.13 matrix

## Next Up (Phase 3+)
🔲 Whisper voice command pipeline
🔲 Real FL Studio testing on Windows
🔲 OmniParser deployment to GCP with user's credits
🔲 Plugin preset management tools
🔲 Pattern/playlist editing tools
🔲 Undo/redo support
🔲 Session recording & playback
