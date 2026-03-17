"""DAWMind Orchestrator – main agent loop.

Receives user input, plans via LLM, dispatches actions to API or Vision layer,
verifies execution, and reports results.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum

import websockets

from dawmind.api_layer.protocol import Command, create_command
from dawmind.api_layer.state import DAWState
from dawmind.config import DAWMindConfig
from dawmind.llm.router import ModelRouter

logger = logging.getLogger(__name__)


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
    """Main agent loop that coordinates LLM planning and action execution."""

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

    async def process_input(self, user_input: str) -> str:
        """Process a user's natural language command.

        Returns a human-readable summary of what was done.
        """
        logger.info("Processing: %s", user_input)

        # Step 1: Plan – ask the LLM to break down the request
        plan = await self._create_plan(user_input)
        logger.info("Plan: %s (%d steps)", plan.reasoning, len(plan.steps))

        # Step 2: Execute each step
        results = []
        for i, step in enumerate(plan.steps):
            logger.info("Step %d/%d: %s", i + 1, len(plan.steps), step.description)

            if step.layer == ActionLayer.API:
                result = await self._execute_api_step(step)
            else:
                result = await self._execute_vision_step(step)

            results.append(result)

            if step.error:
                logger.error("Step %d failed: %s", i + 1, step.error)
                break

        # Step 3: Summarize
        summary = await self._summarize_results(plan, results)
        return summary

    async def _create_plan(self, user_input: str) -> Plan:
        """Use the planning LLM to break down a user request into steps.

        TODO: Full LLM integration. Currently uses a simple keyword-based
        heuristic for testing.
        """
        plan = Plan(user_input=user_input, reasoning="")

        # Simple keyword-based planning for bootstrap
        lower = user_input.lower()

        if "play" in lower:
            plan.reasoning = "Start playback"
            plan.steps.append(
                Step(
                    description="Start transport playback",
                    layer=ActionLayer.API,
                    command=create_command("transport", "play"),
                )
            )
        elif "stop" in lower:
            plan.reasoning = "Stop playback"
            plan.steps.append(
                Step(
                    description="Stop transport",
                    layer=ActionLayer.API,
                    command=create_command("transport", "stop"),
                )
            )
        elif "tempo" in lower:
            # Try to extract a number
            import re

            match = re.search(r"(\d+(?:\.\d+)?)", user_input)
            bpm = float(match.group(1)) if match else 120.0
            plan.reasoning = f"Set tempo to {bpm} BPM"
            plan.steps.append(
                Step(
                    description=f"Set tempo to {bpm}",
                    layer=ActionLayer.API,
                    command=create_command("transport", "setTempo", bpm=bpm),
                )
            )
        elif "volume" in lower:
            plan.reasoning = "Adjust volume (needs LLM parsing for target track and value)"
            # TODO: LLM should parse the target track and volume value
            plan.steps.append(
                Step(
                    description="Adjust volume",
                    layer=ActionLayer.API,
                    command=create_command("mixer", "setTrackVolume", track=0, volume=0.8),
                )
            )
        elif "mute" in lower:
            plan.reasoning = "Toggle mute"
            plan.steps.append(
                Step(
                    description="Toggle mute on track",
                    layer=ActionLayer.API,
                    command=create_command("mixer", "muteTrack", track=0),
                )
            )
        else:
            # Default: ask the planning LLM
            plan.reasoning = "Complex request – requires LLM planning"
            # TODO: Send to Claude for multi-step planning
            plan.steps.append(
                Step(
                    description=f"Execute: {user_input}",
                    layer=ActionLayer.API,
                    command=create_command("state", "full"),
                )
            )

        return plan

    async def _execute_api_step(self, step: Step) -> dict:
        """Execute a step via the API layer (bridge → FL Studio)."""
        if step.command is None:
            step.error = "No command specified"
            return {}

        if self._ws is None:
            step.error = "Not connected to bridge server"
            return {}

        try:
            await self._ws.send(step.command.model_dump_json())
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            response = json.loads(raw)

            if response.get("status") == "ok":
                step.completed = True
                step.result = response.get("result", {})
            else:
                step.error = response.get("error", "Unknown error")

            return response
        except TimeoutError:
            step.error = "Timeout waiting for FL Studio response"
            return {}
        except Exception as exc:
            step.error = str(exc)
            return {}

    async def _execute_vision_step(self, step: Step) -> dict:
        """Execute a step via the Vision layer (screenshot → action).

        TODO: Implement full vision pipeline.
        """
        logger.info("Vision step: %s", step.description)
        step.error = "Vision layer not yet implemented"
        return {}

    async def _summarize_results(self, plan: Plan, results: list[dict]) -> str:
        """Produce a human-readable summary of execution results.

        TODO: Use LLM for natural language summary.
        """
        completed = sum(1 for s in plan.steps if s.completed)
        total = len(plan.steps)

        if completed == total:
            return f"Done: {plan.reasoning} ({completed}/{total} steps completed)"

        failed = [s for s in plan.steps if s.error]
        errors = "; ".join(s.error for s in failed)
        return f"Partial: {plan.reasoning} ({completed}/{total} steps). Errors: {errors}"

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
