"""PyAutoGUI action executor for vision-based GUI control."""

from __future__ import annotations

import logging
import time

import pyautogui

from dawmind.config import DAWMindConfig

logger = logging.getLogger(__name__)

# Safety: prevent pyautogui from moving to corners (failsafe)
pyautogui.FAILSAFE = True
# Default pause between actions
pyautogui.PAUSE = 0.1


class ActionExecutor:
    """Executes mouse/keyboard actions planned by the vision reasoner."""

    def __init__(self, config: DAWMindConfig) -> None:
        self._config = config

    def execute(self, action: dict) -> bool:
        """Execute a single action dict.

        Args:
            action: Action dict with 'type' and relevant parameters.

        Returns:
            True if the action was executed successfully.
        """
        action_type = action.get("type", "")

        try:
            match action_type:
                case "click":
                    return self._click(action)
                case "drag":
                    return self._drag(action)
                case "drag_vertical":
                    return self._drag_vertical(action)
                case "type":
                    return self._type_text(action)
                case "scroll":
                    return self._scroll(action)
                case "double_click":
                    return self._double_click(action)
                case "right_click":
                    return self._right_click(action)
                case _:
                    logger.warning("Unknown action type: %s", action_type)
                    return False
        except pyautogui.FailSafeException:
            logger.error("PyAutoGUI failsafe triggered – mouse moved to corner")
            return False
        except Exception as exc:
            logger.error("Action execution failed: %s", exc)
            return False

    def execute_sequence(self, actions: list[dict], delay: float = 0.2) -> list[bool]:
        """Execute a sequence of actions with delays between them.

        Returns a list of success/failure booleans.
        """
        results = []
        for action in actions:
            success = self.execute(action)
            results.append(success)
            if not success:
                logger.warning("Action failed, stopping sequence: %s", action)
                break
            time.sleep(delay)
        return results

    def _click(self, action: dict) -> bool:
        x, y = action["x"], action["y"]
        logger.debug("Click at (%d, %d)", x, y)
        pyautogui.click(x, y)
        return True

    def _double_click(self, action: dict) -> bool:
        x, y = action["x"], action["y"]
        logger.debug("Double-click at (%d, %d)", x, y)
        pyautogui.doubleClick(x, y)
        return True

    def _right_click(self, action: dict) -> bool:
        x, y = action["x"], action["y"]
        logger.debug("Right-click at (%d, %d)", x, y)
        pyautogui.rightClick(x, y)
        return True

    def _drag(self, action: dict) -> bool:
        x1, y1 = action["x1"], action["y1"]
        x2, y2 = action["x2"], action["y2"]
        duration = action.get("duration", 0.3)
        logger.debug("Drag from (%d,%d) to (%d,%d)", x1, y1, x2, y2)
        pyautogui.moveTo(x1, y1)
        pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
        return True

    def _drag_vertical(self, action: dict) -> bool:
        """Vertical drag for knob interaction.

        Most VST knobs respond to vertical mouse movement:
        drag up = increase value, drag down = decrease.
        """
        x, y = action["x"], action["y"]
        direction = action.get("direction", "up")
        amount = action.get("amount", 30)
        duration = action.get("duration", 0.3)

        dy = -amount if direction == "up" else amount
        logger.debug("Vertical drag at (%d,%d) direction=%s amount=%d", x, y, direction, amount)
        pyautogui.moveTo(x, y)
        pyautogui.drag(0, dy, duration=duration)
        return True

    def _type_text(self, action: dict) -> bool:
        text = action.get("text", "")
        interval = action.get("interval", 0.02)
        logger.debug("Typing: %s", text[:50])
        pyautogui.typewrite(text, interval=interval)
        return True

    def _scroll(self, action: dict) -> bool:
        x, y = action.get("x", 0), action.get("y", 0)
        direction = action.get("direction", "up")
        amount = action.get("amount", 3)
        clicks = amount if direction == "up" else -amount
        logger.debug("Scroll at (%d,%d) %s by %d", x, y, direction, amount)
        pyautogui.scroll(clicks, x=x, y=y)
        return True
