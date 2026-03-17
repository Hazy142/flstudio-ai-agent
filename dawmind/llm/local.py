"""Ollama local model client for simple lookups."""

from __future__ import annotations

import logging

import httpx

from dawmind.config import DAWMindConfig

logger = logging.getLogger(__name__)

_OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaClient:
    """Client for Ollama-hosted local models (e.g. llama3).

    Used for simple parameter lookups and caching to avoid API costs.
    """

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._model = config.llm.local_model
        self._base_url = _OLLAMA_BASE_URL
        self._http = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)

    async def complete(
        self,
        prompt: str,
        *,
        tools: list[dict] | None = None,
        images: list[bytes] | None = None,
        system: str | None = None,
    ) -> str:
        """Send a completion request to the local Ollama model.

        Args:
            prompt: The user message.
            tools: Ignored (Ollama basic API doesn't support tool use).
            images: Ignored for text-only models.
            system: Optional system prompt.
        """
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        try:
            response = await self._http.post("/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except httpx.HTTPError as exc:
            logger.error("Ollama request failed: %s", exc)
            raise

    async def is_available(self) -> bool:
        """Check if Ollama is running and the model is loaded."""
        try:
            response = await self._http.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(self._model in m for m in models)
        except httpx.HTTPError:
            return False
