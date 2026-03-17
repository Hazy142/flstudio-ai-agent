"""Tests for the central tool registry."""

from __future__ import annotations

import pytest

from dawmind.api_layer.protocol import Command, CommandLayer
from dawmind.tools import (
    ALL_TOOLS,
    STATE_TOOLS,
    _CHANNEL_NAMES,
    _MIXER_NAMES,
    _PLUGIN_NAMES,
    _TRANSPORT_NAMES,
    _VISION_NAMES,
    execute_tool,
    is_vision_tool,
)
from dawmind.tools.channel_tools import CHANNEL_TOOLS
from dawmind.tools.mixer_tools import MIXER_TOOLS
from dawmind.tools.plugin_tools import PLUGIN_TOOLS
from dawmind.tools.transport_tools import TRANSPORT_TOOLS
from dawmind.tools.vision_tools import VISION_TOOLS


# ---------------------------------------------------------------------------
# ALL_TOOLS composition
# ---------------------------------------------------------------------------


def test_all_tools_count():
    """ALL_TOOLS should contain all tools from every category."""
    expected = (
        len(STATE_TOOLS)
        + len(TRANSPORT_TOOLS)
        + len(MIXER_TOOLS)
        + len(CHANNEL_TOOLS)
        + len(PLUGIN_TOOLS)
        + len(VISION_TOOLS)
    )
    assert len(ALL_TOOLS) == expected


def test_all_tools_no_duplicates():
    """Tool names must be unique across all categories."""
    names = [t["name"] for t in ALL_TOOLS]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Tool schema validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t["name"] for t in ALL_TOOLS])
def test_tool_has_required_fields(tool):
    """Every tool must have name, description, and input_schema."""
    assert "name" in tool
    assert "description" in tool
    assert "input_schema" in tool
    assert isinstance(tool["name"], str) and tool["name"]
    assert isinstance(tool["description"], str) and tool["description"]


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=[t["name"] for t in ALL_TOOLS])
def test_tool_schema_is_valid_json_schema(tool):
    """input_schema should be a dict with 'type' = 'object' and 'properties'."""
    schema = tool["input_schema"]
    assert isinstance(schema, dict)
    assert schema.get("type") == "object"
    assert "properties" in schema
    assert isinstance(schema["properties"], dict)
    assert "required" in schema
    assert isinstance(schema["required"], list)


# ---------------------------------------------------------------------------
# Tool name sets
# ---------------------------------------------------------------------------


def test_transport_name_set():
    expected = {"transport_play", "transport_stop", "transport_record", "transport_set_tempo"}
    assert _TRANSPORT_NAMES == expected


def test_mixer_name_set():
    expected = {
        "mixer_get_volume",
        "mixer_set_volume",
        "mixer_get_pan",
        "mixer_set_pan",
        "mixer_mute_track",
        "mixer_solo_track",
    }
    assert _MIXER_NAMES == expected


def test_channel_name_set():
    expected = {"channel_get_name", "channel_set_volume", "channel_count", "channel_select"}
    assert _CHANNEL_NAMES == expected


def test_plugin_name_set():
    expected = {
        "plugin_get_name",
        "plugin_get_param_count",
        "plugin_get_param_name",
        "plugin_get_param_value",
        "plugin_set_param_value",
    }
    assert _PLUGIN_NAMES == expected


def test_vision_name_set():
    expected = {
        "vision_click_element",
        "vision_drag_knob",
        "vision_read_display",
        "vision_screenshot",
    }
    assert _VISION_NAMES == expected


# ---------------------------------------------------------------------------
# is_vision_tool
# ---------------------------------------------------------------------------


def test_is_vision_tool_true():
    assert is_vision_tool("vision_click_element") is True
    assert is_vision_tool("vision_drag_knob") is True
    assert is_vision_tool("vision_read_display") is True
    assert is_vision_tool("vision_screenshot") is True


def test_is_vision_tool_false():
    assert is_vision_tool("transport_play") is False
    assert is_vision_tool("mixer_set_volume") is False
    assert is_vision_tool("get_daw_state") is False
    assert is_vision_tool("nonexistent") is False


# ---------------------------------------------------------------------------
# execute_tool – routing
# ---------------------------------------------------------------------------


def test_execute_tool_state():
    """get_daw_state should route to state_full()."""
    cmd = execute_tool("get_daw_state", {})
    assert isinstance(cmd, Command)
    assert cmd.module == "state"
    assert cmd.action == "full"


def test_execute_tool_transport_play():
    cmd = execute_tool("transport_play", {})
    assert cmd.module == "transport"
    assert cmd.action == "play"


def test_execute_tool_transport_stop():
    cmd = execute_tool("transport_stop", {})
    assert cmd.action == "stop"


def test_execute_tool_transport_set_tempo():
    cmd = execute_tool("transport_set_tempo", {"bpm": 120.0})
    assert cmd.params == {"bpm": 120.0}


def test_execute_tool_mixer_set_volume():
    cmd = execute_tool("mixer_set_volume", {"track": 5, "volume": 0.78})
    assert cmd.module == "mixer"
    assert cmd.params["track"] == 5
    assert cmd.params["volume"] == 0.78


def test_execute_tool_mixer_get_volume():
    cmd = execute_tool("mixer_get_volume", {"track": 0})
    assert cmd.module == "mixer"
    assert cmd.params["track"] == 0


def test_execute_tool_mixer_set_pan():
    cmd = execute_tool("mixer_set_pan", {"track": 3, "pan": -0.5})
    assert cmd.params["pan"] == -0.5


def test_execute_tool_mixer_mute_track():
    cmd = execute_tool("mixer_mute_track", {"track": 7})
    assert cmd.params["track"] == 7


def test_execute_tool_mixer_solo_track():
    cmd = execute_tool("mixer_solo_track", {"track": 2})
    assert cmd.params["track"] == 2


def test_execute_tool_channel_get_name():
    cmd = execute_tool("channel_get_name", {"index": 0})
    assert cmd.module == "channels"
    assert cmd.params["index"] == 0


def test_execute_tool_channel_set_volume():
    cmd = execute_tool("channel_set_volume", {"index": 1, "volume": 0.65})
    assert cmd.params["volume"] == 0.65


def test_execute_tool_channel_count():
    cmd = execute_tool("channel_count", {})
    assert cmd.action == "channelCount"


def test_execute_tool_channel_select():
    cmd = execute_tool("channel_select", {"index": 3})
    assert cmd.params["index"] == 3


def test_execute_tool_plugin_get_name():
    cmd = execute_tool("plugin_get_name", {"channel": 2})
    assert cmd.module == "plugins"
    assert cmd.params["channel"] == 2


def test_execute_tool_plugin_get_param_count():
    cmd = execute_tool("plugin_get_param_count", {"channel": 0})
    assert cmd.params["channel"] == 0


def test_execute_tool_plugin_get_param_name():
    cmd = execute_tool("plugin_get_param_name", {"channel": 1, "param_index": 5})
    assert cmd.params["param_index"] == 5


def test_execute_tool_plugin_get_param_value():
    cmd = execute_tool("plugin_get_param_value", {"channel": 1, "param_index": 3})
    assert cmd.params["param_index"] == 3


def test_execute_tool_plugin_set_param_value():
    cmd = execute_tool("plugin_set_param_value", {"channel": 1, "param_index": 5, "value": 0.42})
    assert cmd.params["value"] == 0.42


def test_execute_tool_vision_click_element():
    cmd = execute_tool(
        "vision_click_element",
        {"plugin_window": "Serum", "element_description": "cutoff knob"},
    )
    assert cmd.layer == CommandLayer.VISION
    assert cmd.params["interaction_type"] == "click"
    assert cmd.params["plugin_window"] == "Serum"


def test_execute_tool_vision_drag_knob():
    cmd = execute_tool(
        "vision_drag_knob",
        {
            "plugin_window": "Vital",
            "knob_description": "resonance knob",
            "direction": "up",
            "amount": 30,
        },
    )
    assert cmd.layer == CommandLayer.VISION
    assert cmd.params["interaction_type"] == "drag_vertical"


def test_execute_tool_vision_read_display():
    cmd = execute_tool(
        "vision_read_display",
        {"plugin_window": "Serum", "display_description": "preset name"},
    )
    assert cmd.params["interaction_type"] == "read"


def test_execute_tool_vision_screenshot():
    cmd = execute_tool("vision_screenshot", {"target": "fl_studio"})
    assert cmd.params["interaction_type"] == "screenshot"


# ---------------------------------------------------------------------------
# execute_tool – error handling
# ---------------------------------------------------------------------------


def test_execute_tool_unknown_raises():
    """Unknown tool name should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown tool"):
        execute_tool("nonexistent_tool", {})


def test_execute_tool_empty_name_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        execute_tool("", {})
