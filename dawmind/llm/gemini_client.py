"""Google Gemini client for vision tasks in DAWMind."""

from __future__ import annotations

import base64
import logging

import google.generativeai as genai

from dawmind.config import DAWMindConfig

logger = logging.getLogger(__name__)

VISION_SYSTEM_PROMPT = """\
You are DAWMind's vision module. You analyze screenshots of FL Studio and
third-party VST plugin GUIs. Your job is to:

1. Identify UI elements (knobs, sliders, buttons, dropdowns, displays)
2. Determine their current state/values when visible
3. Plan mouse/keyboard actions to achieve the user's goal
4. Output precise action instructions (click coordinates, drag directions, etc.)

When describing actions, use this format:
- CLICK x,y - click at coordinates
- DRAG x1,y1 x2,y2 - drag from point 1 to point 2
- DRAG_VERTICAL x,y direction amount - vertical drag on a knob
- TYPE text - type text into a focused field
- SCROLL x,y direction amount - scroll at position

Always specify coordinates relative to the screenshot dimensions.
"""


class GeminiClient:
    """Google Gemini client for vision-based screenshot analysis."""

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._model_name = config.llm.vision_model

        if config.llm.google.api_key:
            genai.configure(api_key=config.llm.google.api_key)

        self._model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=VISION_SYSTEM_PROMPT,
        )

    async def complete(
        self,
        prompt: str,
        *,
        tools: list[dict] | None = None,
        images: list[bytes] | None = None,
        system: str | None = None,
    ) -> str:
        """Send a completion request to Gemini, optionally with images.

        Args:
            prompt: The text prompt.
            tools: Not used for Gemini vision (ignored).
            images: Optional list of image bytes (PNG/JPEG).
            system: Optional system prompt override (ignored, set in model init).
        """
        parts = []

        # Add images
        if images:
            for img_data in images:
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": base64.b64encode(img_data).decode("utf-8"),
                        }
                    }
                )

        parts.append(prompt)

        try:
            response = await self._model.generate_content_async(parts)
            return response.text
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            raise

    async def analyze_screenshot(
        self,
        image: bytes,
        task: str,
        parsed_elements: list[dict] | None = None,
    ) -> str:
        """Analyze a screenshot with an optional task description.

        Args:
            image: Screenshot as PNG bytes.
            task: What the user wants to achieve.
            parsed_elements: Optional pre-parsed UI elements from OmniParser.
        """
        prompt_parts = [f"Task: {task}"]

        if parsed_elements:
            prompt_parts.append(
                f"Detected UI elements: {parsed_elements!r}"
            )

        prompt_parts.append(
            "Analyze the screenshot and provide the exact actions needed to complete the task."
        )

        return await self.complete("\n\n".join(prompt_parts), images=[image])
