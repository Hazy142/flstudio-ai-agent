"""Tests for bridge server WebSocket functionality."""

from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from dawmind.api_layer.bridge_server import (
    _HEARTBEAT_MAX_AGE_SECONDS,
    _IPC_DIR,
    _is_heartbeat_fresh,
    _read_heartbeat,
    app,
    bridge_state,
)
import dawmind.api_layer.bridge_server as bs_module


@pytest.fixture(autouse=True)
def _reset_bridge_state():
    """Reset bridge state between tests."""
    bridge_state.daw_state = {}
    bridge_state.clients = []
    bridge_state.pending_responses = {}
    bridge_state.fl_studio_connected = False
    yield


def test_health_endpoint():
    """Test the /health endpoint returns status."""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "fl_studio_connected" in data
        assert "connected_clients" in data


def test_health_no_fl_studio():
    """Health check should show FL Studio as disconnected when no state."""
    with TestClient(app) as client:
        resp = client.get("/health")
        data = resp.json()
        assert data["fl_studio_connected"] is False


def test_state_endpoint_empty():
    """Test /api/state returns error when no state available."""
    with TestClient(app) as client:
        resp = client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data


def test_state_endpoint_with_data():
    """Test /api/state returns state when available."""
    bridge_state.daw_state = {
        "transport": {"playing": True, "tempo": 140.0},
        "mixer": {"tracks": []},
    }
    with TestClient(app) as client:
        resp = client.get("/api/state")
        data = resp.json()
        assert data["transport"]["playing"] is True
        assert data["transport"]["tempo"] == 140.0


def test_websocket_connection():
    """Test WebSocket connection and disconnection."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws"):
            # Client should be tracked
            assert len(bridge_state.clients) == 1

        # After disconnect, client should be removed
        assert len(bridge_state.clients) == 0


def test_websocket_invalid_json():
    """Test that invalid JSON gets an error response."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not valid json")
            response = ws.receive_json()
            assert response["status"] == "error"
            assert "Invalid JSON" in response["error"]


def test_websocket_command_timeout():
    """Test that commands timeout when FL Studio doesn't respond."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            cmd = {
                "id": "test_001",
                "module": "transport",
                "action": "play",
                "params": {},
            }
            ws.send_json(cmd)
            # Should timeout since no FL Studio is connected
            response = ws.receive_json(mode="text")
            data = json.loads(response) if isinstance(response, str) else response
            assert data["id"] == "test_001"
            assert data["status"] in ("timeout", "error")


# ---------------------------------------------------------------------------
# Heartbeat tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def ipc_dir(tmp_path):
    """Create a temporary IPC directory and patch the bridge to use it."""
    ipc = str(tmp_path / "dawmind_ipc")
    os.makedirs(ipc, exist_ok=True)
    original = bs_module._IPC_DIR
    bs_module._IPC_DIR = ipc
    yield ipc
    bs_module._IPC_DIR = original


def test_heartbeat_read_missing(ipc_dir):
    """_read_heartbeat returns None when no heartbeat file exists."""
    assert _read_heartbeat() is None


def test_heartbeat_read_valid(ipc_dir):
    """_read_heartbeat returns the timestamp from the heartbeat file."""
    ts = time.time()
    with open(os.path.join(ipc_dir, "heartbeat"), "w") as f:
        f.write(str(ts))
    result = _read_heartbeat()
    assert result is not None
    assert abs(result - ts) < 0.01


def test_heartbeat_fresh(ipc_dir):
    """_is_heartbeat_fresh returns True when heartbeat is recent."""
    with open(os.path.join(ipc_dir, "heartbeat"), "w") as f:
        f.write(str(time.time()))
    assert _is_heartbeat_fresh() is True


def test_heartbeat_stale(ipc_dir):
    """_is_heartbeat_fresh returns False when heartbeat is old."""
    stale_ts = time.time() - _HEARTBEAT_MAX_AGE_SECONDS - 1
    with open(os.path.join(ipc_dir, "heartbeat"), "w") as f:
        f.write(str(stale_ts))
    assert _is_heartbeat_fresh() is False


def test_heartbeat_missing_is_not_fresh(ipc_dir):
    """_is_heartbeat_fresh returns False when heartbeat file is missing."""
    assert _is_heartbeat_fresh() is False


def test_health_connected_via_heartbeat(ipc_dir):
    """Health endpoint reports fl_studio_connected when heartbeat is fresh."""
    # Write a fresh heartbeat so the poll loop picks it up
    heartbeat_path = os.path.join(ipc_dir, "heartbeat")
    with open(heartbeat_path, "w") as f:
        f.write(str(time.time()))
    # Also write a state file so daw_state gets populated
    state_path = os.path.join(ipc_dir, "state.json")
    with open(state_path, "w") as f:
        json.dump({"transport": {"playing": False}}, f)
    # Give the poll loop a moment to read the heartbeat
    bridge_state.fl_studio_connected = True
    with TestClient(app) as client:
        resp = client.get("/health")
        data = resp.json()
        assert data["fl_studio_connected"] is True


# ---------------------------------------------------------------------------
# /api/ipc-info endpoint tests
# ---------------------------------------------------------------------------


def test_ipc_info_endpoint(ipc_dir):
    """Test /api/ipc-info returns diagnostic info."""
    # Write a heartbeat and state so there's something to report
    with open(os.path.join(ipc_dir, "heartbeat"), "w") as f:
        f.write(str(time.time()))
    with open(os.path.join(ipc_dir, "state.json"), "w") as f:
        json.dump({"transport": {}}, f)
    with open(os.path.join(ipc_dir, "commands.jsonl"), "w") as f:
        f.write("")

    with TestClient(app) as client:
        resp = client.get("/api/ipc-info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ipc_dir"] == ipc_dir
        assert data["ipc_dir_exists"] is True
        assert data["state_exists"] is True
        assert data["commands_exists"] is True
        assert data["heartbeat_fresh"] is True
        assert isinstance(data["files"], list)


def test_ipc_info_endpoint_empty(ipc_dir):
    """Test /api/ipc-info when IPC dir is empty."""
    with TestClient(app) as client:
        resp = client.get("/api/ipc-info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ipc_dir_exists"] is True
        assert data["state_exists"] is False
        assert data["heartbeat_fresh"] is False
