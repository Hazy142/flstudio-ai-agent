"""Bridge Server – WebSocket ↔ FL Studio IPC bridge.

Exposes a FastAPI application with:
- WebSocket endpoint for real-time bidirectional communication
- REST endpoints for health checks and state queries
- Background task that reads FL Studio state via IPC and broadcasts to clients
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
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


# ---------------------------------------------------------------------------
# Named Pipe server (Windows)
# ---------------------------------------------------------------------------


class NamedPipeServer:
    """Async Named Pipe server for Windows.

    Falls back to file-based IPC on non-Windows platforms.
    """

    def __init__(self, pipe_name: str = "dawmind"):
        self._pipe_name = pipe_name
        self._pipe_path = rf"\\.\pipe\{pipe_name}"
        self._handle = None
        self._connected = False
        self._use_file_fallback = sys.platform != "win32"
        self._buffer = ""

    async def start(self) -> None:
        """Create and listen on the named pipe."""
        if self._use_file_fallback:
            _ensure_ipc_dir()
            logger.info("Using file-based IPC at %s", _IPC_DIR)
            return

        try:
            import ctypes

            pipe_access_duplex = 0x00000003
            pipe_type_byte = 0x00000000
            pipe_readmode_byte = 0x00000000
            pipe_nowait = 0x00000001
            nmpwait_default = 0x00000000

            kernel32 = ctypes.windll.kernel32
            self._handle = kernel32.CreateNamedPipeW(
                self._pipe_path,
                pipe_access_duplex,
                pipe_type_byte | pipe_readmode_byte | pipe_nowait,
                1,  # max instances
                4096,  # out buffer
                4096,  # in buffer
                nmpwait_default,
                None,
            )
            if self._handle == -1:
                logger.warning("Failed to create named pipe, falling back to file IPC")
                self._use_file_fallback = True
                _ensure_ipc_dir()
            else:
                logger.info("Named Pipe server listening on %s", self._pipe_path)
        except Exception as exc:
            logger.warning("Named pipe creation failed (%s), using file IPC", exc)
            self._use_file_fallback = True
            _ensure_ipc_dir()

    async def send_command(self, cmd: Command) -> None:
        """Send a command to FL Studio."""
        if self._use_file_fallback:
            await asyncio.to_thread(_send_command_via_file, cmd)
            return

        data = cmd.to_json_line().encode("utf-8")
        try:
            import ctypes
            import ctypes.wintypes

            written = ctypes.wintypes.DWORD(0)
            ctypes.windll.kernel32.WriteFile(
                self._handle, data, len(data), ctypes.byref(written), None
            )
        except Exception as exc:
            logger.error("Pipe write failed: %s", exc)

    async def read_responses(self) -> list[dict]:
        """Read pending responses from FL Studio."""
        if self._use_file_fallback:
            return await asyncio.to_thread(_read_responses_from_file)
        # Named pipe reading would go here
        return []

    async def read_state(self) -> dict | None:
        """Read the latest state from FL Studio."""
        if self._use_file_fallback:
            return await asyncio.to_thread(_read_state_from_file)
        return None

    async def stop(self) -> None:
        """Close the pipe."""
        if self._handle is not None:
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None


# ---------------------------------------------------------------------------
# Bridge application
# ---------------------------------------------------------------------------


class BridgeState:
    """Shared state for the bridge server."""

    def __init__(self) -> None:
        self.pipe = NamedPipeServer()
        self.clients: list[WebSocket] = []
        self.daw_state: dict = {}
        self.pending_responses: dict[str, asyncio.Future] = {}
        self.config: DAWMindConfig = load_config()


bridge_state = BridgeState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage bridge server lifecycle."""
    logger.info("Starting DAWMind Bridge Server")
    await bridge_state.pipe.start()

    # Start background state polling
    poll_task = asyncio.create_task(_state_poll_loop())

    yield

    poll_task.cancel()
    await bridge_state.pipe.stop()
    logger.info("Bridge Server stopped")


app = FastAPI(title="DAWMind Bridge", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(
        {
            "status": "ok",
            "fl_studio_connected": bool(bridge_state.daw_state),
            "connected_clients": len(bridge_state.clients),
        }
    )


@app.get("/api/state")
async def get_state() -> JSONResponse:
    """Return the latest DAW state snapshot."""
    return JSONResponse(bridge_state.daw_state or {"error": "No state available"})


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

            await bridge_state.pipe.send_command(cmd)

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
            # Read state from IPC
            state = await bridge_state.pipe.read_state()
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
            responses = await bridge_state.pipe.read_responses()
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
