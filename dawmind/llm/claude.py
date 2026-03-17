"""Anthropic Claude client wrapper for DAWMind."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import anthropic

from dawmind.config import DAWMindConfig

logger = logging.getLogger(__name__)

# System prompt for the DAWMind planning agent
SYSTEM_PROMPT = """\
You are DAWMind, an AI agent that controls FL Studio through tool calls.

## How You Work
You receive natural language instructions about music production tasks and execute
them by calling the available tools. You can call multiple tools in sequence —
inspect state first, then make changes.

## Available Tool Categories

### API Tools (fast, reliable — always prefer these)
- **Transport**: play, stop, record, set tempo
- **Mixer**: get/set volume, get/set pan, mute, solo (tracks 0-125, where 0 = master)
- **Channels**: get name, set volume, count, select (channel rack instruments)
- **Plugins**: get/set parameter values by index (0.0–1.0 range)
- **State**: get_daw_state — fetches complete project snapshot

### Vision Tools (slower — use only when API tools can't reach the control)
- Click elements, drag knobs, read displays, take screenshots
- Use these for third-party plugin GUIs (e.g. Serum, Vital, OTT) that aren't
  exposed via FL Studio's API

## FL Studio Domain Knowledge

### Volume Scale
- All volumes are 0.0 to 1.0 (linear fader scale)
- 0.0 = silence (−∞ dB)
- 0.8 ≈ 0 dB (unity gain / default)
- 1.0 ≈ +5.6 dB
- To cut 3 dB, reduce by ~0.1 from current value
- To boost 3 dB, increase by ~0.1 from current value

### Mixer Layout
- Track 0 = Master bus
- Tracks 1–125 = Insert tracks (instruments/sends route here)
- Each track has 10 effect slots

### Channel Rack
- Channels are 0-indexed
- Each channel has a generator plugin (e.g. Sampler, Sytrus, 3xOsc)
- Channels route to mixer tracks via `target_mixer_track`

### Plugin Parameters
- Parameter indices are specific to each plugin — always call
  plugin_get_param_name first if you don't know the mapping
- Values are normalised 0.0–1.0 regardless of the parameter's actual range

## Multi-Step Operations
For complex tasks, follow this pattern:
1. Call get_daw_state to understand the current project
2. Query specific details (volumes, parameter names) as needed
3. Make changes
4. Optionally verify the change took effect

Example: "make the kick punchier"
→ get_daw_state → find the kick channel → inspect EQ/compressor params
→ boost low-mid attack, increase compression ratio → verify

## Rules
- Always prefer API tools over vision tools
- Always inspect state before making blind changes
- Explain what you did in your final text response
"""


@dataclass
class ToolCall:
    """A single tool-use block from Claude's response."""

    id: str
    name: str
    input: dict = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Parsed response from a Claude messages API call."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""


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

    async def send_messages(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        system: str | None = None,
    ) -> AgentResponse:
        """Send a full message history and return a parsed AgentResponse.

        This is the core method for the multi-turn agentic loop. It accepts
        the full conversation so far (including prior assistant messages and
        tool_result messages) and returns the next assistant turn.
        """
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system or SYSTEM_PROMPT,
                messages=messages,
                tools=tools,
            )

            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(
                        ToolCall(id=block.id, name=block.name, input=block.input)
                    )

            return AgentResponse(
                text="\n".join(text_parts),
                tool_calls=tool_calls,
                stop_reason=response.stop_reason or "",
            )
        except anthropic.APIError as exc:
            logger.error("Claude API error: %s", exc)
            raise
