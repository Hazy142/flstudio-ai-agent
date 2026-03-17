"""Tests for the Claude client with tool-use support."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dawmind.config import DAWMindConfig
from dawmind.llm.claude import (
    SYSTEM_PROMPT,
    AgentResponse,
    ClaudeClient,
    ToolCall,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config():
    return DAWMindConfig()


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


def test_tool_call_defaults():
    tc = ToolCall(id="tc_1", name="transport_play")
    assert tc.id == "tc_1"
    assert tc.name == "transport_play"
    assert tc.input == {}


def test_tool_call_with_input():
    tc = ToolCall(id="tc_2", name="mixer_set_volume", input={"track": 1, "volume": 0.8})
    assert tc.input["track"] == 1
    assert tc.input["volume"] == 0.8


def test_agent_response_defaults():
    resp = AgentResponse()
    assert resp.text == ""
    assert resp.tool_calls == []
    assert resp.stop_reason == ""


def test_agent_response_with_data():
    tc = ToolCall(id="tc_1", name="transport_play")
    resp = AgentResponse(text="Playing now", tool_calls=[tc], stop_reason="end_turn")
    assert resp.text == "Playing now"
    assert len(resp.tool_calls) == 1
    assert resp.stop_reason == "end_turn"


def test_agent_response_multiple_tool_calls():
    tcs = [
        ToolCall(id="tc_1", name="get_daw_state"),
        ToolCall(id="tc_2", name="mixer_set_volume", input={"track": 1, "volume": 0.5}),
    ]
    resp = AgentResponse(text="", tool_calls=tcs, stop_reason="tool_use")
    assert len(resp.tool_calls) == 2
    assert resp.tool_calls[1].name == "mixer_set_volume"


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def test_system_prompt_contains_domain_knowledge():
    assert "DAWMind" in SYSTEM_PROMPT
    assert "FL Studio" in SYSTEM_PROMPT


def test_system_prompt_contains_volume_scale():
    assert "0.8" in SYSTEM_PROMPT
    assert "0 dB" in SYSTEM_PROMPT or "0dB" in SYSTEM_PROMPT


def test_system_prompt_contains_mixer_layout():
    assert "Track 0 = Master" in SYSTEM_PROMPT
    assert "125" in SYSTEM_PROMPT


def test_system_prompt_contains_tool_categories():
    assert "Transport" in SYSTEM_PROMPT
    assert "Mixer" in SYSTEM_PROMPT
    assert "Channel" in SYSTEM_PROMPT or "Channels" in SYSTEM_PROMPT
    assert "Plugin" in SYSTEM_PROMPT or "Plugins" in SYSTEM_PROMPT
    assert "Vision" in SYSTEM_PROMPT


def test_system_prompt_contains_rules():
    assert "prefer API tools" in SYSTEM_PROMPT
    assert "inspect state" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# ClaudeClient.__init__
# ---------------------------------------------------------------------------


def test_client_init(config):
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        client = ClaudeClient(config)
        assert client._model == config.llm.planning_model
        MockAnthropic.assert_called_once()


# ---------------------------------------------------------------------------
# ClaudeClient.complete
# ---------------------------------------------------------------------------


async def test_complete_basic(config):
    """complete() should return text from Claude."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        # Create mock response
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello from Claude"

        mock_response = MagicMock()
        mock_response.content = [text_block]

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        result = await client.complete("Test prompt")
        assert result == "Hello from Claude"


async def test_complete_with_tools(config):
    """complete() should pass tools to the API."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "ok"

        mock_response = MagicMock()
        mock_response.content = [text_block]

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        tools = [{"name": "test_tool", "description": "A test", "input_schema": {}}]
        result = await client.complete("Test", tools=tools)

        call_kwargs = mock_messages.create.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["tools"] == tools


async def test_complete_uses_default_system_prompt(config):
    """complete() should use SYSTEM_PROMPT when no system override given."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "ok"

        mock_response = MagicMock()
        mock_response.content = [text_block]

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        await client.complete("Test")

        call_kwargs = mock_messages.create.call_args[1]
        assert call_kwargs["system"] == SYSTEM_PROMPT


async def test_complete_custom_system_prompt(config):
    """complete() should use custom system prompt when provided."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "ok"

        mock_response = MagicMock()
        mock_response.content = [text_block]

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        await client.complete("Test", system="Custom system")

        call_kwargs = mock_messages.create.call_args[1]
        assert call_kwargs["system"] == "Custom system"


async def test_complete_api_error(config):
    """complete() should raise on API errors."""
    import anthropic as anthropic_mod

    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(
            side_effect=anthropic_mod.APIError(
                message="rate limit",
                request=MagicMock(),
                body=None,
            )
        )
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        with pytest.raises(anthropic_mod.APIError):
            await client.complete("Test")


# ---------------------------------------------------------------------------
# ClaudeClient.complete_with_tools
# ---------------------------------------------------------------------------


async def test_complete_with_tools_returns_text_and_calls(config):
    """Should parse both text and tool_use blocks."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Let me check"

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "transport_play"
        tool_block.input = {}

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        tools = [{"name": "transport_play", "description": "Play", "input_schema": {}}]
        text, calls = await client.complete_with_tools("Play", tools)

        assert text == "Let me check"
        assert len(calls) == 1
        assert calls[0]["name"] == "transport_play"


async def test_complete_with_tools_no_tool_calls(config):
    """Should return empty tool_calls when Claude doesn't use tools."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "No tools needed"

        mock_response = MagicMock()
        mock_response.content = [text_block]

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        tools = [{"name": "test", "description": "test", "input_schema": {}}]
        text, calls = await client.complete_with_tools("Test", tools)

        assert text == "No tools needed"
        assert calls == []


# ---------------------------------------------------------------------------
# ClaudeClient.send_messages
# ---------------------------------------------------------------------------


async def test_send_messages_text_only(config):
    """Should parse a text-only response into AgentResponse."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "All done"

        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        messages = [{"role": "user", "content": "Test"}]
        tools = []

        resp = await client.send_messages(messages, tools)
        assert isinstance(resp, AgentResponse)
        assert resp.text == "All done"
        assert resp.tool_calls == []
        assert resp.stop_reason == "end_turn"


async def test_send_messages_with_tool_calls(config):
    """Should parse tool_use blocks into ToolCall objects."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Calling tool"

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tc_abc"
        tool_block.name = "mixer_set_volume"
        tool_block.input = {"track": 5, "volume": 0.6}

        mock_response = MagicMock()
        mock_response.content = [text_block, tool_block]
        mock_response.stop_reason = "tool_use"

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        messages = [{"role": "user", "content": "Set volume"}]
        tools = [{"name": "mixer_set_volume"}]

        resp = await client.send_messages(messages, tools)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "tc_abc"
        assert resp.tool_calls[0].name == "mixer_set_volume"
        assert resp.tool_calls[0].input["track"] == 5
        assert resp.stop_reason == "tool_use"


async def test_send_messages_multiple_text_blocks(config):
    """Multiple text blocks should be joined with newlines."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        block1 = MagicMock()
        block1.type = "text"
        block1.text = "Line one"

        block2 = MagicMock()
        block2.type = "text"
        block2.text = "Line two"

        mock_response = MagicMock()
        mock_response.content = [block1, block2]
        mock_response.stop_reason = "end_turn"

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        resp = await client.send_messages([{"role": "user", "content": "Test"}], [])
        assert resp.text == "Line one\nLine two"


async def test_send_messages_passes_system(config):
    """send_messages should forward the system prompt."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "ok"

        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        await client.send_messages(
            [{"role": "user", "content": "Test"}],
            [],
            system="Custom system",
        )
        call_kwargs = mock_messages.create.call_args[1]
        assert call_kwargs["system"] == "Custom system"


async def test_send_messages_api_error(config):
    """send_messages should raise on API errors."""
    import anthropic as anthropic_mod

    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(
            side_effect=anthropic_mod.APIError(
                message="server error",
                request=MagicMock(),
                body=None,
            )
        )
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        with pytest.raises(anthropic_mod.APIError):
            await client.send_messages([{"role": "user", "content": "Test"}], [])


async def test_send_messages_none_stop_reason(config):
    """Should handle None stop_reason gracefully."""
    with patch("dawmind.llm.claude.anthropic.AsyncAnthropic") as MockAnthropic:
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "ok"

        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_response.stop_reason = None

        mock_messages = AsyncMock()
        mock_messages.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        MockAnthropic.return_value = mock_client

        client = ClaudeClient(config)
        resp = await client.send_messages([{"role": "user", "content": "Test"}], [])
        assert resp.stop_reason == ""
