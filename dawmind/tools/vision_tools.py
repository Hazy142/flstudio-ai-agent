"""Vision-based GUI control tools for Claude tool-use."""

from __future__ import annotations

from dawmind.api_layer.commands import vision_interact
from dawmind.api_layer.protocol import Command

VISION_TOOLS = [
    {
        "name": "vision_click_element",
        "description": (
            "Click a UI element in a plugin window identified by description. "
            "Use this for buttons, checkboxes, and menu items in third-party plugin GUIs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plugin_window": {
                    "type": "string",
                    "description": "Name of the plugin window (e.g. 'Serum', 'Vital', 'OTT').",
                },
                "element_description": {
                    "type": "string",
                    "description": (
                        "Natural language description of the element to click "
                        "(e.g. 'the filter cutoff knob', 'the preset browser button')."
                    ),
                },
            },
            "required": ["plugin_window", "element_description"],
        },
    },
    {
        "name": "vision_drag_knob",
        "description": (
            "Drag a knob in a plugin GUI to change its value. "
            "Most VST knobs respond to vertical mouse movement."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plugin_window": {
                    "type": "string",
                    "description": "Name of the plugin window.",
                },
                "knob_description": {
                    "type": "string",
                    "description": "Description of the knob (e.g. 'cutoff frequency knob').",
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Drag direction. 'up' increases value, 'down' decreases.",
                },
                "amount": {
                    "type": "integer",
                    "description": "Drag amount in pixels (10=small, 30=medium, 60=large change).",
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": ["plugin_window", "knob_description", "direction", "amount"],
        },
    },
    {
        "name": "vision_read_display",
        "description": (
            "Read a value or text displayed in a plugin GUI "
            "(e.g. a frequency readout, preset name, parameter value)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plugin_window": {
                    "type": "string",
                    "description": "Name of the plugin window.",
                },
                "display_description": {
                    "type": "string",
                    "description": "Description of what to read (e.g. 'current preset name').",
                },
            },
            "required": ["plugin_window", "display_description"],
        },
    },
    {
        "name": "vision_screenshot",
        "description": (
            "Capture a screenshot of FL Studio or a specific plugin window for analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "What to capture: 'full_screen', 'fl_studio', or a plugin name."
                    ),
                },
            },
            "required": ["target"],
        },
    },
]


def execute(tool_name: str, params: dict) -> Command:
    """Create the FL Studio command for a vision tool call."""
    match tool_name:
        case "vision_click_element":
            return vision_interact(
                description=params["element_description"],
                plugin_window=params["plugin_window"],
                element_hint=params["element_description"],
                interaction_type="click",
            )
        case "vision_drag_knob":
            return vision_interact(
                description=params["knob_description"],
                plugin_window=params["plugin_window"],
                element_hint=params["knob_description"],
                interaction_type="drag_vertical",
                direction=params["direction"],
                amount=params["amount"],
            )
        case "vision_read_display":
            return vision_interact(
                description=params["display_description"],
                plugin_window=params["plugin_window"],
                element_hint=params["display_description"],
                interaction_type="read",
            )
        case "vision_screenshot":
            return vision_interact(
                description=f"Capture screenshot of {params['target']}",
                plugin_window=params.get("target", "full_screen"),
                element_hint="",
                interaction_type="screenshot",
            )
        case _:
            raise ValueError(f"Unknown vision tool: {tool_name}")
