"""Vision reasoning – sends parsed screenshots to Vision LLM for action planning."""

from __future__ import annotations

import logging

from dawmind.config import DAWMindConfig
from dawmind.llm.gemini_client import GeminiClient
from dawmind.vision_layer.parser import ParseResult, UIElement

logger = logging.getLogger(__name__)


class VisionReasoner:
    """Uses a Vision LLM to decide actions based on screenshot analysis."""

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._llm = GeminiClient(config)

    async def plan_action(
        self,
        screenshot: bytes,
        task: str,
        parse_result: ParseResult | None = None,
    ) -> list[dict]:
        """Analyze a screenshot and produce a list of actions to execute.

        Args:
            screenshot: PNG image of the current screen.
            task: Natural language description of what to do.
            parse_result: Optional OmniParser results for the screenshot.

        Returns:
            List of action dicts, e.g.:
            [{"type": "click", "x": 450, "y": 300},
             {"type": "drag_vertical", "x": 450, "y": 300, "direction": "up", "amount": 30}]
        """
        elements_info = None
        if parse_result and parse_result.elements:
            elements_info = [
                {
                    "label": e.label,
                    "type": e.element_type,
                    "center": (e.center_x, e.center_y),
                    "bbox": e.bbox,
                }
                for e in parse_result.elements
            ]

        response = await self._llm.analyze_screenshot(
            image=screenshot,
            task=task,
            parsed_elements=elements_info,
        )

        actions = self._parse_action_response(response)
        logger.info("Vision reasoner produced %d actions for task: %s", len(actions), task)
        return actions

    def _parse_action_response(self, response: str) -> list[dict]:
        """Parse the LLM's text response into structured action dicts.

        Expected format from the LLM:
        CLICK x,y
        DRAG x1,y1 x2,y2
        DRAG_VERTICAL x,y direction amount
        TYPE text
        SCROLL x,y direction amount
        """
        actions = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if not parts:
                continue

            action_type = parts[0].upper()

            if action_type == "CLICK" and len(parts) >= 2:
                coords = parts[1].split(",")
                if len(coords) >= 2:
                    actions.append({
                        "type": "click",
                        "x": int(coords[0]),
                        "y": int(coords[1]),
                    })

            elif action_type == "DRAG" and len(parts) >= 3:
                start = parts[1].split(",")
                end = parts[2].split(",")
                if len(start) >= 2 and len(end) >= 2:
                    actions.append({
                        "type": "drag",
                        "x1": int(start[0]),
                        "y1": int(start[1]),
                        "x2": int(end[0]),
                        "y2": int(end[1]),
                    })

            elif action_type == "DRAG_VERTICAL" and len(parts) >= 4:
                coords = parts[1].split(",")
                if len(coords) >= 2:
                    actions.append({
                        "type": "drag_vertical",
                        "x": int(coords[0]),
                        "y": int(coords[1]),
                        "direction": parts[2],
                        "amount": int(parts[3]),
                    })

            elif action_type == "TYPE" and len(parts) >= 2:
                text = " ".join(parts[1:])
                actions.append({"type": "type", "text": text})

            elif action_type == "SCROLL" and len(parts) >= 4:
                coords = parts[1].split(",")
                if len(coords) >= 2:
                    actions.append({
                        "type": "scroll",
                        "x": int(coords[0]),
                        "y": int(coords[1]),
                        "direction": parts[2],
                        "amount": int(parts[3]),
                    })

        return actions

    async def find_element(
        self,
        screenshot: bytes,
        element_description: str,
        parse_result: ParseResult | None = None,
    ) -> UIElement | None:
        """Find a specific UI element in a screenshot.

        Args:
            screenshot: PNG image bytes.
            element_description: Natural language description of the element.
            parse_result: Optional pre-parsed UI elements.

        Returns:
            The matching UIElement, or None if not found.
        """
        if parse_result and parse_result.elements:
            # Ask the LLM to match the description to a parsed element
            prompt = (
                f"Given these UI elements: {[e.label for e in parse_result.elements]}\n"
                f"Which one best matches: '{element_description}'?\n"
                f"Respond with just the element label."
            )
            response = await self._llm.complete(prompt, images=[screenshot])
            label = response.strip().strip("'\"")

            for element in parse_result.elements:
                if label.lower() in element.label.lower():
                    return element

        return None
