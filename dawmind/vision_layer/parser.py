"""OmniParser V2 client for UI element detection."""

from __future__ import annotations

import base64
import logging

import httpx
from pydantic import BaseModel, Field

from dawmind.config import DAWMindConfig

logger = logging.getLogger(__name__)


class UIElement(BaseModel):
    """A detected UI element from OmniParser."""

    label: str = ""
    element_type: str = ""  # knob, slider, button, dropdown, display, text
    bbox: list[float] = Field(default_factory=list)  # [x1, y1, x2, y2] normalized
    confidence: float = 0.0
    center_x: float = 0.0
    center_y: float = 0.0


class ParseResult(BaseModel):
    """Result from OmniParser analysis."""

    elements: list[UIElement] = Field(default_factory=list)
    raw_response: dict = Field(default_factory=dict)


class OmniParser:
    """Client for the OmniParser V2 UI element detection service."""

    def __init__(self, config: DAWMindConfig) -> None:
        self._endpoint = config.vision.omniparser_endpoint
        self._http = httpx.AsyncClient(timeout=30.0)

    async def parse(self, screenshot: bytes) -> ParseResult:
        """Send a screenshot to OmniParser and get detected UI elements.

        Args:
            screenshot: PNG image bytes.

        Returns:
            ParseResult with detected UI elements and bounding boxes.
        """
        encoded = base64.b64encode(screenshot).decode("utf-8")

        try:
            response = await self._http.post(
                self._endpoint,
                json={"image": encoded, "return_labels": True},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error("OmniParser request failed: %s", exc)
            return ParseResult()

        elements = []
        for item in data.get("elements", []):
            bbox = item.get("bbox", [0, 0, 0, 0])
            cx = (bbox[0] + bbox[2]) / 2 if len(bbox) >= 4 else 0.0
            cy = (bbox[1] + bbox[3]) / 2 if len(bbox) >= 4 else 0.0

            elements.append(
                UIElement(
                    label=item.get("label", ""),
                    element_type=item.get("type", "unknown"),
                    bbox=bbox,
                    confidence=item.get("confidence", 0.0),
                    center_x=cx,
                    center_y=cy,
                )
            )

        logger.info("OmniParser detected %d elements", len(elements))
        return ParseResult(elements=elements, raw_response=data)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()
