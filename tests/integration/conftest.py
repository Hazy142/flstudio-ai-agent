"""Shared fixtures for integration tests.

Provides:
- ``mock_fl_studio`` — starts/stops the mock FL Studio IPC process
- ``bridge_server`` — starts/stops the bridge server on a random port
- ``ws_client`` — a connected WebSocket client to the bridge
"""

from __future__ import annotations

import asyncio
import os

import pytest
import websockets

from tests.integration.mock_fl_studio import MockFLStudio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Return an available TCP port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def ipc_dir(tmp_path):
    """Create a temporary IPC directory shared by mock and bridge."""
    ipc = str(tmp_path / "dawmind_ipc")
    os.makedirs(ipc, exist_ok=True)
    yield ipc
    # Cleanup handled by tmp_path


@pytest.fixture()
async def mock_fl_studio(ipc_dir):
    """Start and stop a MockFLStudio instance using the shared IPC dir."""
    mock = MockFLStudio(ipc_dir=ipc_dir, scenario="basic_beat")
    await mock.start()
    # Give the mock a moment to write initial state
    await asyncio.sleep(0.1)
    yield mock
    await mock.stop()


@pytest.fixture()
async def mock_fl_full_mix(ipc_dir):
    """MockFLStudio with the full_mix scenario (for plugin/effect tests)."""
    mock = MockFLStudio(ipc_dir=ipc_dir, scenario="full_mix")
    await mock.start()
    await asyncio.sleep(0.1)
    yield mock
    await mock.stop()


@pytest.fixture()
async def mock_fl_empty(ipc_dir):
    """MockFLStudio with the empty_project scenario."""
    mock = MockFLStudio(ipc_dir=ipc_dir, scenario="empty_project")
    await mock.start()
    await asyncio.sleep(0.1)
    yield mock
    await mock.stop()


@pytest.fixture()
async def bridge_server(ipc_dir):
    """Start the bridge server on a random port, pointed at the test IPC dir.

    Yields ``(host, port)`` tuple.  Patches the module-level ``_IPC_DIR`` in
    ``bridge_server`` so file-based IPC reads/writes go to our temp directory.
    """
    import dawmind.api_layer.bridge_server as bs_module

    # Save originals to restore later
    original_ipc_dir = bs_module._IPC_DIR
    original_bridge_state = bs_module.bridge_state

    # Patch the IPC directory
    bs_module._IPC_DIR = ipc_dir

    # Reset global bridge state to avoid leaking between tests
    bs_module.bridge_state = bs_module.BridgeState()
    # Also patch the pipe to use our IPC dir
    bs_module.bridge_state.pipe._use_file_fallback = True

    host = "127.0.0.1"
    port = _free_port()

    # Patch config to use our port and a fast poll interval
    bs_module.bridge_state.config.server.ws_port = port
    bs_module.bridge_state.config.server.host = host
    bs_module.bridge_state.config.fl_studio.state_poll_interval_ms = 50

    import uvicorn

    config = uvicorn.Config(bs_module.app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    task = asyncio.create_task(server.serve())
    # Wait for the server to be ready
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:
        raise RuntimeError("Bridge server did not start in time")

    yield host, port

    server.should_exit = True
    await task
    # Restore originals to avoid leaking into unit tests
    bs_module._IPC_DIR = original_ipc_dir
    bs_module.bridge_state = original_bridge_state


@pytest.fixture()
async def ws_client(bridge_server):
    """Provide a connected WebSocket client to the bridge server."""
    host, port = bridge_server
    uri = f"ws://{host}:{port}/ws"
    async with websockets.connect(uri) as ws:
        yield ws
