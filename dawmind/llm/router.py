"""LLM Model Router – selects the best model for each task type."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Protocol

from dawmind.config import DAWMindConfig

logger = logging.getLogger(__name__)


class TaskType(StrEnum):
    """Classification of tasks for model routing."""

    PLANNING = "planning"
    VISION = "vision"
    SIMPLE_LOOKUP = "simple_lookup"
    AUDIO_ANALYSIS = "audio_analysis"


class LLMClient(Protocol):
    """Protocol that all LLM clients must implement."""

    async def complete(
        self,
        prompt: str,
        *,
        tools: list[dict] | None = None,
        images: list[bytes] | None = None,
        system: str | None = None,
    ) -> str: ...


class ModelRouter:
    """Routes tasks to the appropriate LLM based on task type and config."""

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._clients: dict[str, LLMClient] = {}
        self._strategy = config.llm.router_strategy

    def _get_client(self, model_key: str) -> LLMClient:
        """Lazy-initialize and cache LLM clients."""
        if model_key in self._clients:
            return self._clients[model_key]

        if model_key == "planning":
            from dawmind.llm.claude import ClaudeClient

            client = ClaudeClient(self._config)
        elif model_key == "vision":
            from dawmind.llm.gemini_client import GeminiClient

            client = GeminiClient(self._config)
        elif model_key == "local":
            from dawmind.llm.local import OllamaClient

            client = OllamaClient(self._config)
        else:
            raise ValueError(f"Unknown model key: {model_key}")

        self._clients[model_key] = client
        return client

    def route(self, task_type: TaskType) -> LLMClient:
        """Select the appropriate LLM client for a task type."""
        if self._strategy == "force_api":
            return self._get_client("planning")
        if self._strategy == "force_vision":
            return self._get_client("vision")

        # Auto routing
        match task_type:
            case TaskType.PLANNING:
                return self._get_client("planning")
            case TaskType.VISION:
                return self._get_client("vision")
            case TaskType.SIMPLE_LOOKUP:
                try:
                    return self._get_client("local")
                except Exception:
                    logger.warning("Local model unavailable, falling back to planning model")
                    return self._get_client("planning")
            case TaskType.AUDIO_ANALYSIS:
                return self._get_client("planning")
            case _:
                return self._get_client("planning")

    async def complete(
        self,
        task_type: TaskType,
        prompt: str,
        *,
        tools: list[dict] | None = None,
        images: list[bytes] | None = None,
        system: str | None = None,
    ) -> str:
        """Route a completion request to the appropriate model."""
        client = self.route(task_type)
        return await client.complete(prompt, tools=tools, images=images, system=system)
