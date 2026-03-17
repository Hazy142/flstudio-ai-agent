"""Action verification – confirms vision-based actions succeeded."""

from __future__ import annotations

import logging

from dawmind.config import DAWMindConfig
from dawmind.llm.gemini_client import GeminiClient
from dawmind.vision_layer.capture import ScreenCapture

logger = logging.getLogger(__name__)


class ActionVerifier:
    """Verifies that a vision-based action achieved its intended effect.

    Takes before/after screenshots and asks the Vision LLM to compare them.
    """

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._capture = ScreenCapture(config)
        self._llm = GeminiClient(config)
        self._enabled = config.vision.verification_enabled

    async def verify(
        self,
        before: bytes,
        after: bytes,
        expected_change: str,
    ) -> VerificationResult:
        """Compare before/after screenshots to verify an action.

        Args:
            before: Screenshot taken before the action.
            after: Screenshot taken after the action.
            expected_change: Description of what should have changed.

        Returns:
            VerificationResult indicating success, failure, or uncertainty.
        """
        if not self._enabled:
            return VerificationResult(success=True, confidence=1.0, reason="Verification disabled")

        prompt = (
            f"Compare these two screenshots (before and after an action).\n"
            f"Expected change: {expected_change}\n\n"
            f"Did the expected change occur? Answer with:\n"
            f"- YES: if the change clearly happened\n"
            f"- NO: if nothing changed or something different happened\n"
            f"- UNCERTAIN: if you can't tell\n\n"
            f"Then briefly explain what you observe."
        )

        try:
            response = await self._llm.complete(prompt, images=[before, after])
            return self._parse_response(response)
        except Exception as exc:
            logger.error("Verification failed: %s", exc)
            return VerificationResult(
                success=False,
                confidence=0.0,
                reason=f"Verification error: {exc}",
            )

    def capture_before(self) -> bytes:
        """Take a 'before' screenshot for later comparison."""
        return self._capture.capture_full(force=True)

    def capture_after(self) -> bytes:
        """Take an 'after' screenshot for comparison."""
        self._capture.invalidate_cache()
        return self._capture.capture_full(force=True)

    def _parse_response(self, response: str) -> VerificationResult:
        """Parse the LLM's verification response."""
        upper = response.strip().upper()
        if upper.startswith("YES"):
            return VerificationResult(success=True, confidence=0.9, reason=response)
        elif upper.startswith("NO"):
            return VerificationResult(success=False, confidence=0.9, reason=response)
        else:
            return VerificationResult(success=False, confidence=0.5, reason=response)


class VerificationResult:
    """Result of an action verification."""

    def __init__(self, success: bool, confidence: float, reason: str) -> None:
        self.success = success
        self.confidence = confidence
        self.reason = reason

    def __repr__(self) -> str:
        status = "OK" if self.success else "FAILED"
        return f"VerificationResult({status}, confidence={self.confidence:.1f})"
