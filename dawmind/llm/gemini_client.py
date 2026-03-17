"""Google Gemini client for vision tasks in DAWMind."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re

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

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY = 1.0


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
            system: Optional system prompt override (used for one-off model).

        Returns:
            The model's text response.
        """
        parts: list[dict | str] = []

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

        model = self._model
        if system:
            model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system,
            )

        return await self._call_with_retry(model, parts)

    async def _call_with_retry(
        self,
        model: genai.GenerativeModel,
        parts: list,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> str:
        """Call Gemini with exponential backoff on transient errors."""
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                response = await model.generate_content_async(parts)
                return response.text
            except Exception as exc:
                last_error = exc
                error_str = str(exc).lower()
                # Retry on rate-limit and transient server errors
                if "429" in error_str or "500" in error_str or "503" in error_str:
                    delay = _DEFAULT_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        "Gemini API transient error (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1,
                        max_retries,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Non-transient error, raise immediately
                logger.error("Gemini API error: %s", exc)
                raise

        logger.error("Gemini API failed after %d retries: %s", max_retries, last_error)
        raise last_error  # type: ignore[misc]

    def complete_sync(
        self,
        prompt: str,
        *,
        images: list[bytes] | None = None,
        system: str | None = None,
    ) -> str:
        """Synchronous wrapper around :meth:`complete` for non-async contexts."""
        return asyncio.get_event_loop().run_until_complete(
            self.complete(prompt, images=images, system=system)
        )

    async def analyze_screenshot(
        self,
        image: bytes,
        task: str,
        parsed_elements: list[dict] | None = None,
    ) -> dict:
        """Analyze a DAW screenshot and return a structured action plan.

        Args:
            image: Screenshot as PNG bytes.
            task: What the user wants to achieve.
            parsed_elements: Optional pre-parsed UI elements from OmniParser.

        Returns:
            Dict with ``observations`` (str) and ``actions`` (list of action dicts).
        """
        prompt_parts = [
            f"Task: {task}",
            "",
            "Analyze this FL Studio screenshot and determine what actions to take.",
        ]

        if parsed_elements:
            elements_json = json.dumps(parsed_elements, indent=2)
            prompt_parts.append(f"\nDetected UI elements (from OmniParser):\n{elements_json}")

        prompt_parts.append(
            "\nReturn a JSON object (no markdown fences) with:\n"
            '- "observations": string describing what you see in the screenshot\n'
            '- "actions": list of action objects, each with:\n'
            '    - "type": one of "click", "drag", "drag_vertical", "type", "scroll"\n'
            '    - "target": description of the UI element\n'
            '    - "x", "y": coordinates (integers)\n'
            '    - "details": any extra parameters (direction, amount, text, etc.)\n'
        )

        response_text = await self.complete("\n".join(prompt_parts), images=[image])

        return self._parse_json_response(response_text)

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """Extract a JSON object from Gemini's response text.

        Handles responses wrapped in markdown code fences or with extra text.
        """
        # Try direct JSON parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences
        fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                pass

        # Find first { ... } block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return raw text wrapped in a dict
        logger.warning("Could not parse JSON from Gemini response, returning raw text")
        return {"observations": text, "actions": []}
