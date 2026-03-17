"""Bridge Server -- WebSocket <-> FL Studio IPC bridge.

Exposes a FastAPI application with:
- WebSocket endpoint for real-time bidirectional communication
- REST endpoints for health checks, state queries, and IPC diagnostics
- Background task that reads FL Studio state via file-based IPC and broadcasts to clients

IPC is entirely file-based for reliability.  Named Pipes may be re-added
as an optional optimisation in a future release.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from dawmind.api_layer.protocol import Command
from dawmind.config import DAWMindConfig, load_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File-based IPC helpers (bridge-server side)
# ---------------------------------------------------------------------------

_IPC_DIR = os.path.join(os.environ.get("TEMP", "/tmp"), "dawmind_ipc")

# Heartbeat is considered fresh if updated within this many seconds.
_HEARTBEAT_MAX_AGE_SECONDS = 5.0


def _get_ipc_dir() -> str:
    """Return the IPC directory path."""
    return _IPC_DIR


def _ensure_ipc_dir() -> None:
    os.makedirs(_IPC_DIR, exist_ok=True)


def _send_command_via_file(cmd: Command) -> None:
    """Write a command to the file-based IPC command file."""
    path = os.path.join(_IPC_DIR, "commands.jsonl")
    with open(path, "a") as f:
        f.write(cmd.to_json_line())


def _read_responses_from_file() -> list[dict]:
    """Read and consume all pending responses from the file IPC."""
    path = os.path.join(_IPC_DIR, "responses.jsonl")
    responses: list[dict] = []
    try:
        with open(path) as f:
            lines = f.readlines()
        if lines:
            with open(path, "w") as f:
                f.write("")
            for line in lines:
                line = line.strip()
                if line:
                    try:
                        responses.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return responses


def _read_state_from_file() -> dict | None:
    """Read the latest state snapshot from file IPC."""
    path = os.path.join(_IPC_DIR, "state.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _read_heartbeat() -> float | None:
    """Read the heartbeat timestamp.  Returns None if missing or unreadable."""
    path = os.path.join(_IPC_DIR, "heartbeat")
    try:
        with open(path) as f:
            return float(f.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _is_heartbeat_fresh() -> bool:
    """Return True if the heartbeat file was updated recently."""
    ts = _read_heartbeat()
    if ts is None:
        return False
    return (time.time() - ts) < _HEARTBEAT_MAX_AGE_SECONDS


def _get_ipc_info() -> dict:
    """Gather diagnostic information about the IPC directory."""
    info: dict = {
        "ipc_dir": _IPC_DIR,
        "ipc_dir_exists": os.path.isdir(_IPC_DIR),
        "files": [],
        "heartbeat_ts": None,
        "heartbeat_age_seconds": None,
        "heartbeat_fresh": False,
        "state_exists": False,
        "commands_exists": False,
        "responses_exists": False,
    }
    if info["ipc_dir_exists"]:
        try:
            info["files"] = sorted(os.listdir(_IPC_DIR))
        except OSError:
            pass
        info["state_exists"] = os.path.isfile(os.path.join(_IPC_DIR, "state.json"))
        info["commands_exists"] = os.path.isfile(os.path.join(_IPC_DIR, "commands.jsonl"))
        info["responses_exists"] = os.path.isfile(os.path.join(_IPC_DIR, "responses.jsonl"))

        ts = _read_heartbeat()
        if ts is not None:
            info["heartbeat_ts"] = ts
            info["heartbeat_age_seconds"] = round(time.time() - ts, 2)
            info["heartbeat_fresh"] = (time.time() - ts) < _HEARTBEAT_MAX_AGE_SECONDS
    return info


# ---------------------------------------------------------------------------
# Bridge application
# ---------------------------------------------------------------------------


class BridgeState:
    """Shared state for the bridge server."""

    def __init__(self) -> None:
        self.clients: list[WebSocket] = []
        self.daw_state: dict = {}
        self.pending_responses: dict[str, asyncio.Future] = {}
        self.config: DAWMindConfig = load_config()
        self.fl_studio_connected: bool = False


bridge_state = BridgeState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage bridge server lifecycle."""
    logger.info("Starting DAWMind Bridge Server")
    _ensure_ipc_dir()
    logger.info("Using file-based IPC at %s", _IPC_DIR)

    # Start background state polling
    poll_task = asyncio.create_task(_state_poll_loop())

    yield

    poll_task.cancel()
    logger.info("Bridge Server stopped")


app = FastAPI(title="DAWMind Bridge", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        {
            "status": "ok",
            "fl_studio_connected": bridge_state.fl_studio_connected,
            "connected_clients": len(bridge_state.clients),
        }
    )


@app.get("/api/state")
async def get_state() -> JSONResponse:
    """Return the latest DAW state snapshot."""
    return JSONResponse(bridge_state.daw_state or {"error": "No state available"})


@app.get("/api/ipc-info")
async def ipc_info() -> JSONResponse:
    """Return diagnostic information about the IPC layer."""
    info = await asyncio.to_thread(_get_ipc_info)
    info["fl_studio_connected"] = bridge_state.fl_studio_connected
    return JSONResponse(info)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time communication."""
    await ws.accept()
    bridge_state.clients.append(ws)
    logger.info("Client connected (%d total)", len(bridge_state.clients))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"status": "error", "error": "Invalid JSON"})
                continue

            # Build command and forward to FL Studio
            cmd = Command.model_validate(data)
            logger.info("Command: %s.%s", cmd.module, cmd.action)

            # Create a future for the response
            future: asyncio.Future = asyncio.get_event_loop().create_future()
            bridge_state.pending_responses[cmd.id] = future

            await asyncio.to_thread(_send_command_via_file, cmd)

            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(future, timeout=5.0)
                await ws.send_json(response)
            except TimeoutError:
                await ws.send_json(
                    {"id": cmd.id, "status": "timeout", "error": "FL Studio did not respond"}
                )
            finally:
                bridge_state.pending_responses.pop(cmd.id, None)

    except WebSocketDisconnect:
        pass
    finally:
        bridge_state.clients.remove(ws)
        logger.info("Client disconnected (%d remaining)", len(bridge_state.clients))


async def _state_poll_loop() -> None:
    """Background task: poll FL Studio state and broadcast to clients."""
    interval = bridge_state.config.fl_studio.state_poll_interval_ms / 1000.0

    while True:
        try:
            # Check heartbeat for connection status
            bridge_state.fl_studio_connected = await asyncio.to_thread(_is_heartbeat_fresh)

            # Read state from IPC
            state = await asyncio.to_thread(_read_state_from_file)
            if state:
                bridge_state.daw_state = state

                # Broadcast to connected WebSocket clients
                msg = json.dumps({"type": "state", "data": state})
                disconnected = []
                for client in bridge_state.clients:
                    try:
                        await client.send_text(msg)
                    except Exception:
                        disconnected.append(client)
                for client in disconnected:
                    bridge_state.clients.remove(client)

            # Also check for command responses
            responses = await asyncio.to_thread(_read_responses_from_file)
            for resp in responses:
                cmd_id = resp.get("id", "")
                future = bridge_state.pending_responses.get(cmd_id)
                if future and not future.done():
                    future.set_result(resp)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in state poll loop")

        await asyncio.sleep(interval)


def run_bridge(config: DAWMindConfig | None = None) -> None:
    """Run the bridge server (blocking)."""
    import uvicorn

    if config:
        bridge_state.config = config

    uvicorn.run(
        app,
        host=bridge_state.config.server.host,
        port=bridge_state.config.server.ws_port,
        log_level="info",
    )
