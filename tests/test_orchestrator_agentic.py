"""Tests for the agentic loop orchestrator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dawmind.api_layer.protocol import Command
from dawmind.api_layer.state import (
    ChannelState,
    DAWState,
    EffectSlot,
    MixerTrackState,
    TransportState,
)
from dawmind.config import DAWMindConfig
from dawmind.llm.claude import AgentResponse, ToolCall
from dawmind.orchestrator import (
    MAX_AGENT_ITERATIONS,
    ActionLayer,
    Orchestrator,
    Plan,
    Step,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config():
    return DAWMindConfig()


@pytest.fixture()
def orchestrator(config):
    return Orchestrator(config)


# ---------------------------------------------------------------------------
# Dataclass / enum tests
# ---------------------------------------------------------------------------


def test_action_layer_values():
    assert ActionLayer.API == "api"
    assert ActionLayer.VISION == "vision"


def test_step_defaults():
    step = Step(description="Play", layer=ActionLayer.API)
    assert step.completed is False
    assert step.result == {}
    assert step.error == ""
    assert step.command is None
    assert step.vision_task is None


def test_step_with_command():
    cmd = Command(module="transport", action="play")
    step = Step(description="Play", layer=ActionLayer.API, command=cmd)
    assert step.command.action == "play"


def test_plan_defaults():
    plan = Plan(user_input="Play", reasoning="Simple")
    assert plan.steps == []


def test_plan_with_steps():
    steps = [
        Step(description="Check state", layer=ActionLayer.API),
        Step(description="Set tempo", layer=ActionLayer.API),
    ]
    plan = Plan(user_input="Set tempo to 120", reasoning="Need to change tempo", steps=steps)
    assert len(plan.steps) == 2
    assert plan.steps[0].description == "Check state"


# ---------------------------------------------------------------------------
# Orchestrator init / status
# ---------------------------------------------------------------------------


def test_orchestrator_initial_state(orchestrator):
    assert orchestrator._ws is None
    assert orchestrator._running is False
    assert isinstance(orchestrator._daw_state, DAWState)


async def test_orchestrator_status_disconnected(orchestrator):
    status = await orchestrator.get_status()
    assert status["connected"] is False
    assert status["daw_state_available"] is False


async def test_orchestrator_daw_state_property(orchestrator):
    assert orchestrator.daw_state.transport.playing is False


# ---------------------------------------------------------------------------
# _format_daw_state
# ---------------------------------------------------------------------------


def test_format_daw_state_empty(orchestrator):
    result = orchestrator._format_daw_state()
    assert "Transport: stopped" in result
    assert "tempo=140.0" in result


def test_format_daw_state_playing(orchestrator):
    orchestrator._daw_state = DAWState(transport=TransportState(playing=True, tempo=128.0))
    result = orchestrator._format_daw_state()
    assert "Transport: playing" in result
    assert "tempo=128.0" in result


def test_format_daw_state_recording(orchestrator):
    orchestrator._daw_state = DAWState(
        transport=TransportState(playing=True, recording=True, tempo=140.0)
    )
    result = orchestrator._format_daw_state()
    assert "Transport: recording" in result


def test_format_daw_state_with_mixer_tracks(orchestrator):
    orchestrator._daw_state = DAWState(
        mixer_tracks=[
            MixerTrackState(index=0, name="Master", volume=0.8, pan=0.0),
            MixerTrackState(
                index=1,
                name="Kick",
                volume=0.75,
                muted=True,
                solo=False,
                effects=[EffectSlot(index=0, plugin_name="OTT", enabled=True)],
            ),
        ]
    )
    result = orchestrator._format_daw_state()
    assert "Mixer Tracks:" in result
    assert "[0] Master" in result
    assert "[1] Kick" in result
    assert "MUTED" in result
    assert "fx=[OTT]" in result


def test_format_daw_state_with_solo_track(orchestrator):
    orchestrator._daw_state = DAWState(
        mixer_tracks=[
            MixerTrackState(index=2, name="Vocal", volume=0.6, solo=True),
        ]
    )
    result = orchestrator._format_daw_state()
    assert "SOLO" in result


def test_format_daw_state_with_channels(orchestrator):
    orchestrator._daw_state = DAWState(
        channels=[
            ChannelState(
                index=0,
                name="Kick",
                plugin_name="Sampler",
                volume=0.8,
                selected=True,
                target_mixer_track=1,
            ),
            ChannelState(index=1, name="HiHat", volume=0.6, target_mixer_track=2),
        ]
    )
    result = orchestrator._format_daw_state()
    assert "Channels:" in result
    assert "[0] Kick (Sampler)" in result
    assert "→ mixer 1" in result
    assert " *" in result  # selected marker
    assert "[1] HiHat (no plugin)" in result


def test_format_daw_state_with_patterns(orchestrator):
    orchestrator._daw_state = DAWState(pattern_count=8, current_pattern=3)
    result = orchestrator._format_daw_state()
    assert "Patterns: 8 total, current=3" in result


# ---------------------------------------------------------------------------
# _build_user_message
# ---------------------------------------------------------------------------


def test_build_user_message_with_state(orchestrator):
    msg = orchestrator._build_user_message("Play the track")
    assert "Play the track" in msg
    assert "--- Current DAW State ---" in msg
    assert "Transport:" in msg


def test_build_user_message_preserves_input(orchestrator):
    msg = orchestrator._build_user_message("Set volume to 0.5")
    assert msg.startswith("Set volume to 0.5")


# ---------------------------------------------------------------------------
# _build_assistant_content
# ---------------------------------------------------------------------------


def test_build_assistant_content_text_only():
    resp = AgentResponse(text="All done!")
    content = Orchestrator._build_assistant_content(resp)
    assert len(content) == 1
    assert content[0] == {"type": "text", "text": "All done!"}


def test_build_assistant_content_tool_calls():
    resp = AgentResponse(
        text="Let me check",
        tool_calls=[
            ToolCall(id="tc_1", name="transport_play", input={}),
            ToolCall(id="tc_2", name="mixer_set_volume", input={"track": 1, "volume": 0.5}),
        ],
    )
    content = Orchestrator._build_assistant_content(resp)
    assert len(content) == 3
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "tool_use"
    assert content[1]["name"] == "transport_play"
    assert content[2]["id"] == "tc_2"
    assert content[2]["input"] == {"track": 1, "volume": 0.5}


def test_build_assistant_content_no_text():
    resp = AgentResponse(
        text="",
        tool_calls=[ToolCall(id="tc_1", name="get_daw_state", input={})],
    )
    content = Orchestrator._build_assistant_content(resp)
    # Empty text should not produce a text block
    assert len(content) == 1
    assert content[0]["type"] == "tool_use"


# ---------------------------------------------------------------------------
# _execute_tool_call
# ---------------------------------------------------------------------------


async def test_execute_tool_call_api_tool(orchestrator):
    """API tools should route through _execute_api_command."""
    tc = ToolCall(id="tc_1", name="transport_play", input={})
    mock_result = {"status": "ok", "result": {}}
    orchestrator._execute_api_command = AsyncMock(return_value=mock_result)
    result = await orchestrator._execute_tool_call(tc)
    assert result["status"] == "ok"
    orchestrator._execute_api_command.assert_awaited_once()


async def test_execute_tool_call_vision_tool(orchestrator):
    """Vision tools should route through _execute_vision_command."""
    tc = ToolCall(id="tc_1", name="vision_click_element", input={
        "plugin_window": "Serum",
        "element_description": "cutoff",
    })
    mock_result = {"status": "error", "error": "Vision layer execution not yet implemented"}
    orchestrator._execute_vision_command = AsyncMock(return_value=mock_result)
    result = await orchestrator._execute_tool_call(tc)
    orchestrator._execute_vision_command.assert_awaited_once()


async def test_execute_tool_call_unknown_tool(orchestrator):
    """Unknown tools should return an error result."""
    tc = ToolCall(id="tc_1", name="nonexistent_tool", input={})
    result = await orchestrator._execute_tool_call(tc)
    assert result["status"] == "error"
    assert "Unknown tool" in result["error"]


# ---------------------------------------------------------------------------
# _execute_api_command
# ---------------------------------------------------------------------------


async def test_execute_api_command_no_ws(orchestrator):
    """Should return error when not connected."""
    cmd = Command(module="transport", action="play")
    result = await orchestrator._execute_api_command(cmd)
    assert result["status"] == "error"
    assert "Not connected" in result["error"]


async def test_execute_api_command_success(orchestrator):
    """Should send command and parse response."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(return_value=json.dumps({"status": "ok", "result": {"volume": 0.8}}))
    orchestrator._ws = ws

    cmd = Command(module="mixer", action="getTrackVolume", params={"track": 1})
    result = await orchestrator._execute_api_command(cmd)
    assert result["status"] == "ok"
    assert result["result"]["volume"] == 0.8
    ws.send.assert_awaited_once()


async def test_execute_api_command_error_response(orchestrator):
    """Should handle error response from bridge."""
    ws = AsyncMock()
    ws.recv = AsyncMock(
        return_value=json.dumps({"status": "error", "error": "track not found"})
    )
    orchestrator._ws = ws

    cmd = Command(module="mixer", action="getTrackVolume", params={"track": 999})
    result = await orchestrator._execute_api_command(cmd)
    assert result["status"] == "error"
    assert result["error"] == "track not found"


async def test_execute_api_command_timeout(orchestrator):
    """Should handle timeout."""
    ws = AsyncMock()
    ws.recv = AsyncMock(side_effect=TimeoutError)
    orchestrator._ws = ws

    cmd = Command(module="transport", action="play")
    result = await orchestrator._execute_api_command(cmd)
    assert result["status"] == "error"
    assert "Timeout" in result["error"]


async def test_execute_api_command_exception(orchestrator):
    """Should handle unexpected exceptions."""
    ws = AsyncMock()
    ws.recv = AsyncMock(side_effect=ConnectionError("disconnected"))
    orchestrator._ws = ws

    cmd = Command(module="transport", action="play")
    result = await orchestrator._execute_api_command(cmd)
    assert result["status"] == "error"
    assert "disconnected" in result["error"]


# ---------------------------------------------------------------------------
# _execute_vision_command
# ---------------------------------------------------------------------------


async def test_execute_vision_command_not_implemented(orchestrator):
    """Vision commands should return not-yet-implemented error."""
    cmd = Command(module="vision", action="click")
    result = await orchestrator._execute_vision_command(cmd)
    assert result["status"] == "error"
    assert "not yet implemented" in result["error"]


# ---------------------------------------------------------------------------
# process_input – agentic loop
# ---------------------------------------------------------------------------


async def test_process_input_single_turn(orchestrator):
    """Claude returns text without tool calls → single iteration."""
    mock_response = AgentResponse(text="Done! I played the track.", tool_calls=[], stop_reason="end_turn")

    mock_client = AsyncMock()
    mock_client.send_messages = AsyncMock(return_value=mock_response)
    orchestrator._get_claude_client = MagicMock(return_value=mock_client)

    result = await orchestrator.process_input("Play the track")
    assert result == "Done! I played the track."
    mock_client.send_messages.assert_awaited_once()


async def test_process_input_tool_call_then_done(orchestrator):
    """Claude calls a tool, gets result, then returns text."""
    # First response: tool call
    tool_response = AgentResponse(
        text="Let me play that for you.",
        tool_calls=[ToolCall(id="tc_1", name="transport_play", input={})],
        stop_reason="tool_use",
    )
    # Second response: final text
    final_response = AgentResponse(
        text="I've started playback.", tool_calls=[], stop_reason="end_turn"
    )

    mock_client = AsyncMock()
    mock_client.send_messages = AsyncMock(side_effect=[tool_response, final_response])
    orchestrator._get_claude_client = MagicMock(return_value=mock_client)
    orchestrator._execute_tool_call = AsyncMock(return_value={"status": "ok", "result": {}})

    result = await orchestrator.process_input("Play")
    assert result == "I've started playback."
    assert mock_client.send_messages.await_count == 2
    orchestrator._execute_tool_call.assert_awaited_once()


async def test_process_input_multiple_tool_calls(orchestrator):
    """Claude returns multiple tool calls in one turn."""
    tool_response = AgentResponse(
        text="Checking state and setting volume.",
        tool_calls=[
            ToolCall(id="tc_1", name="get_daw_state", input={}),
            ToolCall(id="tc_2", name="mixer_set_volume", input={"track": 1, "volume": 0.5}),
        ],
        stop_reason="tool_use",
    )
    final_response = AgentResponse(text="Done.", tool_calls=[], stop_reason="end_turn")

    mock_client = AsyncMock()
    mock_client.send_messages = AsyncMock(side_effect=[tool_response, final_response])
    orchestrator._get_claude_client = MagicMock(return_value=mock_client)
    orchestrator._execute_tool_call = AsyncMock(return_value={"status": "ok", "result": {}})

    result = await orchestrator.process_input("Set volume")
    assert result == "Done."
    assert orchestrator._execute_tool_call.await_count == 2


async def test_process_input_max_iterations_guard(orchestrator):
    """Should stop after MAX_AGENT_ITERATIONS even if Claude keeps calling tools."""
    # Always return a tool call
    tool_response = AgentResponse(
        text="",
        tool_calls=[ToolCall(id="tc_loop", name="get_daw_state", input={})],
        stop_reason="tool_use",
    )

    mock_client = AsyncMock()
    mock_client.send_messages = AsyncMock(return_value=tool_response)
    orchestrator._get_claude_client = MagicMock(return_value=mock_client)
    orchestrator._execute_tool_call = AsyncMock(return_value={"status": "ok", "result": {}})

    result = await orchestrator.process_input("Loop forever")
    assert "maximum number of steps" in result
    assert mock_client.send_messages.await_count == MAX_AGENT_ITERATIONS


async def test_process_input_max_iterations_with_text(orchestrator):
    """If the last response has text when hitting max iterations, use it."""
    tool_response = AgentResponse(
        text="Still working...",
        tool_calls=[ToolCall(id="tc_1", name="get_daw_state", input={})],
        stop_reason="tool_use",
    )

    mock_client = AsyncMock()
    mock_client.send_messages = AsyncMock(return_value=tool_response)
    orchestrator._get_claude_client = MagicMock(return_value=mock_client)
    orchestrator._execute_tool_call = AsyncMock(return_value={"status": "ok", "result": {}})

    result = await orchestrator.process_input("Keep trying")
    assert result == "Still working..."


async def test_process_input_conversation_history_accumulates(orchestrator):
    """Verify that conversation history grows with each iteration."""
    call_count = 0
    captured_messages = []

    async def capture_messages(messages, tools, **kwargs):
        nonlocal call_count
        captured_messages.append(len(messages))
        call_count += 1
        if call_count == 1:
            return AgentResponse(
                text="Calling tool",
                tool_calls=[ToolCall(id="tc_1", name="transport_play", input={})],
                stop_reason="tool_use",
            )
        return AgentResponse(text="All done", tool_calls=[], stop_reason="end_turn")

    mock_client = AsyncMock()
    mock_client.send_messages = AsyncMock(side_effect=capture_messages)
    orchestrator._get_claude_client = MagicMock(return_value=mock_client)
    orchestrator._execute_tool_call = AsyncMock(return_value={"status": "ok", "result": {}})

    await orchestrator.process_input("Test")
    # First call: 1 message (user)
    assert captured_messages[0] == 1
    # Second call: 3 messages (user, assistant, user with tool_results)
    assert captured_messages[1] == 3


async def test_process_input_tool_error_fed_back(orchestrator):
    """Tool errors should be fed back to Claude."""
    tool_response = AgentResponse(
        text="",
        tool_calls=[ToolCall(id="tc_1", name="transport_play", input={})],
        stop_reason="tool_use",
    )
    final_response = AgentResponse(
        text="The command failed.", tool_calls=[], stop_reason="end_turn"
    )

    mock_client = AsyncMock()
    mock_client.send_messages = AsyncMock(side_effect=[tool_response, final_response])
    orchestrator._get_claude_client = MagicMock(return_value=mock_client)
    orchestrator._execute_tool_call = AsyncMock(
        return_value={"status": "error", "error": "Not connected"}
    )

    result = await orchestrator.process_input("Play")
    assert result == "The command failed."


async def test_process_input_done_dot_fallback(orchestrator):
    """Empty text and no tool calls should return 'Done.'."""
    mock_response = AgentResponse(text="", tool_calls=[], stop_reason="end_turn")

    mock_client = AsyncMock()
    mock_client.send_messages = AsyncMock(return_value=mock_response)
    orchestrator._get_claude_client = MagicMock(return_value=mock_client)

    result = await orchestrator.process_input("Test")
    assert result == "Done."


# ---------------------------------------------------------------------------
# _get_claude_client
# ---------------------------------------------------------------------------


def test_get_claude_client_returns_claude(orchestrator):
    """Should return a ClaudeClient from the router."""
    with patch("dawmind.orchestrator.ModelRouter") as MockRouter:
        from dawmind.llm.claude import ClaudeClient

        mock_client = MagicMock(spec=ClaudeClient)
        mock_router = MagicMock()
        mock_router.route.return_value = mock_client
        orchestrator._router = mock_router

        client = orchestrator._get_claude_client()
        assert client is mock_client


def test_get_claude_client_fallback(orchestrator):
    """Should create a ClaudeClient if router returns non-Claude client."""
    from dawmind.llm.claude import ClaudeClient

    mock_router = MagicMock()
    mock_router.route.return_value = MagicMock()  # Not a ClaudeClient instance
    orchestrator._router = mock_router

    # The isinstance check in _get_claude_client will fail for a plain MagicMock,
    # so it should fall back to creating a new ClaudeClient.
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic"):
        client = orchestrator._get_claude_client()
        assert isinstance(client, ClaudeClient)


# ---------------------------------------------------------------------------
# Legacy step-based execution
# ---------------------------------------------------------------------------


async def test_execute_api_step_no_command(orchestrator):
    """Step with no command should set error."""
    step = Step(description="No cmd", layer=ActionLayer.API)
    result = await orchestrator._execute_api_step(step)
    assert step.error == "No command specified"
    assert result == {}


async def test_execute_api_step_success(orchestrator):
    """Successful step execution should mark step completed."""
    cmd = Command(module="transport", action="play")
    step = Step(description="Play", layer=ActionLayer.API, command=cmd)
    orchestrator._execute_api_command = AsyncMock(
        return_value={"status": "ok", "result": {"playing": True}}
    )

    await orchestrator._execute_api_step(step)
    assert step.completed is True
    assert step.result == {"playing": True}


async def test_execute_api_step_error(orchestrator):
    """Failed step execution should set error string."""
    cmd = Command(module="mixer", action="setVolume")
    step = Step(description="Set vol", layer=ActionLayer.API, command=cmd)
    orchestrator._execute_api_command = AsyncMock(
        return_value={"status": "error", "error": "out of range"}
    )

    await orchestrator._execute_api_step(step)
    assert step.completed is False
    assert step.error == "out of range"


async def test_execute_vision_step_not_implemented(orchestrator):
    """Vision steps should return not-implemented error."""
    step = Step(description="Click something", layer=ActionLayer.VISION)
    result = await orchestrator._execute_vision_step(step)
    assert step.error == "Vision layer not yet implemented"
    assert result == {}


# ---------------------------------------------------------------------------
# connect / disconnect (mocked WebSocket)
# ---------------------------------------------------------------------------


async def test_connect_and_disconnect(orchestrator):
    """Test connect/disconnect lifecycle with mocked WebSocket."""
    mock_ws = AsyncMock()
    with patch("dawmind.orchestrator.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_ws
        with patch("dawmind.orchestrator.asyncio.create_task"):
            await orchestrator.connect()
            assert orchestrator._ws is mock_ws

    await orchestrator.disconnect()
    mock_ws.close.assert_awaited_once()
    assert orchestrator._ws is None


async def test_disconnect_when_not_connected(orchestrator):
    """Disconnecting when not connected should be a no-op."""
    await orchestrator.disconnect()
    assert orchestrator._ws is None
