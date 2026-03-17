"""End-to-end integration tests.

Tests the full flow: WebSocket client -> Bridge Server -> File IPC -> Mock FL Studio -> response.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import websockets

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _recv_response(ws, timeout: float = 5.0) -> dict:
    """Receive from WS, skipping state broadcasts, until a command response arrives."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for command response")
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        msg = json.loads(raw)
        # State broadcasts have {"type": "state", "data": {...}} — skip them
        if msg.get("type") == "state":
            continue
        return msg


# ---------------------------------------------------------------------------
# Health / REST endpoint tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for the /health REST endpoint with a live mock FL Studio."""

    async def test_health_returns_ok(self, mock_fl_studio, bridge_server):
        host, port = bridge_server
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://{host}:{port}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_health_shows_connected_after_state_poll(self, mock_fl_studio, bridge_server):
        host, port = bridge_server
        # Wait for at least one state poll cycle
        await asyncio.sleep(0.2)
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://{host}:{port}/health")
        data = resp.json()
        assert data["fl_studio_connected"] is True


class TestStateEndpoint:
    """Tests for the /api/state REST endpoint."""

    async def test_state_available_after_poll(self, mock_fl_studio, bridge_server):
        host, port = bridge_server
        await asyncio.sleep(0.2)
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://{host}:{port}/api/state")
        data = resp.json()
        assert "transport" in data
        assert data["transport"]["tempo"] == 128.0  # basic_beat scenario

    async def test_state_empty_project(self, mock_fl_empty, bridge_server):
        host, port = bridge_server
        await asyncio.sleep(0.2)
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://{host}:{port}/api/state")
        data = resp.json()
        assert data["transport"]["playing"] is False
        assert data["channels"] == []


# ---------------------------------------------------------------------------
# Transport command tests
# ---------------------------------------------------------------------------


class TestTransportCommands:
    """End-to-end transport commands via WebSocket."""

    async def test_play(self, mock_fl_studio, ws_client):
        cmd = {"id": "e2e_play", "module": "transport", "action": "play", "params": {}}
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["id"] == "e2e_play"
        assert resp["status"] == "ok"
        assert resp["result"]["playing"] is True

    async def test_stop(self, mock_fl_studio, ws_client):
        cmd = {"id": "e2e_stop", "module": "transport", "action": "stop", "params": {}}
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["playing"] is False

    async def test_set_tempo(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_tempo",
            "module": "transport",
            "action": "setTempo",
            "params": {"bpm": 175.0},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["current"] == 175.0
        assert resp["result"]["previous"] == 128.0  # basic_beat default

    async def test_record_toggle(self, mock_fl_studio, ws_client):
        cmd = {"id": "e2e_rec", "module": "transport", "action": "record", "params": {}}
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["recording"] is True

        # Toggle again
        cmd["id"] = "e2e_rec2"
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["result"]["recording"] is False


# ---------------------------------------------------------------------------
# Mixer command tests
# ---------------------------------------------------------------------------


class TestMixerCommands:
    """End-to-end mixer commands via WebSocket."""

    async def test_get_volume(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_mvol",
            "module": "mixer",
            "action": "getTrackVolume",
            "params": {"track": 1},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["volume"] == 0.75  # Kick track in basic_beat

    async def test_set_volume(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_svol",
            "module": "mixer",
            "action": "setTrackVolume",
            "params": {"track": 1, "volume": 0.5},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["previous"] == 0.75
        assert resp["result"]["current"] == 0.5

    async def test_set_and_get_pan(self, mock_fl_studio, ws_client):
        # Set pan
        cmd = {
            "id": "e2e_span",
            "module": "mixer",
            "action": "setTrackPan",
            "params": {"track": 2, "pan": -0.3},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["current"] == -0.3

        # Get pan to verify
        cmd = {
            "id": "e2e_gpan",
            "module": "mixer",
            "action": "getTrackPan",
            "params": {"track": 2},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["result"]["pan"] == -0.3

    async def test_mute_track(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_mute",
            "module": "mixer",
            "action": "muteTrack",
            "params": {"track": 3},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["muted"] is True

    async def test_solo_track(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_solo",
            "module": "mixer",
            "action": "soloTrack",
            "params": {"track": 1},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["solo"] is True

    async def test_invalid_track(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_bad_track",
            "module": "mixer",
            "action": "getTrackVolume",
            "params": {"track": 999},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "error"
        assert "not found" in resp["error"]


# ---------------------------------------------------------------------------
# Channel command tests
# ---------------------------------------------------------------------------


class TestChannelCommands:
    """End-to-end channel commands via WebSocket."""

    async def test_channel_count(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_chcnt",
            "module": "channels",
            "action": "channelCount",
            "params": {},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["count"] == 3  # basic_beat has 3 channels

    async def test_get_channel_name(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_chname",
            "module": "channels",
            "action": "getChannelName",
            "params": {"index": 0},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["name"] == "Kick"

    async def test_set_channel_volume(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_chvol",
            "module": "channels",
            "action": "setChannelVolume",
            "params": {"index": 1, "volume": 0.5},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["previous"] == 0.78
        assert resp["result"]["current"] == 0.5

    async def test_select_channel(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_chsel",
            "module": "channels",
            "action": "selectChannel",
            "params": {"index": 2},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["selected"] == 2

    async def test_empty_project_channel_count(self, mock_fl_empty, ws_client):
        cmd = {
            "id": "e2e_empty_cnt",
            "module": "channels",
            "action": "channelCount",
            "params": {},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["result"]["count"] == 0


# ---------------------------------------------------------------------------
# Plugin command tests (full_mix scenario)
# ---------------------------------------------------------------------------


class TestPluginCommands:
    """End-to-end plugin commands using the full_mix scenario."""

    async def test_get_plugin_name(self, mock_fl_full_mix, ws_client):
        cmd = {
            "id": "e2e_pname",
            "module": "plugins",
            "action": "getPluginName",
            "params": {"channel": 4},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["name"] == "Serum"

    async def test_get_param_count(self, mock_fl_full_mix, ws_client):
        cmd = {
            "id": "e2e_pcnt",
            "module": "plugins",
            "action": "getParamCount",
            "params": {"channel": 4},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["count"] == 5

    async def test_get_param_name(self, mock_fl_full_mix, ws_client):
        cmd = {
            "id": "e2e_pn",
            "module": "plugins",
            "action": "getParamName",
            "params": {"channel": 4, "param_index": 2},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["name"] == "Filter Cutoff"

    async def test_get_and_set_param_value(self, mock_fl_full_mix, ws_client):
        # Get current value
        cmd = {
            "id": "e2e_gpv",
            "module": "plugins",
            "action": "getParamValue",
            "params": {"channel": 4, "param_index": 2},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["result"]["value"] == 0.65

        # Set new value
        cmd = {
            "id": "e2e_spv",
            "module": "plugins",
            "action": "setParamValue",
            "params": {"channel": 4, "param_index": 2, "value": 0.9},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        assert resp["result"]["previous"] == 0.65
        assert resp["result"]["current"] == 0.9


# ---------------------------------------------------------------------------
# State command tests
# ---------------------------------------------------------------------------


class TestStateCommands:
    """End-to-end state retrieval commands."""

    async def test_full_state(self, mock_fl_studio, ws_client):
        cmd = {"id": "e2e_state", "module": "state", "action": "full", "params": {}}
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "ok"
        state = resp["result"]
        assert "transport" in state
        assert "mixer_tracks" in state
        assert "channels" in state
        assert state["transport"]["tempo"] == 128.0

    async def test_full_state_full_mix(self, mock_fl_full_mix, ws_client):
        cmd = {"id": "e2e_state_fm", "module": "state", "action": "full", "params": {}}
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        state = resp["result"]
        assert state["transport"]["playing"] is True
        assert state["transport"]["tempo"] == 150.0
        assert len(state["channels"]) == 8
        assert "Serum" in state["plugins"]


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error conditions in the full pipeline."""

    async def test_unknown_command(self, mock_fl_studio, ws_client):
        cmd = {
            "id": "e2e_unknown",
            "module": "nonexistent",
            "action": "bogus",
            "params": {},
        }
        await ws_client.send(json.dumps(cmd))
        resp = await _recv_response(ws_client)
        assert resp["status"] == "error"
        assert "Unknown command" in resp["error"]

    async def test_invalid_json(self, mock_fl_studio, bridge_server):
        host, port = bridge_server
        uri = f"ws://{host}:{port}/ws"
        async with websockets.connect(uri) as ws:
            await ws.send("this is not json")
            resp = await _recv_response(ws)
            assert resp["status"] == "error"


# ---------------------------------------------------------------------------
# Multi-command sequence tests
# ---------------------------------------------------------------------------


class TestMultiCommandSequence:
    """Tests that chain multiple commands in sequence."""

    async def test_play_set_tempo_stop(self, mock_fl_studio, ws_client):
        """Simulate a typical workflow: play -> change tempo -> stop."""
        # Play
        await ws_client.send(
            json.dumps({"id": "seq_1", "module": "transport", "action": "play", "params": {}})
        )
        resp = await _recv_response(ws_client)
        assert resp["result"]["playing"] is True

        # Set tempo
        await ws_client.send(
            json.dumps(
                {
                    "id": "seq_2",
                    "module": "transport",
                    "action": "setTempo",
                    "params": {"bpm": 160.0},
                }
            )
        )
        resp = await _recv_response(ws_client)
        assert resp["result"]["current"] == 160.0

        # Stop
        await ws_client.send(
            json.dumps({"id": "seq_3", "module": "transport", "action": "stop", "params": {}})
        )
        resp = await _recv_response(ws_client)
        assert resp["result"]["playing"] is False

    async def test_mixer_workflow(self, mock_fl_studio, ws_client):
        """Set volume, mute, then verify state persists."""
        # Set volume on track 1
        await ws_client.send(
            json.dumps(
                {
                    "id": "mw_1",
                    "module": "mixer",
                    "action": "setTrackVolume",
                    "params": {"track": 1, "volume": 0.6},
                }
            )
        )
        resp = await _recv_response(ws_client)
        assert resp["result"]["current"] == 0.6

        # Mute track 1
        await ws_client.send(
            json.dumps(
                {"id": "mw_2", "module": "mixer", "action": "muteTrack", "params": {"track": 1}}
            )
        )
        resp = await _recv_response(ws_client)
        assert resp["result"]["muted"] is True

        # Read back volume — should still be 0.6 even though muted
        await ws_client.send(
            json.dumps(
                {
                    "id": "mw_3",
                    "module": "mixer",
                    "action": "getTrackVolume",
                    "params": {"track": 1},
                }
            )
        )
        resp = await _recv_response(ws_client)
        assert resp["result"]["volume"] == 0.6


# ---------------------------------------------------------------------------
# State broadcast tests
# ---------------------------------------------------------------------------


class TestStateBroadcast:
    """Verify that state updates are broadcast to WebSocket clients."""

    async def test_receives_state_broadcast(self, mock_fl_studio, bridge_server):
        """A connected WS client should receive periodic state broadcasts."""
        host, port = bridge_server
        uri = f"ws://{host}:{port}/ws"
        async with websockets.connect(uri) as ws:
            # Wait for a state broadcast (the poll loop sends these)
            raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
            msg = json.loads(raw)
            assert msg["type"] == "state"
            assert "transport" in msg["data"]

    async def test_state_reflects_command_changes(self, mock_fl_studio, bridge_server):
        """After a command mutates state, the next broadcast should reflect it."""
        host, port = bridge_server
        uri = f"ws://{host}:{port}/ws"
        async with websockets.connect(uri) as ws:
            # Send a tempo change
            cmd = {
                "id": "bc_tempo",
                "module": "transport",
                "action": "setTempo",
                "params": {"bpm": 200.0},
            }
            await ws.send(json.dumps(cmd))

            # Consume messages until we get a state broadcast with the new tempo
            found = False
            for _ in range(20):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                msg = json.loads(raw)
                if msg.get("type") == "state":
                    if msg["data"]["transport"]["tempo"] == 200.0:
                        found = True
                        break
            assert found, "State broadcast did not reflect tempo change"
