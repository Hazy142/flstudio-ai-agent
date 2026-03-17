"""Pre-built command constructors for common FL Studio operations."""

from __future__ import annotations

from dawmind.api_layer.protocol import Command, CommandLayer

# --- Transport commands ---


def transport_play() -> Command:
    return Command(module="transport", action="play")


def transport_stop() -> Command:
    return Command(module="transport", action="stop")


def transport_record() -> Command:
    return Command(module="transport", action="record")


def transport_set_tempo(bpm: float) -> Command:
    return Command(module="transport", action="setTempo", params={"bpm": bpm})


# --- Mixer commands ---


def mixer_get_volume(track: int) -> Command:
    return Command(module="mixer", action="getTrackVolume", params={"track": track})


def mixer_set_volume(track: int, volume: float) -> Command:
    return Command(
        module="mixer", action="setTrackVolume", params={"track": track, "volume": volume}
    )


def mixer_get_pan(track: int) -> Command:
    return Command(module="mixer", action="getTrackPan", params={"track": track})


def mixer_set_pan(track: int, pan: float) -> Command:
    return Command(module="mixer", action="setTrackPan", params={"track": track, "pan": pan})


def mixer_mute_track(track: int) -> Command:
    return Command(module="mixer", action="muteTrack", params={"track": track})


def mixer_solo_track(track: int) -> Command:
    return Command(module="mixer", action="soloTrack", params={"track": track})


# --- Channel commands ---


def channel_get_name(index: int) -> Command:
    return Command(module="channels", action="getChannelName", params={"index": index})


def channel_set_volume(index: int, volume: float) -> Command:
    return Command(
        module="channels", action="setChannelVolume", params={"index": index, "volume": volume}
    )


def channel_count() -> Command:
    return Command(module="channels", action="channelCount")


def channel_select(index: int) -> Command:
    return Command(module="channels", action="selectChannel", params={"index": index})


# --- Plugin commands ---


def plugin_get_param_count(channel: int) -> Command:
    return Command(module="plugins", action="getParamCount", params={"channel": channel})


def plugin_get_param_name(channel: int, param_index: int) -> Command:
    return Command(
        module="plugins",
        action="getParamName",
        params={"channel": channel, "param_index": param_index},
    )


def plugin_get_param_value(channel: int, param_index: int) -> Command:
    return Command(
        module="plugins",
        action="getParamValue",
        params={"channel": channel, "param_index": param_index},
    )


def plugin_set_param_value(channel: int, param_index: int, value: float) -> Command:
    return Command(
        module="plugins",
        action="setParamValue",
        params={"channel": channel, "param_index": param_index, "value": value},
    )


def plugin_get_name(channel: int) -> Command:
    return Command(module="plugins", action="getPluginName", params={"channel": channel})


# --- State commands ---


def state_full() -> Command:
    """Request a complete DAW state snapshot."""
    return Command(module="state", action="full")


# --- Vision commands (routed to Layer 2) ---


def vision_interact(
    description: str,
    plugin_window: str,
    element_hint: str,
    interaction_type: str = "click",
    **kwargs: object,
) -> Command:
    return Command(
        layer=CommandLayer.VISION,
        module="vision",
        action="interact",
        params={
            "description": description,
            "plugin_window": plugin_window,
            "element_hint": element_hint,
            "interaction_type": interaction_type,
            **kwargs,
        },
    )
