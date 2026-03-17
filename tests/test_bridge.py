"""Tests for bridge server WebSocket functionality."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from dawmind.api_layer.bridge_server import app, bridge_state


@pytest.fixture(autouse=True)
def _reset_bridge_state():
    """Reset bridge state between tests."""
    bridge_state.daw_state = {}
    bridge_state.clients = []
    bridge_state.pending_responses = {}
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
