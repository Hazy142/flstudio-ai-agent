"""Tests for DAW state model serialization."""

from __future__ import annotations

from dawmind.api_layer.state import (
    ChannelState,
    DAWState,
    EffectSlot,
    MixerTrackState,
    PluginParameter,
    PluginState,
    TransportState,
)


def test_transport_state_defaults():
    state = TransportState()
    assert state.playing is False
    assert state.recording is False
    assert state.tempo == 140.0
    assert state.time_signature_num == 4
    assert state.time_signature_den == 4


def test_transport_state_serialization():
    state = TransportState(playing=True, tempo=128.0, recording=True)
    data = state.model_dump()
    assert data["playing"] is True
    assert data["tempo"] == 128.0
    restored = TransportState.model_validate(data)
    assert restored.playing is True
    assert restored.tempo == 128.0


def test_mixer_track_state():
    track = MixerTrackState(
        index=1,
        name="Kick",
        volume=0.75,
        pan=-0.3,
        muted=False,
        solo=True,
        effects=[EffectSlot(index=0, plugin_name="OTT", enabled=True)],
    )
    data = track.model_dump()
    assert data["name"] == "Kick"
    assert data["effects"][0]["plugin_name"] == "OTT"

    restored = MixerTrackState.model_validate(data)
    assert restored.effects[0].plugin_name == "OTT"


def test_channel_state():
    ch = ChannelState(index=0, name="Kick", plugin_name="Sampler", volume=0.8, muted=False)
    data = ch.model_dump()
    assert data["plugin_name"] == "Sampler"


def test_plugin_state():
    plugin = PluginState(
        name="Serum",
        channel_index=2,
        param_count=3,
        parameters=[
            PluginParameter(index=0, name="Cutoff", value=0.5),
            PluginParameter(index=1, name="Resonance", value=0.3),
            PluginParameter(index=2, name="Drive", value=0.0),
        ],
    )
    data = plugin.model_dump()
    assert len(data["parameters"]) == 3
    assert data["parameters"][0]["name"] == "Cutoff"


def test_daw_state_full():
    state = DAWState(
        transport=TransportState(playing=True, tempo=140.0),
        mixer_tracks=[
            MixerTrackState(index=0, name="Master", volume=0.8),
            MixerTrackState(index=1, name="Kick", volume=0.75),
        ],
        channels=[
            ChannelState(index=0, name="Kick", volume=0.8),
        ],
        selected_channel=0,
        pattern_count=4,
        current_pattern=1,
    )

    # JSON round-trip
    json_str = state.model_dump_json()
    restored = DAWState.model_validate_json(json_str)

    assert restored.transport.playing is True
    assert restored.transport.tempo == 140.0
    assert len(restored.mixer_tracks) == 2
    assert restored.mixer_tracks[1].name == "Kick"
    assert restored.pattern_count == 4


def test_daw_state_get_mixer_track():
    state = DAWState(
        mixer_tracks=[
            MixerTrackState(index=0, name="Master"),
            MixerTrackState(index=5, name="Vocals"),
        ]
    )
    assert state.get_mixer_track(5).name == "Vocals"
    assert state.get_mixer_track(99) is None


def test_daw_state_get_channel():
    state = DAWState(
        channels=[
            ChannelState(index=0, name="Kick"),
            ChannelState(index=3, name="Hi-hat"),
        ]
    )
    assert state.get_channel(3).name == "Hi-hat"
    assert state.get_channel(10) is None


def test_daw_state_empty():
    state = DAWState()
    data = state.model_dump()
    assert data["transport"]["playing"] is False
    assert data["mixer_tracks"] == []
    assert data["channels"] == []
