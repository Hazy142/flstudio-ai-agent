"""Mixer control tools for Claude tool-use."""

from __future__ import annotations

from dawmind.api_layer.commands import (
    mixer_get_pan,
    mixer_get_volume,
    mixer_mute_track,
    mixer_set_pan,
    mixer_set_volume,
    mixer_solo_track,
)
from dawmind.api_layer.protocol import Command

MIXER_TOOLS = [
    {
        "name": "mixer_get_volume",
        "description": "Get the current volume of a mixer track (0.0 to 1.0).",
        "input_schema": {
            "type": "object",
            "properties": {
                "track": {
                    "type": "integer",
                    "description": "Mixer track index (0 = master, 1-125 = insert tracks).",
                    "minimum": 0,
                    "maximum": 125,
                }
            },
            "required": ["track"],
        },
    },
    {
        "name": "mixer_set_volume",
        "description": (
            "Set the volume of a mixer track. 0.0 = silence, 0.8 = ~0dB, 1.0 = ~5.6dB."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "track": {
                    "type": "integer",
                    "description": "Mixer track index (0 = master, 1-125 = insert tracks).",
                    "minimum": 0,
                    "maximum": 125,
                },
                "volume": {
                    "type": "number",
                    "description": "Volume level (0.0 to 1.0). 0.8 ≈ 0dB.",
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
            },
            "required": ["track", "volume"],
        },
    },
    {
        "name": "mixer_get_pan",
        "description": "Get the pan position of a mixer track (-1.0 left to 1.0 right).",
        "input_schema": {
            "type": "object",
            "properties": {
                "track": {
                    "type": "integer",
                    "description": "Mixer track index.",
                    "minimum": 0,
                    "maximum": 125,
                }
            },
            "required": ["track"],
        },
    },
    {
        "name": "mixer_set_pan",
        "description": (
            "Set the pan position of a mixer track "
            "(-1.0 = full left, 0.0 = center, 1.0 = full right)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "track": {
                    "type": "integer",
                    "description": "Mixer track index.",
                    "minimum": 0,
                    "maximum": 125,
                },
                "pan": {
                    "type": "number",
                    "description": "Pan position (-1.0 to 1.0).",
                    "minimum": -1.0,
                    "maximum": 1.0,
                },
            },
            "required": ["track", "pan"],
        },
    },
    {
        "name": "mixer_mute_track",
        "description": "Toggle mute on a mixer track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "track": {
                    "type": "integer",
                    "description": "Mixer track index to mute/unmute.",
                    "minimum": 0,
                    "maximum": 125,
                }
            },
            "required": ["track"],
        },
    },
    {
        "name": "mixer_solo_track",
        "description": "Toggle solo on a mixer track (mutes all other tracks).",
        "input_schema": {
            "type": "object",
            "properties": {
                "track": {
                    "type": "integer",
                    "description": "Mixer track index to solo.",
                    "minimum": 0,
                    "maximum": 125,
                }
            },
            "required": ["track"],
        },
    },
]


def execute(tool_name: str, params: dict) -> Command:
    """Create the FL Studio command for a mixer tool call."""
    match tool_name:
        case "mixer_get_volume":
            return mixer_get_volume(params["track"])
        case "mixer_set_volume":
            return mixer_set_volume(params["track"], params["volume"])
        case "mixer_get_pan":
            return mixer_get_pan(params["track"])
        case "mixer_set_pan":
            return mixer_set_pan(params["track"], params["pan"])
        case "mixer_mute_track":
            return mixer_mute_track(params["track"])
        case "mixer_solo_track":
            return mixer_solo_track(params["track"])
        case _:
            raise ValueError(f"Unknown mixer tool: {tool_name}")
