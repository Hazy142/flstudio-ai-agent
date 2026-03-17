# name=DAWMind
# url=https://github.com/aelsen1808/flstudio-ai-agent
#
# FL Studio MIDI Controller Script for DAWMind.
# This script runs inside FL Studio's Python interpreter and exposes
# the internal API to the DAWMind bridge server via IPC.
#
# Communication: Named Pipe (preferred) or file-based IPC (fallback).
# Protocol: JSON lines – one JSON object per line.
#
# IMPORTANT: FL Studio's Python is limited:
#   - No pip packages
#   - Restricted stdlib
#   - Must never block the main thread

import json
import sys
import os
import time

print("=" * 40)
print("DAWMind Script: Lade Python-Modul...")
print("=" * 40)

# Add the script directory to sys.path so we can import ipc_handler
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import ipc_handler

# FL Studio modules (only available inside FL Studio's interpreter)
try:
    import mixer
    import channels
    import plugins
    import transport
    import playlist
    import patterns
    import ui
    import device
    import general
except ImportError:
    # Running outside FL Studio (e.g. for testing) – create stubs
    mixer = channels = plugins = transport = None
    playlist = patterns = ui = device = general = None

# Globals
_ipc = None
_last_state_push = 0.0
_STATE_INTERVAL = 0.5  # seconds


def OnInit():
    """Called when the script is loaded by FL Studio."""
    global _ipc
    _ipc = ipc_handler.create_ipc()
    _log("DAWMind IPC initialized")


def OnDeInit():
    """Called when the script is unloaded."""
    global _ipc
    if _ipc:
        _ipc.close()
        _ipc = None
    _log("DAWMind IPC closed")


def OnIdle():
    """Called frequently by FL Studio (~10-50 Hz). Process incoming commands."""
    global _last_state_push

    if _ipc is None:
        return

    # Process all pending commands
    commands = _ipc.read_commands()
    for cmd in commands:
        response = _handle_command(cmd)
        if response:
            _ipc.write_response(response)

    # Periodic state broadcast
    now = time.time()
    if now - _last_state_push >= _STATE_INTERVAL:
        _last_state_push = now
        _push_state()


def OnRefresh(flags):
    """Called when FL Studio's state changes. Push state immediately."""
    _push_state()


def OnDirtyMixerTrack(track):
    """Called when a mixer track changes."""
    _push_state()


def OnDirtyChannel(channel, flags):
    """Called when a channel changes."""
    _push_state()


def OnUpdateBeatIndicator(value):
    """Called on beat changes during playback."""
    pass


# ---------------------------------------------------------------------------
# Command handling
# ---------------------------------------------------------------------------

def _handle_command(cmd):
    """Dispatch a command dict and return a response dict."""
    cmd_id = cmd.get("id", "")
    module = cmd.get("module", "")
    action = cmd.get("action", "")
    params = cmd.get("params", {})

    try:
        result = _dispatch(module, action, params)
        return {"id": cmd_id, "status": "ok", "result": result}
    except Exception as e:
        return {"id": cmd_id, "status": "error", "error": str(e)}


def _dispatch(module, action, params):
    """Route a command to the correct FL Studio API call."""
    handler_key = "{}.{}".format(module, action)
    handler = _HANDLERS.get(handler_key)
    if handler is None:
        raise ValueError("Unknown command: {}".format(handler_key))
    return handler(params)


# --- Transport handlers ---

def _transport_play(params):
    transport.start()
    return {"playing": True}


def _transport_stop(params):
    transport.stop()
    return {"playing": False}


def _transport_record(params):
    transport.record()
    return {"recording": transport.isRecording()}


def _transport_set_tempo(params):
    bpm = params.get("bpm", 120.0)
    old_bpm = mixer.getCurrentTempo(True) / 1000.0 if mixer else 0.0
    transport.setTempo(bpm)
    return {"previous": old_bpm, "current": bpm}


# --- Mixer handlers ---

def _mixer_get_volume(params):
    track = params.get("track", 0)
    vol = mixer.getTrackVolume(track)
    return {"track": track, "volume": vol}


def _mixer_set_volume(params):
    track = params.get("track", 0)
    volume = params.get("volume", 0.8)
    prev = mixer.getTrackVolume(track)
    mixer.setTrackVolume(track, volume)
    return {"previous": prev, "current": volume}


def _mixer_get_pan(params):
    track = params.get("track", 0)
    pan = mixer.getTrackPan(track)
    return {"track": track, "pan": pan}


def _mixer_set_pan(params):
    track = params.get("track", 0)
    pan = params.get("pan", 0.0)
    prev = mixer.getTrackPan(track)
    mixer.setTrackPan(track, pan)
    return {"previous": prev, "current": pan}


def _mixer_mute_track(params):
    track = params.get("track", 0)
    mixer.muteTrack(track)
    muted = mixer.isTrackMuted(track)
    return {"track": track, "muted": muted}


def _mixer_solo_track(params):
    track = params.get("track", 0)
    mixer.soloTrack(track)
    solo = mixer.isTrackSolo(track)
    return {"track": track, "solo": solo}


# --- Channel handlers ---

def _channels_get_name(params):
    index = params.get("index", 0)
    name = channels.getChannelName(index)
    return {"index": index, "name": name}


def _channels_set_volume(params):
    index = params.get("index", 0)
    volume = params.get("volume", 0.78)
    prev = channels.getChannelVolume(index)
    channels.setChannelVolume(index, volume)
    return {"previous": prev, "current": volume}


def _channels_count(params):
    count = channels.channelCount()
    return {"count": count}


def _channels_select(params):
    index = params.get("index", 0)
    channels.selectOneChannel(index)
    return {"selected": index}


# --- Plugin handlers ---

def _plugins_get_param_count(params):
    channel = params.get("channel", 0)
    count = plugins.getParamCount(channel)
    return {"channel": channel, "param_count": count}


def _plugins_get_param_name(params):
    channel = params.get("channel", 0)
    param_index = params.get("param_index", 0)
    name = plugins.getParamName(param_index, channel)
    return {"channel": channel, "param_index": param_index, "name": name}


def _plugins_get_param_value(params):
    channel = params.get("channel", 0)
    param_index = params.get("param_index", 0)
    value = plugins.getParamValue(param_index, channel)
    return {"channel": channel, "param_index": param_index, "value": value}


def _plugins_set_param_value(params):
    channel = params.get("channel", 0)
    param_index = params.get("param_index", 0)
    value = params.get("value", 0.0)
    prev = plugins.getParamValue(param_index, channel)
    plugins.setParamValue(value, param_index, channel)
    return {"previous": prev, "current": value}


def _plugins_get_name(params):
    channel = params.get("channel", 0)
    name = plugins.getPluginName(channel)
    return {"channel": channel, "name": name}


# --- State handlers ---

def _state_full(params):
    return _build_full_state()


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS = {
    "transport.play": _transport_play,
    "transport.stop": _transport_stop,
    "transport.record": _transport_record,
    "transport.setTempo": _transport_set_tempo,
    "mixer.getTrackVolume": _mixer_get_volume,
    "mixer.setTrackVolume": _mixer_set_volume,
    "mixer.getTrackPan": _mixer_get_pan,
    "mixer.setTrackPan": _mixer_set_pan,
    "mixer.muteTrack": _mixer_mute_track,
    "mixer.soloTrack": _mixer_solo_track,
    "channels.getChannelName": _channels_get_name,
    "channels.setChannelVolume": _channels_set_volume,
    "channels.channelCount": _channels_count,
    "channels.selectChannel": _channels_select,
    "plugins.getParamCount": _plugins_get_param_count,
    "plugins.getParamName": _plugins_get_param_name,
    "plugins.getParamValue": _plugins_get_param_value,
    "plugins.setParamValue": _plugins_set_param_value,
    "plugins.getPluginName": _plugins_get_name,
    "state.full": _state_full,
}


# ---------------------------------------------------------------------------
# State building
# ---------------------------------------------------------------------------

def _build_full_state():
    """Build a complete state snapshot of the DAW."""
    state = {
        "transport": _get_transport_state(),
        "mixer": {"tracks": _get_mixer_state()},
        "channels": _get_channels_state(),
        "patterns": {
            "count": patterns.patternCount() if patterns else 0,
            "current": patterns.patternNumber() if patterns else 0,
        },
    }
    return state


def _get_transport_state():
    if transport is None:
        return {}
    return {
        "playing": transport.isPlaying() == 1,
        "recording": transport.isRecording() == 1,
        "tempo": mixer.getCurrentTempo(True) / 1000.0 if mixer else 120.0,
        "song_position": transport.getSongPos(0),
    }


def _get_mixer_state():
    if mixer is None:
        return []
    tracks = []
    # FL Studio has 125 mixer tracks (0-124) + master
    track_count = min(mixer.trackCount(), 126)
    for i in range(track_count):
        tracks.append({
            "index": i,
            "name": mixer.getTrackName(i),
            "volume": mixer.getTrackVolume(i),
            "pan": mixer.getTrackPan(i),
            "muted": mixer.isTrackMuted(i) == 1,
            "solo": mixer.isTrackSolo(i) == 1,
        })
    return tracks


def _get_channels_state():
    if channels is None:
        return []
    chans = []
    count = channels.channelCount()
    for i in range(count):
        chans.append({
            "index": i,
            "name": channels.getChannelName(i),
            "volume": channels.getChannelVolume(i),
            "pan": channels.getChannelPan(i),
            "muted": channels.isChannelMuted(i) == 1,
            "selected": channels.isChannelSelected(i) == 1,
            "color": channels.getChannelColor(i),
        })
    return chans


def _push_state():
    """Push the current state to the bridge server via IPC."""
    if _ipc is None:
        return
    try:
        state = _build_full_state()
        _ipc.write_state(state)
    except Exception:
        pass


def _log(msg):
    """Log a message (visible in FL Studio's script console)."""
    try:
        print("[DAWMind] " + str(msg))
    except Exception:
        pass
