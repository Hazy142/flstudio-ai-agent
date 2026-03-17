"""IPC protocol definitions for communication with FL Studio."""

from __future__ import annotations

import json
import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class CommandLayer(StrEnum):
    API = "api"
    VISION = "vision"


class CommandStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


class Command(BaseModel):
    """A command sent to FL Studio."""

    id: str = Field(default_factory=lambda: f"cmd_{uuid.uuid4().hex[:8]}")
    layer: CommandLayer = CommandLayer.API
    module: str = ""
    action: str = ""
    params: dict = Field(default_factory=dict)

    def to_json_line(self) -> str:
        """Serialize to a single JSON line for pipe transport."""
        return json.dumps(self.model_dump()) + "\n"


class CommandResponse(BaseModel):
    """A response received from FL Studio."""

    id: str = ""
    status: CommandStatus = CommandStatus.OK
    result: dict = Field(default_factory=dict)
    error: str = ""

    @classmethod
    def from_json(cls, data: str | bytes) -> CommandResponse:
        """Deserialize from JSON."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return cls.model_validate(json.loads(data))


class StateUpdate(BaseModel):
    """A state broadcast from FL Studio."""

    type: str = "state"
    data: dict = Field(default_factory=dict)

    @classmethod
    def from_json(cls, data: str | bytes) -> StateUpdate:
        """Deserialize from JSON."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return cls.model_validate(json.loads(data))


def create_command(module: str, action: str, **params: object) -> Command:
    """Factory for creating FL Studio API commands."""
    return Command(module=module, action=action, params=params)
