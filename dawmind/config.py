"""Configuration loading for DAWMind."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import toml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATHS = [
    Path("config/dawmind.toml"),
    Path("dawmind.toml"),
    Path.home() / ".config" / "dawmind" / "dawmind.toml",
]


@dataclass
class FLStudioConfig:
    pipe_name: str = "dawmind"
    state_poll_interval_ms: int = 500
    script_path: str = "~/Documents/Image-Line/FL Studio/Settings/Hardware/DAWMind/"


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    ws_port: int = 9500
    api_port: int = 9501


@dataclass
class AnthropicConfig:
    api_key: str = ""


@dataclass
class GoogleConfig:
    api_key: str = ""
    project_id: str = ""
    region: str = "europe-west1"


@dataclass
class OpenAIConfig:
    api_key: str = ""


@dataclass
class LLMConfig:
    planning_model: str = "claude-sonnet-4-20250514"
    vision_model: str = "gemini-2.5-flash"
    local_model: str = "llama3"
    router_strategy: str = "auto"
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)


@dataclass
class VisionConfig:
    omniparser_endpoint: str = "http://localhost:8080/parse"
    screenshot_cache_seconds: float = 2.0
    capture_monitor: int = 0
    verification_enabled: bool = True


@dataclass
class VoiceConfig:
    enabled: bool = False
    whisper_model: str = "base"


@dataclass
class GeneralConfig:
    name: str = "DAWMind"
    version: str = "0.1.0"
    log_level: str = "INFO"


@dataclass
class DAWMindConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    fl_studio: FLStudioConfig = field(default_factory=FLStudioConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)


def _apply_dict(dc: object, data: dict) -> None:
    """Recursively apply a dict to a dataclass instance."""
    for key, value in data.items():
        if not hasattr(dc, key):
            continue
        current = getattr(dc, key)
        if isinstance(value, dict) and hasattr(current, "__dataclass_fields__"):
            _apply_dict(current, value)
        else:
            setattr(dc, key, value)


def _inject_env_keys(config: DAWMindConfig) -> None:
    """Inject API keys from environment variables."""
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        config.llm.anthropic.api_key = key
    if key := os.environ.get("GOOGLE_API_KEY"):
        config.llm.google.api_key = key
    if key := os.environ.get("OPENAI_API_KEY"):
        config.llm.openai.api_key = key


def load_config(path: str | Path | None = None) -> DAWMindConfig:
    """Load configuration from a TOML file.

    Searches default paths if no explicit path is given.  API keys are
    always overlaid from environment variables when present.
    """
    config = DAWMindConfig()

    config_path: Path | None = None
    if path is not None:
        config_path = Path(path)
    else:
        for candidate in _DEFAULT_CONFIG_PATHS:
            if candidate.exists():
                config_path = candidate
                break

    if config_path and config_path.exists():
        logger.info("Loading config from %s", config_path)
        data = toml.load(config_path)
        _apply_dict(config, data)
    else:
        logger.warning("No config file found, using defaults")

    _inject_env_keys(config)

    logging.basicConfig(
        level=getattr(logging, config.general.log_level, logging.INFO),
        format="%(asctime)s | %(name)-24s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    return config
