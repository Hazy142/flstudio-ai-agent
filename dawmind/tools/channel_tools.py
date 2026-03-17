"""Channel rack tools for Claude tool-use."""

from __future__ import annotations

from dawmind.api_layer.commands import (
    channel_count,
    channel_get_name,
    channel_select,
    channel_set_volume,
)
from dawmind.api_layer.protocol import Command

CHANNEL_TOOLS = [
    {
        "name": "channel_get_name",
        "description": "Get the name of a channel in the channel rack.",
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "Channel index (0-based).",
                    "minimum": 0,
                }
            },
            "required": ["index"],
        },
    },
    {
        "name": "channel_set_volume",
        "description": "Set the volume of a channel in the channel rack (0.0 to 1.0).",
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "Channel index (0-based).",
                    "minimum": 0,
                },
                "volume": {
                    "type": "number",
                    "description": "Volume level (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
            },
            "required": ["index", "volume"],
        },
    },
    {
        "name": "channel_count",
        "description": "Get the total number of channels in the channel rack.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "channel_select",
        "description": "Select a channel in the channel rack (deselects all others).",
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "Channel index to select (0-based).",
                    "minimum": 0,
                }
            },
            "required": ["index"],
        },
    },
]


def execute(tool_name: str, params: dict) -> Command:
    """Create the FL Studio command for a channel tool call."""
    match tool_name:
        case "channel_get_name":
            return channel_get_name(params["index"])
        case "channel_set_volume":
            return channel_set_volume(params["index"], params["volume"])
        case "channel_count":
            return channel_count()
        case "channel_select":
            return channel_select(params["index"])
        case _:
            raise ValueError(f"Unknown channel tool: {tool_name}")
