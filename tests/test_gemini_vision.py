"""Tests for the Gemini vision client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dawmind.config import DAWMindConfig
from dawmind.llm.gemini_client import (
    VISION_SYSTEM_PROMPT,
    GeminiClient,
    _DEFAULT_MAX_RETRIES,
    _DEFAULT_RETRY_DELAY,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config():
    return DAWMindConfig()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_vision_system_prompt_content():
    assert "DAWMind" in VISION_SYSTEM_PROMPT
    assert "FL Studio" in VISION_SYSTEM_PROMPT
    assert "CLICK" in VISION_SYSTEM_PROMPT
    assert "DRAG" in VISION_SYSTEM_PROMPT


def test_default_retry_constants():
    assert _DEFAULT_MAX_RETRIES == 3
    assert _DEFAULT_RETRY_DELAY == 1.0


# ---------------------------------------------------------------------------
# GeminiClient.__init__
# ---------------------------------------------------------------------------


def test_client_init(config):
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = MagicMock()
        client = GeminiClient(config)
        assert client._model_name == config.llm.vision_model
        mock_genai.GenerativeModel.assert_called_once()


def test_client_init_with_api_key():
    config = DAWMindConfig()
    config.llm.google.api_key = "test-key"
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = MagicMock()
        GeminiClient(config)
        mock_genai.configure.assert_called_once_with(api_key="test-key")


def test_client_init_no_api_key(config):
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = MagicMock()
        GeminiClient(config)
        mock_genai.configure.assert_not_called()


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------


def test_parse_json_direct():
    """Valid JSON should be parsed directly."""
    text = '{"observations": "I see FL Studio", "actions": []}'
    result = GeminiClient._parse_json_response(text)
    assert result["observations"] == "I see FL Studio"
    assert result["actions"] == []


def test_parse_json_with_markdown_fences():
    """JSON wrapped in markdown code fences should be extracted."""
    text = '```json\n{"observations": "test", "actions": [{"type": "click"}]}\n```'
    result = GeminiClient._parse_json_response(text)
    assert result["observations"] == "test"
    assert len(result["actions"]) == 1


def test_parse_json_with_plain_fences():
    """JSON wrapped in plain fences (no json tag) should be extracted."""
    text = '```\n{"key": "value"}\n```'
    result = GeminiClient._parse_json_response(text)
    assert result["key"] == "value"


def test_parse_json_embedded_in_text():
    """JSON embedded in surrounding text should be extracted."""
    text = 'Here is the result:\n{"actions": [{"type": "click", "x": 100}]}\nThat is all.'
    result = GeminiClient._parse_json_response(text)
    assert len(result["actions"]) == 1


def test_parse_json_malformed_returns_fallback():
    """Completely malformed text should return fallback dict."""
    text = "This is not JSON at all, no braces anywhere"
    result = GeminiClient._parse_json_response(text)
    assert result["observations"] == text
    assert result["actions"] == []


def test_parse_json_invalid_json_in_fences():
    """Invalid JSON in fences should fall through to brace matching."""
    # The brace regex matches greedily from the first { to the last }, so
    # if the fence content is also brace-wrapped it gets captured too.
    # Test with fences that don't use braces for the invalid part.
    text = '```json\nnot json\n```\nSome text {"valid": true} end'
    result = GeminiClient._parse_json_response(text)
    assert result["valid"] is True


def test_parse_json_nested_objects():
    """Complex nested JSON should be parsed correctly."""
    data = {
        "observations": "Complex scene",
        "actions": [
            {
                "type": "drag",
                "target": "knob",
                "x": 50,
                "y": 100,
                "details": {"direction": "up", "amount": 30},
            }
        ],
    }
    text = json.dumps(data)
    result = GeminiClient._parse_json_response(text)
    assert result["actions"][0]["details"]["direction"] == "up"


def test_parse_json_empty_object():
    result = GeminiClient._parse_json_response("{}")
    assert result == {}


# ---------------------------------------------------------------------------
# GeminiClient.complete (mocked)
# ---------------------------------------------------------------------------


async def test_complete_text_only(config):
    """complete() with text-only prompt should work."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "I see the mixer"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        result = await client.complete("Describe the screen")
        assert result == "I see the mixer"


async def test_complete_with_images(config):
    """complete() should encode images as base64 inline_data."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "I see a DAW"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        fake_image = b"\x89PNG\r\n\x1a\nfake_image_data"
        result = await client.complete("What do you see?", images=[fake_image])
        assert result == "I see a DAW"

        # Verify the parts include an inline_data block
        call_args = mock_model.generate_content_async.call_args
        parts = call_args[0][0]
        assert any(
            isinstance(p, dict) and "inline_data" in p
            for p in parts
        )


async def test_complete_with_system_override(config):
    """complete() with system override should create a new model instance."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        # Default and override model
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        await client.complete("Test", system="Custom prompt")

        # Should have been called twice: once in __init__, once for override
        assert mock_genai.GenerativeModel.call_count == 2
        second_call = mock_genai.GenerativeModel.call_args_list[1]
        assert second_call[1]["system_instruction"] == "Custom prompt"


# ---------------------------------------------------------------------------
# GeminiClient._call_with_retry
# ---------------------------------------------------------------------------


async def test_call_with_retry_success_first_try(config):
    """Should return immediately on success."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "success"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        result = await client._call_with_retry(mock_model, ["test"])
        assert result == "success"
        assert mock_model.generate_content_async.await_count == 1


async def test_call_with_retry_transient_then_success(config):
    """Should retry on 429/500/503 errors and succeed."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_success = MagicMock()
        mock_success.text = "recovered"

        mock_model.generate_content_async = AsyncMock(
            side_effect=[
                Exception("429 Resource exhausted"),
                mock_success,
            ]
        )
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        with patch("dawmind.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock):
            result = await client._call_with_retry(mock_model, ["test"])
        assert result == "recovered"
        assert mock_model.generate_content_async.await_count == 2


async def test_call_with_retry_500_error(config):
    """500 errors should be retried."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_success = MagicMock()
        mock_success.text = "ok"

        mock_model.generate_content_async = AsyncMock(
            side_effect=[
                Exception("500 Internal Server Error"),
                mock_success,
            ]
        )
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        with patch("dawmind.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock):
            result = await client._call_with_retry(mock_model, ["test"])
        assert result == "ok"


async def test_call_with_retry_503_error(config):
    """503 errors should be retried."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_success = MagicMock()
        mock_success.text = "ok"

        mock_model.generate_content_async = AsyncMock(
            side_effect=[
                Exception("503 Service Unavailable"),
                mock_success,
            ]
        )
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        with patch("dawmind.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock):
            result = await client._call_with_retry(mock_model, ["test"])
        assert result == "ok"


async def test_call_with_retry_exhausted(config):
    """Should raise after max retries exhausted."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=Exception("429 Too Many Requests")
        )
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        with patch("dawmind.llm.gemini_client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="429"):
                await client._call_with_retry(mock_model, ["test"], max_retries=3)
        assert mock_model.generate_content_async.await_count == 3


async def test_call_with_retry_non_transient_raises_immediately(config):
    """Non-transient errors should raise immediately without retry."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(
            side_effect=Exception("Invalid API key")
        )
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        with pytest.raises(Exception, match="Invalid API key"):
            await client._call_with_retry(mock_model, ["test"])
        # Should only try once for non-transient errors
        assert mock_model.generate_content_async.await_count == 1


async def test_call_with_retry_exponential_backoff(config):
    """Verify exponential backoff delays."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_success = MagicMock()
        mock_success.text = "ok"

        mock_model.generate_content_async = AsyncMock(
            side_effect=[
                Exception("429 rate limit"),
                Exception("429 rate limit"),
                mock_success,
            ]
        )
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        sleep_calls = []

        async def capture_sleep(delay):
            sleep_calls.append(delay)

        with patch("dawmind.llm.gemini_client.asyncio.sleep", side_effect=capture_sleep):
            await client._call_with_retry(mock_model, ["test"])

        # delay = _DEFAULT_RETRY_DELAY * 2^attempt
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == _DEFAULT_RETRY_DELAY * 1   # 2^0 = 1
        assert sleep_calls[1] == _DEFAULT_RETRY_DELAY * 2   # 2^1 = 2


# ---------------------------------------------------------------------------
# GeminiClient.analyze_screenshot (mocked)
# ---------------------------------------------------------------------------


async def test_analyze_screenshot_basic(config):
    """analyze_screenshot should call complete and parse JSON."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        response_json = json.dumps({
            "observations": "I see a mixer",
            "actions": [{"type": "click", "target": "play", "x": 100, "y": 50}],
        })
        mock_response = MagicMock()
        mock_response.text = response_json
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        result = await client.analyze_screenshot(
            image=b"fake_png",
            task="Click the play button",
        )
        assert result["observations"] == "I see a mixer"
        assert len(result["actions"]) == 1
        assert result["actions"][0]["type"] == "click"


async def test_analyze_screenshot_with_parsed_elements(config):
    """analyze_screenshot should include parsed elements in the prompt."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        captured_parts = None

        async def capture_generate(parts):
            nonlocal captured_parts
            captured_parts = parts
            mock_resp = MagicMock()
            mock_resp.text = '{"observations": "ok", "actions": []}'
            return mock_resp

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(side_effect=capture_generate)
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        elements = [{"id": 0, "label": "Play", "type": "button"}]
        await client.analyze_screenshot(
            image=b"fake_png",
            task="Click play",
            parsed_elements=elements,
        )
        # The prompt (last part) should mention the elements
        prompt_text = captured_parts[-1]
        assert "Play" in prompt_text
        assert "OmniParser" in prompt_text


async def test_analyze_screenshot_no_parsed_elements(config):
    """analyze_screenshot without elements should not include element section."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        captured_parts = None

        async def capture_generate(parts):
            nonlocal captured_parts
            captured_parts = parts
            mock_resp = MagicMock()
            mock_resp.text = '{"observations": "ok", "actions": []}'
            return mock_resp

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(side_effect=capture_generate)
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        await client.analyze_screenshot(image=b"fake_png", task="Look around")
        prompt_text = captured_parts[-1]
        assert "OmniParser" not in prompt_text


async def test_analyze_screenshot_malformed_response(config):
    """Should return fallback dict when response is not valid JSON."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "I cannot parse this image properly"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        result = await client.analyze_screenshot(image=b"fake_png", task="test")
        assert "observations" in result
        assert result["actions"] == []


# ---------------------------------------------------------------------------
# GeminiClient.complete_sync
# ---------------------------------------------------------------------------


def test_complete_sync(config):
    """complete_sync should call the async complete under the hood."""
    with patch("dawmind.llm.gemini_client.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "sync result"
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_genai.GenerativeModel.return_value = mock_model

        client = GeminiClient(config)
        with patch("dawmind.llm.gemini_client.asyncio.get_event_loop") as mock_loop:
            mock_loop_instance = MagicMock()
            mock_loop_instance.run_until_complete.return_value = "sync result"
            mock_loop.return_value = mock_loop_instance

            result = client.complete_sync("Test prompt")
            assert result == "sync result"
            mock_loop_instance.run_until_complete.assert_called_once()
