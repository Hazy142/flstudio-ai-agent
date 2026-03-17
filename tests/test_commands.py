"""Tests for command creation and parsing."""

from __future__ import annotations

import json

from dawmind.api_layer.commands import (
    channel_count,
    channel_get_name,
    channel_select,
    channel_set_volume,
    mixer_get_volume,
    mixer_mute_track,
    mixer_set_pan,
    mixer_set_volume,
    mixer_solo_track,
    plugin_get_name,
    plugin_get_param_value,
    plugin_set_param_value,
    state_full,
    transport_play,
    transport_set_tempo,
    transport_stop,
    vision_interact,
)
from dawmind.api_layer.protocol import (
    Command,
    CommandLayer,
    CommandResponse,
    CommandStatus,
    StateUpdate,
    create_command,
)


def test_command_creation():
    cmd = create_command("mixer", "setTrackVolume", track=5, volume=0.78)
    assert cmd.module == "mixer"
    assert cmd.action == "setTrackVolume"
    assert cmd.params == {"track": 5, "volume": 0.78}
    assert cmd.id.startswith("cmd_")


def test_command_json_line():
    cmd = Command(id="cmd_test", module="transport", action="play")
    line = cmd.to_json_line()
    assert line.endswith("\n")
    data = json.loads(line)
    assert data["id"] == "cmd_test"
    assert data["module"] == "transport"
    assert data["action"] == "play"


def test_command_response_from_json():
    raw = '{"id": "cmd_001", "status": "ok", "result": {"volume": 0.78}}'
    resp = CommandResponse.from_json(raw)
    assert resp.id == "cmd_001"
    assert resp.status == CommandStatus.OK
    assert resp.result["volume"] == 0.78


def test_command_response_error():
    raw = '{"id": "cmd_002", "status": "error", "error": "track not found"}'
    resp = CommandResponse.from_json(raw)
    assert resp.status == CommandStatus.ERROR
    assert resp.error == "track not found"


def test_state_update_from_json():
    raw = '{"type": "state", "data": {"transport": {"playing": true, "tempo": 140.0}}}'
    update = StateUpdate.from_json(raw)
    assert update.type == "state"
    assert update.data["transport"]["playing"] is True


# --- Transport commands ---


def test_transport_play():
    cmd = transport_play()
    assert cmd.module == "transport"
    assert cmd.action == "play"


def test_transport_stop():
    cmd = transport_stop()
    assert cmd.module == "transport"
    assert cmd.action == "stop"


def test_transport_set_tempo():
    cmd = transport_set_tempo(128.5)
    assert cmd.params == {"bpm": 128.5}


# --- Mixer commands ---


def test_mixer_set_volume():
    cmd = mixer_set_volume(5, 0.78)
    assert cmd.module == "mixer"
    assert cmd.action == "setTrackVolume"
    assert cmd.params == {"track": 5, "volume": 0.78}


def test_mixer_get_volume():
    cmd = mixer_get_volume(0)
    assert cmd.params == {"track": 0}


def test_mixer_set_pan():
    cmd = mixer_set_pan(3, -0.5)
    assert cmd.params == {"track": 3, "pan": -0.5}


def test_mixer_mute_track():
    cmd = mixer_mute_track(7)
    assert cmd.params == {"track": 7}


def test_mixer_solo_track():
    cmd = mixer_solo_track(2)
    assert cmd.params == {"track": 2}


# --- Channel commands ---


def test_channel_get_name():
    cmd = channel_get_name(0)
    assert cmd.module == "channels"
    assert cmd.params == {"index": 0}


def test_channel_set_volume():
    cmd = channel_set_volume(1, 0.65)
    assert cmd.params == {"index": 1, "volume": 0.65}


def test_channel_count():
    cmd = channel_count()
    assert cmd.action == "channelCount"


def test_channel_select():
    cmd = channel_select(3)
    assert cmd.params == {"index": 3}


# --- Plugin commands ---


def test_plugin_get_name():
    cmd = plugin_get_name(2)
    assert cmd.params == {"channel": 2}


def test_plugin_get_param_value():
    cmd = plugin_get_param_value(1, 5)
    assert cmd.params == {"channel": 1, "param_index": 5}


def test_plugin_set_param_value():
    cmd = plugin_set_param_value(1, 5, 0.42)
    assert cmd.params == {"channel": 1, "param_index": 5, "value": 0.42}


# --- State commands ---


def test_state_full():
    cmd = state_full()
    assert cmd.module == "state"
    assert cmd.action == "full"


# --- Vision commands ---


def test_vision_interact():
    cmd = vision_interact(
        description="Click cutoff knob",
        plugin_window="Serum",
        element_hint="cutoff knob, top-left",
        interaction_type="click",
    )
    assert cmd.layer == CommandLayer.VISION
    assert cmd.params["plugin_window"] == "Serum"
    assert cmd.params["interaction_type"] == "click"
