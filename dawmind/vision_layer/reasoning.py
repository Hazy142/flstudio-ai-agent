"""Vision reasoning – combines OmniParser (UI detection) with Gemini (reasoning)."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from dawmind.config import DAWMindConfig
from dawmind.llm.gemini_client import GeminiClient
from dawmind.vision_layer.parser import OmniParser, ParseResult, UIElement

logger = logging.getLogger(__name__)


@dataclass
class VisionAction:
    """A single action planned by the vision reasoning pipeline."""

    type: str  # click, drag, drag_vertical, type, scroll
    target: str  # description of the UI element
    x: int = 0
    y: int = 0
    # Extra parameters depending on action type
    x2: int = 0  # drag end x
    y2: int = 0  # drag end y
    direction: str = ""  # up/down/left/right
    amount: int = 0  # drag/scroll amount
    text: str = ""  # text to type


class VisionReasoner:
    """Combines OmniParser (UI detection) with Gemini (reasoning) for action planning.

    Pipeline:
    1. Send screenshot to OmniParser -> get UI elements with bounding boxes
    2. Annotate screenshot with element IDs (overlay bounding boxes)
    3. Send annotated screenshot + elements + task to Gemini
    4. Gemini returns which element to interact with and how
    5. Return structured VisionAction objects
    """

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._llm = GeminiClient(config)
        self._parser = OmniParser(config)

    async def plan_action(
        self,
        screenshot: bytes,
        task: str,
        parse_result: ParseResult | None = None,
    ) -> list[VisionAction]:
        """Analyze a screenshot and produce a list of actions to execute.

        Args:
            screenshot: PNG image of the current screen.
            task: Natural language description of what to do.
            parse_result: Optional pre-computed OmniParser results. If not
                provided, OmniParser will be called automatically.

        Returns:
            List of VisionAction objects ready for execution.
        """
        # Step 1: Parse UI elements if not already provided
        if parse_result is None:
            parse_result = await self._parser.parse(screenshot)

        # Step 2: Build element info and annotated screenshot
        elements_info = []
        if parse_result.elements:
            elements_info = [
                {
                    "id": idx,
                    "label": e.label,
                    "type": e.element_type,
                    "center": [int(e.center_x), int(e.center_y)],
                    "bbox": [int(v) for v in e.bbox],
                    "confidence": round(e.confidence, 3),
                }
                for idx, e in enumerate(parse_result.elements)
            ]

        # Step 3: Annotate screenshot with bounding boxes and element IDs
        annotated = self._annotate_screenshot(screenshot, parse_result)

        # Step 4: Send to Gemini for reasoning
        result = await self._llm.analyze_screenshot(
            image=annotated,
            task=task,
            parsed_elements=elements_info if elements_info else None,
        )

        # Step 5: Convert response to VisionAction objects
        actions = self._build_actions(result)
        logger.info("Vision reasoner produced %d actions for task: %s", len(actions), task)
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
        if parse_result is None:
            parse_result = await self._parser.parse(screenshot)

        if not parse_result.elements:
            return None

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

    async def close(self) -> None:
        """Clean up resources."""
        await self._parser.close()

    @staticmethod
    def _annotate_screenshot(screenshot: bytes, parse_result: ParseResult) -> bytes:
        """Overlay bounding boxes and element IDs on the screenshot.

        This helps Gemini identify which element to interact with by
        visually marking detected UI elements with numbered labels.
        """
        if not parse_result.elements:
            return screenshot

        img = Image.open(io.BytesIO(screenshot)).convert("RGB")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        except OSError:
            font = ImageFont.load_default()

        colors = ["#FF0000", "#00FF00", "#0088FF", "#FF8800", "#FF00FF", "#00FFFF"]

        for idx, element in enumerate(parse_result.elements):
            bbox = element.bbox
            if len(bbox) < 4:
                continue

            color = colors[idx % len(colors)]
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])

            # Draw bounding box
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

            # Draw label background and text
            label_text = f"[{idx}] {element.label}"
            text_bbox = draw.textbbox((x1, y1 - 18), label_text, font=font)
            draw.rectangle(text_bbox, fill=color)
            draw.text((x1, y1 - 18), label_text, fill="white", font=font)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _build_actions(result: dict) -> list[VisionAction]:
        """Convert Gemini's structured JSON response into VisionAction objects."""
        actions = []
        for action_dict in result.get("actions", []):
            action_type = action_dict.get("type", "").lower()
            target = action_dict.get("target", "")
            details = action_dict.get("details", {})
            if isinstance(details, str):
                details = {}

            action = VisionAction(
                type=action_type,
                target=target,
                x=int(action_dict.get("x", 0)),
                y=int(action_dict.get("y", 0)),
            )

            if action_type == "drag":
                action.x2 = int(details.get("x2", action_dict.get("x2", 0)))
                action.y2 = int(details.get("y2", action_dict.get("y2", 0)))
            elif action_type == "drag_vertical":
                action.direction = str(details.get("direction", "up"))
                action.amount = int(details.get("amount", 10))
            elif action_type == "scroll":
                action.direction = str(details.get("direction", "down"))
                action.amount = int(details.get("amount", 3))
            elif action_type == "type":
                action.text = str(details.get("text", ""))

            actions.append(action)

        return actions
