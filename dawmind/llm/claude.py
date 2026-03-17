"""Anthropic Claude client wrapper for DAWMind."""

from __future__ import annotations

import logging

import anthropic

from dawmind.config import DAWMindConfig

logger = logging.getLogger(__name__)

# System prompt for the DAWMind planning agent
SYSTEM_PROMPT = """\
You are DAWMind, an AI agent that controls FL Studio. You receive natural language
instructions about music production tasks and break them down into concrete API
calls or vision-based actions.

You have access to FL Studio's internal API through these modules:
- transport: play, stop, record, setTempo
- mixer: getTrackVolume, setTrackVolume, getTrackPan, setTrackPan, muteTrack, soloTrack
- channels: getChannelName, setChannelVolume, channelCount, selectChannel
- plugins: getParamCount, getParamName, getParamValue, setParamValue, getPluginName

For third-party plugin GUIs that aren't accessible via the API, you can use
vision-based actions (screenshot + click/drag).

Always prefer API calls over vision actions when possible – they are faster and
more reliable.
"""


class ClaudeClient:
    """Anthropic Claude client for task planning and reasoning."""

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._model = config.llm.planning_model
        self._client = anthropic.AsyncAnthropic(api_key=config.llm.anthropic.api_key or None)

    async def complete(
        self,
        prompt: str,
        *,
        tools: list[dict] | None = None,
        images: list[bytes] | None = None,
        system: str | None = None,
    ) -> str:
        """Send a completion request to Claude.

        Args:
            prompt: The user message.
            tools: Optional tool definitions in Claude tool-use format.
            images: Optional images (not used for Claude planning).
            system: Optional system prompt override.
        """
        messages = [{"role": "user", "content": prompt}]

        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "system": system or SYSTEM_PROMPT,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = await self._client.messages.create(**kwargs)

            # Extract text from response
            text_parts = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)

            return "\n".join(text_parts)
        except anthropic.APIError as exc:
            logger.error("Claude API error: %s", exc)
            raise

    async def complete_with_tools(
        self,
        prompt: str,
        tools: list[dict],
        *,
        system: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Send a request expecting tool use responses.

        Returns:
            A tuple of (text_response, tool_calls) where tool_calls is a list
            of dicts with 'name' and 'input' keys.
        """
        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system or SYSTEM_PROMPT,
                messages=messages,
                tools=tools,
            )

            text_parts = []
            tool_calls = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append({"name": block.name, "input": block.input})

            return "\n".join(text_parts), tool_calls
        except anthropic.APIError as exc:
            logger.error("Claude API error: %s", exc)
            raise
