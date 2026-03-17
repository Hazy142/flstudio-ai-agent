"""Central tool registry for the DAWMind agent.

Collects all tool definitions from every module and provides a unified
execution entry point for the orchestrator's agentic loop.
"""

from __future__ import annotations

import logging

from dawmind.api_layer.commands import state_full
from dawmind.api_layer.protocol import Command
from dawmind.tools.channel_tools import CHANNEL_TOOLS
from dawmind.tools.channel_tools import execute as channel_execute
from dawmind.tools.mixer_tools import MIXER_TOOLS
from dawmind.tools.mixer_tools import execute as mixer_execute
from dawmind.tools.plugin_tools import PLUGIN_TOOLS
from dawmind.tools.plugin_tools import execute as plugin_execute
from dawmind.tools.transport_tools import TRANSPORT_TOOLS
from dawmind.tools.transport_tools import execute as transport_execute
from dawmind.tools.vision_tools import VISION_TOOLS
from dawmind.tools.vision_tools import execute as vision_execute

logger = logging.getLogger(__name__)

# Tool that requests the complete DAW state snapshot
STATE_TOOLS: list[dict] = [
    {
        "name": "get_daw_state",
        "description": (
            "Get the complete current state of FL Studio including transport "
            "(playing/stopped, tempo), all mixer tracks (volumes, pans, mutes, "
            "solos, effects), all channels in the channel rack, and loaded plugins. "
            "Call this before making changes so you know the current project state."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# Every tool across all modules, in a single flat list
ALL_TOOLS: list[dict] = (
    STATE_TOOLS + TRANSPORT_TOOLS + MIXER_TOOLS + CHANNEL_TOOLS + PLUGIN_TOOLS + VISION_TOOLS
)

# Lookup sets for routing tool calls to the correct module executor
_TRANSPORT_NAMES = {t["name"] for t in TRANSPORT_TOOLS}
_MIXER_NAMES = {t["name"] for t in MIXER_TOOLS}
_CHANNEL_NAMES = {t["name"] for t in CHANNEL_TOOLS}
_PLUGIN_NAMES = {t["name"] for t in PLUGIN_TOOLS}
_VISION_NAMES = {t["name"] for t in VISION_TOOLS}


def is_vision_tool(tool_name: str) -> bool:
    """Return True if the tool is a vision-layer tool (executes locally)."""
    return tool_name in _VISION_NAMES


def execute_tool(tool_name: str, params: dict) -> Command:
    """Route a tool call to the correct module and return a Command.

    Raises:
        ValueError: If the tool name is not recognised.
    """
    if tool_name == "get_daw_state":
        return state_full()

    if tool_name in _TRANSPORT_NAMES:
        return transport_execute(tool_name, params)
    if tool_name in _MIXER_NAMES:
        return mixer_execute(tool_name, params)
    if tool_name in _CHANNEL_NAMES:
        return channel_execute(tool_name, params)
    if tool_name in _PLUGIN_NAMES:
        return plugin_execute(tool_name, params)
    if tool_name in _VISION_NAMES:
        return vision_execute(tool_name, params)

    raise ValueError(f"Unknown tool: {tool_name}")
