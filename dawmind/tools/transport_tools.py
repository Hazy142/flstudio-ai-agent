"""Transport control tools for Claude tool-use."""

from __future__ import annotations

from dawmind.api_layer.commands import (
    transport_play,
    transport_record,
    transport_set_tempo,
    transport_stop,
)
from dawmind.api_layer.protocol import Command

TRANSPORT_TOOLS = [
    {
        "name": "transport_play",
        "description": "Start playback in FL Studio. Toggles play/pause.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "transport_stop",
        "description": "Stop playback in FL Studio and return to the beginning.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "transport_record",
        "description": "Toggle recording mode in FL Studio.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "transport_set_tempo",
        "description": "Set the project tempo (BPM) in FL Studio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bpm": {
                    "type": "number",
                    "description": "Tempo in beats per minute (e.g. 120.0, 140.5).",
                    "minimum": 10,
                    "maximum": 522,
                }
            },
            "required": ["bpm"],
        },
    },
]


def execute(tool_name: str, params: dict) -> Command:
    """Create the FL Studio command for a transport tool call."""
    match tool_name:
        case "transport_play":
            return transport_play()
        case "transport_stop":
            return transport_stop()
        case "transport_record":
            return transport_record()
        case "transport_set_tempo":
            return transport_set_tempo(params["bpm"])
        case _:
            raise ValueError(f"Unknown transport tool: {tool_name}")
