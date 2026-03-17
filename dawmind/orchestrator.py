"""DAWMind Orchestrator – agentic loop powered by Claude tool-use.

Receives user input, sends it to Claude with DAW state and tools,
executes tool calls via the bridge (API) or locally (Vision), feeds
results back, and lets Claude decide the next step until it's done.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum

import websockets

from dawmind.api_layer.protocol import Command
from dawmind.api_layer.state import DAWState
from dawmind.config import DAWMindConfig
from dawmind.llm.claude import AgentResponse, ClaudeClient, ToolCall
from dawmind.llm.router import ModelRouter, TaskType
from dawmind.tools import ALL_TOOLS, execute_tool, is_vision_tool

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 10


class ActionLayer(StrEnum):
    """Which execution layer to use for an action."""

    API = "api"
    VISION = "vision"


@dataclass
class Step:
    """A single executable step in an action plan."""

    description: str
    layer: ActionLayer
    command: Command | None = None
    vision_task: dict | None = None
    completed: bool = False
    result: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class Plan:
    """An action plan produced by the LLM planner."""

    user_input: str
    reasoning: str
    steps: list[Step] = field(default_factory=list)


class Orchestrator:
    """Main agent loop that coordinates Claude tool-use and action execution."""

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._router = ModelRouter(config)
        self._daw_state = DAWState()
        self._running = False

    async def connect(self) -> None:
        """Connect to the bridge server via WebSocket."""
        uri = f"ws://{self._config.server.host}:{self._config.server.ws_port}/ws"
        logger.info("Connecting to bridge server at %s", uri)
        self._ws = await websockets.connect(uri)
        logger.info("Connected to bridge server")

        # Start listening for state updates
        asyncio.create_task(self._state_listener())

    async def disconnect(self) -> None:
        """Disconnect from the bridge server."""
        if self._ws:
            await self._ws.close()
            self._ws = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def process_input(self, user_input: str) -> str:
        """Process a user's natural language command via the agentic loop.

        Flow:
            1. Build context with current DAW state
            2. Send user request + tools to Claude
            3. If Claude calls tools → execute → feed results back → repeat
            4. When Claude finishes (text only, no tool calls) → return text
        """
        logger.info("Processing: %s", user_input)

        client = self._get_claude_client()
        tools = ALL_TOOLS

        # Build the initial user message with DAW state context
        user_message = self._build_user_message(user_input)
        messages: list[dict] = [{"role": "user", "content": user_message}]

        response: AgentResponse | None = None
        for iteration in range(MAX_AGENT_ITERATIONS):
            logger.info("Agent iteration %d/%d", iteration + 1, MAX_AGENT_ITERATIONS)

            response = await client.send_messages(messages, tools)

            # If no tool calls, Claude is done — return the final text
            if not response.tool_calls:
                logger.info("Agent finished after %d iterations", iteration + 1)
                return response.text or "Done."

            # Append Claude's assistant turn (text + tool_use blocks) to history
            assistant_content = self._build_assistant_content(response)
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute each tool call and collect results
            tool_results: list[dict] = []
            for tc in response.tool_calls:
                result = await self._execute_tool_call(tc)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": json.dumps(result),
                    }
                )

            # Append tool results as a user message (Claude API format)
            messages.append({"role": "user", "content": tool_results})

        # Safety: if we hit the iteration cap, return what we have
        logger.warning("Agent hit max iterations (%d)", MAX_AGENT_ITERATIONS)
        final_text = ""
        if response is not None:
            final_text = response.text
        return (
            final_text
            or "I reached the maximum number of steps. Here's what I've done so far."
        )

    # ------------------------------------------------------------------
    # Message construction helpers
    # ------------------------------------------------------------------

    def _build_user_message(self, user_input: str) -> str:
        """Build a rich user message that includes the current DAW state."""
        state_summary = self._format_daw_state()
        if state_summary:
            return (
                f"{user_input}\n\n"
                f"--- Current DAW State ---\n{state_summary}"
            )
        return user_input

    def _format_daw_state(self) -> str:
        """Format the current DAW state as a concise context string."""
        s = self._daw_state
        parts: list[str] = []

        # Transport
        status = "playing" if s.transport.playing else "stopped"
        if s.transport.recording:
            status = "recording"
        parts.append(
            f"Transport: {status}, tempo={s.transport.tempo} BPM, "
            f"position={s.transport.song_position}"
        )

        # Mixer tracks
        if s.mixer_tracks:
            track_lines = []
            for t in s.mixer_tracks:
                extras = []
                if t.muted:
                    extras.append("MUTED")
                if t.solo:
                    extras.append("SOLO")
                extra_str = f" [{', '.join(extras)}]" if extras else ""
                fx = ""
                if t.effects:
                    fx_names = [e.plugin_name for e in t.effects if e.plugin_name]
                    if fx_names:
                        fx = f" fx=[{', '.join(fx_names)}]"
                track_lines.append(
                    f"  [{t.index}] {t.name or '(unnamed)'}: "
                    f"vol={t.volume:.2f} pan={t.pan:.2f}{extra_str}{fx}"
                )
            parts.append("Mixer Tracks:\n" + "\n".join(track_lines))

        # Channels
        if s.channels:
            ch_lines = []
            for c in s.channels:
                sel = " *" if c.selected else ""
                ch_lines.append(
                    f"  [{c.index}] {c.name or '(unnamed)'} "
                    f"({c.plugin_name or 'no plugin'}): "
                    f"vol={c.volume:.2f} → mixer {c.target_mixer_track}{sel}"
                )
            parts.append("Channels:\n" + "\n".join(ch_lines))

        # Patterns
        if s.pattern_count:
            parts.append(
                f"Patterns: {s.pattern_count} total, current={s.current_pattern}"
            )

        return "\n".join(parts)

    @staticmethod
    def _build_assistant_content(response: AgentResponse) -> list[dict]:
        """Reconstruct the assistant content blocks for the message history."""
        content: list[dict] = []
        if response.text:
            content.append({"type": "text", "text": response.text})
        for tc in response.tool_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                }
            )
        return content

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool_call(self, tc: ToolCall) -> dict:
        """Execute a single tool call and return the result dict."""
        logger.info("Executing tool: %s(%s)", tc.name, tc.input)

        try:
            command = execute_tool(tc.name, tc.input)
        except ValueError as exc:
            logger.error("Unknown tool %s: %s", tc.name, exc)
            return {"status": "error", "error": str(exc)}

        if is_vision_tool(tc.name):
            return await self._execute_vision_command(command)
        return await self._execute_api_command(command)

    async def _execute_api_command(self, command: Command) -> dict:
        """Execute a command via the API layer (bridge → FL Studio)."""
        if self._ws is None:
            return {"status": "error", "error": "Not connected to bridge server"}

        try:
            await self._ws.send(command.model_dump_json())
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            response = json.loads(raw)

            if response.get("status") == "ok":
                return {"status": "ok", "result": response.get("result", {})}
            return {
                "status": "error",
                "error": response.get("error", "Unknown error"),
            }
        except TimeoutError:
            return {"status": "error", "error": "Timeout waiting for FL Studio response"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def _execute_vision_command(self, command: Command) -> dict:
        """Execute a vision command locally (screenshot + PyAutoGUI).

        TODO: Wire up the full vision pipeline (capture → parse → reason → execute → verify).
        """
        logger.info("Vision command: %s", command.action)
        return {
            "status": "error",
            "error": "Vision layer execution not yet implemented",
        }

    # ------------------------------------------------------------------
    # Claude client access
    # ------------------------------------------------------------------

    def _get_claude_client(self) -> ClaudeClient:
        """Get the Claude client from the router."""
        client = self._router.route(TaskType.PLANNING)
        # The router guarantees a ClaudeClient for PLANNING task type
        if not isinstance(client, ClaudeClient):
            return ClaudeClient(self._config)
        return client

    # ------------------------------------------------------------------
    # Legacy step-based execution (kept for backward compatibility)
    # ------------------------------------------------------------------

    async def _execute_api_step(self, step: Step) -> dict:
        """Execute a step via the API layer (bridge → FL Studio)."""
        if step.command is None:
            step.error = "No command specified"
            return {}

        result = await self._execute_api_command(step.command)
        if result.get("status") == "ok":
            step.completed = True
            step.result = result.get("result", {})
        else:
            step.error = result.get("error", "Unknown error")
        return result

    async def _execute_vision_step(self, step: Step) -> dict:
        """Execute a step via the Vision layer (screenshot → action).

        TODO: Implement full vision pipeline.
        """
        logger.info("Vision step: %s", step.description)
        step.error = "Vision layer not yet implemented"
        return {}

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    async def _state_listener(self) -> None:
        """Listen for state broadcasts from the bridge server."""
        if self._ws is None:
            return

        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                    if msg.get("type") == "state":
                        self._daw_state = DAWState.model_validate(msg.get("data", {}))
                except (json.JSONDecodeError, Exception):
                    pass
        except websockets.ConnectionClosed:
            logger.warning("Bridge connection closed")

    @property
    def daw_state(self) -> DAWState:
        return self._daw_state

    async def get_status(self) -> dict:
        """Return the current orchestrator status."""
        return {
            "connected": self._ws is not None,
            "daw_state_available": bool(self._daw_state.mixer_tracks),
            "transport_playing": self._daw_state.transport.playing,
            "tempo": self._daw_state.transport.tempo,
        }
