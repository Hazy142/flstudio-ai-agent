"""Screenshot capture using mss with region selection."""

from __future__ import annotations

import io
import logging
import time

import mss
from PIL import Image

from dawmind.config import DAWMindConfig

logger = logging.getLogger(__name__)


class ScreenCapture:
    """Fast screenshot capture with caching and region selection."""

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._monitor_index = config.vision.capture_monitor
        self._cache_seconds = config.vision.screenshot_cache_seconds
        self._last_capture: bytes | None = None
        self._last_capture_time: float = 0.0

    def capture_full(self, *, force: bool = False) -> bytes:
        """Capture the full screen (or configured monitor) as PNG bytes.

        Returns cached screenshot if within cache interval unless ``force=True``.
        """
        now = time.time()
        if (
            not force
            and self._last_capture is not None
            and (now - self._last_capture_time) < self._cache_seconds
        ):
            return self._last_capture

        with mss.mss() as sct:
            monitors = sct.monitors
            if self._monitor_index < len(monitors):
                monitor = monitors[self._monitor_index]
            else:
                monitor = monitors[0]  # Entire virtual screen

            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()

        self._last_capture = data
        self._last_capture_time = now
        logger.debug("Captured screenshot (%d bytes)", len(data))
        return data

    def capture_region(self, x: int, y: int, width: int, height: int) -> bytes:
        """Capture a specific screen region as PNG bytes."""
        with mss.mss() as sct:
            region = {"left": x, "top": y, "width": width, "height": height}
            screenshot = sct.grab(region)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    def invalidate_cache(self) -> None:
        """Force the next capture to take a fresh screenshot."""
        self._last_capture = None
        self._last_capture_time = 0.0
