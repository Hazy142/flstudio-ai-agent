"""Plugin control tools for Claude tool-use."""

from __future__ import annotations

from dawmind.api_layer.commands import (
    plugin_get_name,
    plugin_get_param_count,
    plugin_get_param_name,
    plugin_get_param_value,
    plugin_set_param_value,
)
from dawmind.api_layer.protocol import Command

PLUGIN_TOOLS = [
    {
        "name": "plugin_get_name",
        "description": "Get the name of the plugin loaded on a channel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "integer",
                    "description": "Channel index where the plugin is loaded.",
                    "minimum": 0,
                }
            },
            "required": ["channel"],
        },
    },
    {
        "name": "plugin_get_param_count",
        "description": "Get the number of automatable parameters for a plugin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "integer",
                    "description": "Channel index.",
                    "minimum": 0,
                }
            },
            "required": ["channel"],
        },
    },
    {
        "name": "plugin_get_param_name",
        "description": "Get the name of a specific plugin parameter by index.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "integer",
                    "description": "Channel index.",
                    "minimum": 0,
                },
                "param_index": {
                    "type": "integer",
                    "description": "Parameter index (0-based).",
                    "minimum": 0,
                },
            },
            "required": ["channel", "param_index"],
        },
    },
    {
        "name": "plugin_get_param_value",
        "description": "Get the current value of a plugin parameter (0.0 to 1.0).",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "integer",
                    "description": "Channel index.",
                    "minimum": 0,
                },
                "param_index": {
                    "type": "integer",
                    "description": "Parameter index.",
                    "minimum": 0,
                },
            },
            "required": ["channel", "param_index"],
        },
    },
    {
        "name": "plugin_set_param_value",
        "description": "Set the value of a plugin parameter. Value range is 0.0 to 1.0.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "integer",
                    "description": "Channel index.",
                    "minimum": 0,
                },
                "param_index": {
                    "type": "integer",
                    "description": "Parameter index.",
                    "minimum": 0,
                },
                "value": {
                    "type": "number",
                    "description": "Parameter value (0.0 to 1.0).",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
            },
            "required": ["channel", "param_index", "value"],
        },
    },
]


def execute(tool_name: str, params: dict) -> Command:
    """Create the FL Studio command for a plugin tool call."""
    match tool_name:
        case "plugin_get_name":
            return plugin_get_name(params["channel"])
        case "plugin_get_param_count":
            return plugin_get_param_count(params["channel"])
        case "plugin_get_param_name":
            return plugin_get_param_name(params["channel"], params["param_index"])
        case "plugin_get_param_value":
            return plugin_get_param_value(params["channel"], params["param_index"])
        case "plugin_set_param_value":
            return plugin_set_param_value(
                params["channel"], params["param_index"], params["value"]
            )
        case _:
            raise ValueError(f"Unknown plugin tool: {tool_name}")
