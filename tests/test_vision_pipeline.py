"""Tests for the vision reasoning pipeline."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from dawmind.config import DAWMindConfig
from dawmind.vision_layer.parser import ParseResult, UIElement
from dawmind.vision_layer.reasoning import VisionAction, VisionReasoner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_screenshot(width: int = 100, height: int = 100) -> bytes:
    """Create a minimal PNG image in memory."""
    img = Image.new("RGB", (width, height), color="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_parse_result(n_elements: int = 3) -> ParseResult:
    """Create a ParseResult with N dummy UI elements."""
    elements = []
    for i in range(n_elements):
        elements.append(
            UIElement(
                label=f"Element_{i}",
                element_type="button",
                bbox=[10.0 * i, 10.0 * i, 10.0 * i + 50, 10.0 * i + 50],
                confidence=0.95,
                center_x=10.0 * i + 25,
                center_y=10.0 * i + 25,
            )
        )
    return ParseResult(elements=elements, raw_response={"elements": []})


# ---------------------------------------------------------------------------
# VisionAction dataclass
# ---------------------------------------------------------------------------


def test_vision_action_defaults():
    action = VisionAction(type="click", target="button")
    assert action.x == 0
    assert action.y == 0
    assert action.x2 == 0
    assert action.y2 == 0
    assert action.direction == ""
    assert action.amount == 0
    assert action.text == ""


def test_vision_action_click():
    action = VisionAction(type="click", target="Play button", x=100, y=200)
    assert action.type == "click"
    assert action.x == 100
    assert action.y == 200


def test_vision_action_drag():
    action = VisionAction(type="drag", target="slider", x=10, y=20, x2=100, y2=20)
    assert action.x2 == 100
    assert action.y2 == 20


def test_vision_action_drag_vertical():
    action = VisionAction(
        type="drag_vertical", target="knob", x=50, y=50, direction="up", amount=30
    )
    assert action.direction == "up"
    assert action.amount == 30


def test_vision_action_type_text():
    action = VisionAction(type="type", target="input field", text="hello world")
    assert action.text == "hello world"


def test_vision_action_scroll():
    action = VisionAction(type="scroll", target="list", direction="down", amount=3)
    assert action.direction == "down"
    assert action.amount == 3


# ---------------------------------------------------------------------------
# VisionReasoner._build_actions
# ---------------------------------------------------------------------------


def test_build_actions_click():
    result = {"actions": [{"type": "click", "target": "play btn", "x": 100, "y": 50}]}
    actions = VisionReasoner._build_actions(result)
    assert len(actions) == 1
    assert actions[0].type == "click"
    assert actions[0].x == 100
    assert actions[0].y == 50


def test_build_actions_drag():
    result = {
        "actions": [
            {
                "type": "drag",
                "target": "slider",
                "x": 10,
                "y": 20,
                "details": {"x2": 200, "y2": 20},
            }
        ]
    }
    actions = VisionReasoner._build_actions(result)
    assert actions[0].x2 == 200
    assert actions[0].y2 == 20


def test_build_actions_drag_with_toplevel_x2():
    """x2/y2 can also be at top level instead of details."""
    result = {
        "actions": [
            {"type": "drag", "target": "fader", "x": 10, "y": 20, "x2": 150, "y2": 20}
        ]
    }
    actions = VisionReasoner._build_actions(result)
    assert actions[0].x2 == 150


def test_build_actions_drag_vertical():
    result = {
        "actions": [
            {
                "type": "drag_vertical",
                "target": "cutoff knob",
                "x": 50,
                "y": 50,
                "details": {"direction": "up", "amount": 30},
            }
        ]
    }
    actions = VisionReasoner._build_actions(result)
    assert actions[0].direction == "up"
    assert actions[0].amount == 30


def test_build_actions_scroll():
    result = {
        "actions": [
            {
                "type": "SCROLL",
                "target": "preset list",
                "x": 100,
                "y": 200,
                "details": {"direction": "down", "amount": 5},
            }
        ]
    }
    actions = VisionReasoner._build_actions(result)
    assert actions[0].type == "scroll"  # lowercase
    assert actions[0].direction == "down"
    assert actions[0].amount == 5


def test_build_actions_type():
    result = {
        "actions": [
            {
                "type": "type",
                "target": "search box",
                "x": 200,
                "y": 30,
                "details": {"text": "Saw Wave"},
            }
        ]
    }
    actions = VisionReasoner._build_actions(result)
    assert actions[0].text == "Saw Wave"


def test_build_actions_empty():
    result = {"actions": []}
    actions = VisionReasoner._build_actions(result)
    assert actions == []


def test_build_actions_no_actions_key():
    result = {"observations": "I see FL Studio"}
    actions = VisionReasoner._build_actions(result)
    assert actions == []


def test_build_actions_multiple():
    result = {
        "actions": [
            {"type": "click", "target": "menu", "x": 10, "y": 10},
            {"type": "click", "target": "option", "x": 20, "y": 30},
            {"type": "type", "target": "field", "x": 0, "y": 0, "details": {"text": "hi"}},
        ]
    }
    actions = VisionReasoner._build_actions(result)
    assert len(actions) == 3


def test_build_actions_string_details_ignored():
    """If details is a string instead of dict, it should be treated as empty."""
    result = {
        "actions": [{"type": "drag", "target": "knob", "x": 10, "y": 10, "details": "bad data"}]
    }
    actions = VisionReasoner._build_actions(result)
    assert actions[0].x2 == 0  # defaults since details was invalid


# ---------------------------------------------------------------------------
# VisionReasoner._annotate_screenshot
# ---------------------------------------------------------------------------


def test_annotate_screenshot_no_elements():
    """Should return original screenshot when no elements detected."""
    screenshot = _make_screenshot()
    result = ParseResult(elements=[])
    annotated = VisionReasoner._annotate_screenshot(screenshot, result)
    assert annotated == screenshot


def test_annotate_screenshot_with_elements():
    """Should return a different (annotated) image when elements present."""
    screenshot = _make_screenshot(200, 200)
    parse_result = _make_parse_result(2)
    annotated = VisionReasoner._annotate_screenshot(screenshot, parse_result)
    # Annotated image should be different from original
    assert annotated != screenshot
    # Should still be valid PNG
    img = Image.open(io.BytesIO(annotated))
    assert img.format == "PNG"
    assert img.size == (200, 200)


def test_annotate_screenshot_skips_short_bbox():
    """Elements with bbox < 4 values should be skipped."""
    screenshot = _make_screenshot(100, 100)
    elements = [UIElement(label="Bad", bbox=[10.0, 20.0], confidence=0.9)]
    parse_result = ParseResult(elements=elements)
    # Should not raise
    annotated = VisionReasoner._annotate_screenshot(screenshot, parse_result)
    assert len(annotated) > 0


# ---------------------------------------------------------------------------
# VisionReasoner.plan_action (mocked)
# ---------------------------------------------------------------------------


@pytest.fixture()
def config():
    return DAWMindConfig()


async def test_plan_action_with_pre_parsed(config):
    """plan_action with pre-parsed elements should skip OmniParser."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        mock_gemini = MagicMock()
        mock_gemini.analyze_screenshot = AsyncMock(
            return_value={
                "observations": "I see the play button",
                "actions": [{"type": "click", "target": "play", "x": 100, "y": 50}],
            }
        )
        MockGemini.return_value = mock_gemini
        mock_parser = MagicMock()
        MockParser.return_value = mock_parser

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot()
        parse_result = _make_parse_result(2)

        actions = await reasoner.plan_action(screenshot, "Click play", parse_result)
        assert len(actions) == 1
        assert actions[0].type == "click"
        # OmniParser.parse should NOT have been called since we passed pre-parsed
        mock_parser.parse.assert_not_called()


async def test_plan_action_calls_omniparser(config):
    """plan_action without pre-parsed elements should call OmniParser."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        mock_gemini = MagicMock()
        mock_gemini.analyze_screenshot = AsyncMock(
            return_value={"observations": "Screen", "actions": []}
        )
        MockGemini.return_value = mock_gemini

        mock_parser = MagicMock()
        mock_parser.parse = AsyncMock(return_value=ParseResult(elements=[]))
        MockParser.return_value = mock_parser

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot()

        await reasoner.plan_action(screenshot, "Do something")
        mock_parser.parse.assert_awaited_once_with(screenshot)


async def test_plan_action_sends_annotated_to_gemini(config):
    """Annotated screenshot should be sent to Gemini, not the raw one."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        captured_image = None

        async def capture_analyze(*, image, task, parsed_elements):
            nonlocal captured_image
            captured_image = image
            return {"observations": "Annotated", "actions": []}

        mock_gemini = MagicMock()
        mock_gemini.analyze_screenshot = AsyncMock(side_effect=capture_analyze)
        MockGemini.return_value = mock_gemini
        MockParser.return_value = MagicMock()

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot(200, 200)
        parse_result = _make_parse_result(2)

        await reasoner.plan_action(screenshot, "Test", parse_result)
        # The annotated image is different from the raw screenshot
        assert captured_image is not None
        assert captured_image != screenshot


async def test_plan_action_passes_elements_info(config):
    """parsed_elements should be sent to Gemini when elements exist."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        captured_elements = None

        async def capture_analyze(*, image, task, parsed_elements):
            nonlocal captured_elements
            captured_elements = parsed_elements
            return {"actions": []}

        mock_gemini = MagicMock()
        mock_gemini.analyze_screenshot = AsyncMock(side_effect=capture_analyze)
        MockGemini.return_value = mock_gemini
        MockParser.return_value = MagicMock()

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot()
        parse_result = _make_parse_result(2)

        await reasoner.plan_action(screenshot, "Test", parse_result)
        assert captured_elements is not None
        assert len(captured_elements) == 2
        assert captured_elements[0]["id"] == 0
        assert captured_elements[0]["label"] == "Element_0"
        assert "center" in captured_elements[0]
        assert "bbox" in captured_elements[0]


async def test_plan_action_no_elements_passes_none(config):
    """When no elements detected, parsed_elements should be None."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        captured_elements = "SENTINEL"

        async def capture_analyze(*, image, task, parsed_elements):
            nonlocal captured_elements
            captured_elements = parsed_elements
            return {"actions": []}

        mock_gemini = MagicMock()
        mock_gemini.analyze_screenshot = AsyncMock(side_effect=capture_analyze)
        MockGemini.return_value = mock_gemini
        MockParser.return_value = MagicMock()

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot()
        empty_result = ParseResult(elements=[])

        await reasoner.plan_action(screenshot, "Test", empty_result)
        assert captured_elements is None


# ---------------------------------------------------------------------------
# VisionReasoner.find_element (mocked)
# ---------------------------------------------------------------------------


async def test_find_element_found(config):
    """Should return matching UIElement."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        mock_gemini = MagicMock()
        mock_gemini.complete = AsyncMock(return_value="Play Button")
        MockGemini.return_value = mock_gemini
        MockParser.return_value = MagicMock()

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot()
        elements = [
            UIElement(label="Play Button", element_type="button", confidence=0.9),
            UIElement(label="Stop Button", element_type="button", confidence=0.9),
        ]
        parse_result = ParseResult(elements=elements)

        result = await reasoner.find_element(screenshot, "play button", parse_result)
        assert result is not None
        assert result.label == "Play Button"


async def test_find_element_not_found(config):
    """Should return None when no matching element."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        mock_gemini = MagicMock()
        mock_gemini.complete = AsyncMock(return_value="Nonexistent Widget")
        MockGemini.return_value = mock_gemini
        MockParser.return_value = MagicMock()

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot()
        elements = [UIElement(label="Play Button", element_type="button", confidence=0.9)]
        parse_result = ParseResult(elements=elements)

        result = await reasoner.find_element(screenshot, "something else", parse_result)
        assert result is None


async def test_find_element_no_elements(config):
    """Should return None when parse result has no elements."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        MockGemini.return_value = MagicMock()
        MockParser.return_value = MagicMock()

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot()
        parse_result = ParseResult(elements=[])

        result = await reasoner.find_element(screenshot, "play", parse_result)
        assert result is None


async def test_find_element_calls_parser_if_no_result(config):
    """Should call OmniParser when no pre-parsed result given."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        mock_gemini = MagicMock()
        mock_gemini.complete = AsyncMock(return_value="Element_0")
        MockGemini.return_value = mock_gemini

        mock_parser = MagicMock()
        mock_parser.parse = AsyncMock(return_value=_make_parse_result(1))
        MockParser.return_value = mock_parser

        reasoner = VisionReasoner(config)
        screenshot = _make_screenshot()

        result = await reasoner.find_element(screenshot, "element 0")
        mock_parser.parse.assert_awaited_once()
        assert result is not None


# ---------------------------------------------------------------------------
# VisionReasoner.close
# ---------------------------------------------------------------------------


async def test_close(config):
    """close() should close the OmniParser client."""
    with patch("dawmind.vision_layer.reasoning.GeminiClient") as MockGemini, \
         patch("dawmind.vision_layer.reasoning.OmniParser") as MockParser:
        MockGemini.return_value = MagicMock()
        mock_parser = MagicMock()
        mock_parser.close = AsyncMock()
        MockParser.return_value = mock_parser

        reasoner = VisionReasoner(config)
        await reasoner.close()
        mock_parser.close.assert_awaited_once()
