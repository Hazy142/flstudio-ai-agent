"""Pydantic models for the complete FL Studio DAW state."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TransportState(BaseModel):
    """Transport bar state."""

    playing: bool = False
    recording: bool = False
    tempo: float = 140.0
    time_signature_num: int = 4
    time_signature_den: int = 4
    song_position: float = 0.0
    loop_mode: bool = False


class EffectSlot(BaseModel):
    """A single effect slot on a mixer track."""

    index: int = 0
    plugin_name: str = ""
    enabled: bool = True


class MixerTrackState(BaseModel):
    """State of a single mixer track."""

    index: int = 0
    name: str = ""
    volume: float = Field(default=0.8, ge=0.0, le=1.0)
    pan: float = Field(default=0.0, ge=-1.0, le=1.0)
    muted: bool = False
    solo: bool = False
    armed: bool = False
    effects: list[EffectSlot] = Field(default_factory=list)


class PluginParameter(BaseModel):
    """A single plugin parameter."""

    index: int = 0
    name: str = ""
    value: float = 0.0


class ChannelState(BaseModel):
    """State of a single channel in the channel rack."""

    index: int = 0
    name: str = ""
    plugin_name: str = ""
    volume: float = Field(default=0.78, ge=0.0, le=1.0)
    pan: float = Field(default=0.0, ge=-1.0, le=1.0)
    muted: bool = False
    selected: bool = False
    color: int = 0
    target_mixer_track: int = -1


class PluginState(BaseModel):
    """State of a loaded plugin instance."""

    name: str = ""
    channel_index: int = -1
    mixer_track: int = -1
    mixer_slot: int = -1
    param_count: int = 0
    parameters: list[PluginParameter] = Field(default_factory=list)


class DAWState(BaseModel):
    """Complete snapshot of the FL Studio state."""

    transport: TransportState = Field(default_factory=TransportState)
    mixer_tracks: list[MixerTrackState] = Field(default_factory=list)
    channels: list[ChannelState] = Field(default_factory=list)
    plugins: dict[str, PluginState] = Field(default_factory=dict)
    selected_channel: int = 0
    focused_window: str = ""
    pattern_count: int = 0
    current_pattern: int = 0

    def get_mixer_track(self, index: int) -> MixerTrackState | None:
        """Return a mixer track by index, or None if not found."""
        for track in self.mixer_tracks:
            if track.index == index:
                return track
        return None

    def get_channel(self, index: int) -> ChannelState | None:
        """Return a channel by index, or None if not found."""
        for ch in self.channels:
            if ch.index == index:
                return ch
        return None
