"""Mock FL Studio environment for integration testing.

Simulates the FL Studio side of the file-based IPC protocol:
- Reads commands from ``{ipc_dir}/commands.jsonl``
- Writes responses to ``{ipc_dir}/responses.jsonl``
- Writes state snapshots to ``{ipc_dir}/state.json``

Maintains internal DAW state that mirrors the real FL Studio API
and responds to all command types with realistic fake data.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Pre-built project scenarios
# ---------------------------------------------------------------------------


def _empty_project_state() -> dict:
    """An empty FL Studio project — stopped, no channels, default mixer."""
    return {
        "transport": {
            "playing": False,
            "recording": False,
            "tempo": 140.0,
            "time_signature_num": 4,
            "time_signature_den": 4,
            "song_position": 0.0,
            "loop_mode": False,
        },
        "mixer_tracks": [
            {
                "index": 0,
                "name": "Master",
                "volume": 0.8,
                "pan": 0.0,
                "muted": False,
                "solo": False,
                "armed": False,
                "effects": [],
            }
        ],
        "channels": [],
        "plugins": {},
        "selected_channel": 0,
        "focused_window": "Channel Rack",
        "pattern_count": 1,
        "current_pattern": 1,
    }


def _basic_beat_state() -> dict:
    """A simple beat project with kick, snare, hat channels."""
    return {
        "transport": {
            "playing": False,
            "recording": False,
            "tempo": 128.0,
            "time_signature_num": 4,
            "time_signature_den": 4,
            "song_position": 0.0,
            "loop_mode": True,
        },
        "mixer_tracks": [
            {
                "index": 0,
                "name": "Master",
                "volume": 0.8,
                "pan": 0.0,
                "muted": False,
                "solo": False,
                "armed": False,
                "effects": [],
            },
            {
                "index": 1,
                "name": "Kick",
                "volume": 0.75,
                "pan": 0.0,
                "muted": False,
                "solo": False,
                "armed": False,
                "effects": [],
            },
            {
                "index": 2,
                "name": "Snare",
                "volume": 0.7,
                "pan": 0.0,
                "muted": False,
                "solo": False,
                "armed": False,
                "effects": [],
            },
            {
                "index": 3,
                "name": "HiHat",
                "volume": 0.65,
                "pan": 0.1,
                "muted": False,
                "solo": False,
                "armed": False,
                "effects": [],
            },
        ],
        "channels": [
            {
                "index": 0,
                "name": "Kick",
                "plugin_name": "Sampler",
                "volume": 0.78,
                "pan": 0.0,
                "muted": False,
                "selected": True,
                "color": 0xFF5500,
                "target_mixer_track": 1,
            },
            {
                "index": 1,
                "name": "Snare",
                "plugin_name": "Sampler",
                "volume": 0.78,
                "pan": 0.0,
                "muted": False,
                "selected": False,
                "color": 0x55FF00,
                "target_mixer_track": 2,
            },
            {
                "index": 2,
                "name": "HiHat",
                "plugin_name": "Sampler",
                "volume": 0.65,
                "pan": 0.1,
                "muted": False,
                "selected": False,
                "color": 0x0055FF,
                "target_mixer_track": 3,
            },
        ],
        "plugins": {},
        "selected_channel": 0,
        "focused_window": "Channel Rack",
        "pattern_count": 1,
        "current_pattern": 1,
    }


def _full_mix_state() -> dict:
    """A full mix project with multiple channels, effects, and plugins."""
    mixer_tracks = [
        {
            "index": 0,
            "name": "Master",
            "volume": 0.8,
            "pan": 0.0,
            "muted": False,
            "solo": False,
            "armed": False,
            "effects": [
                {"index": 0, "plugin_name": "Fruity Limiter", "enabled": True},
                {"index": 1, "plugin_name": "Parametric EQ 2", "enabled": True},
            ],
        },
    ]
    for i, (name, vol) in enumerate(
        [
            ("Kick", 0.75),
            ("Snare", 0.72),
            ("HiHat", 0.60),
            ("Bass", 0.70),
            ("Lead", 0.65),
            ("Pad", 0.55),
            ("FX", 0.50),
            ("Vocal", 0.68),
        ],
        start=1,
    ):
        effects = []
        if name in ("Kick", "Snare", "Bass"):
            effects.append({"index": 0, "plugin_name": "Parametric EQ 2", "enabled": True})
        if name in ("Lead", "Pad", "Vocal"):
            effects.append({"index": 0, "plugin_name": "Fruity Reverb 2", "enabled": True})
        if name == "Vocal":
            effects.append({"index": 1, "plugin_name": "Fruity Compressor", "enabled": True})
        mixer_tracks.append(
            {
                "index": i,
                "name": name,
                "volume": vol,
                "pan": 0.0,
                "muted": False,
                "solo": False,
                "armed": False,
                "effects": effects,
            }
        )

    channels = []
    channel_data = [
        ("Kick", "FPC", 1),
        ("Snare", "FPC", 2),
        ("HiHat", "FPC", 3),
        ("Bass", "Sytrus", 4),
        ("Lead", "Serum", 5),
        ("Pad", "Vital", 6),
        ("FX", "Gross Beat", 7),
        ("Vocal", "Sampler", 8),
    ]
    for idx, (name, plugin, mixer_trk) in enumerate(channel_data):
        channels.append(
            {
                "index": idx,
                "name": name,
                "plugin_name": plugin,
                "volume": 0.78,
                "pan": 0.0,
                "muted": False,
                "selected": idx == 0,
                "color": 0x808080 + idx * 0x101010,
                "target_mixer_track": mixer_trk,
            }
        )

    plugins = {
        "Serum": {
            "name": "Serum",
            "channel_index": 4,
            "mixer_track": -1,
            "mixer_slot": -1,
            "param_count": 5,
            "parameters": [
                {"index": 0, "name": "Osc A Level", "value": 0.8},
                {"index": 1, "name": "Osc B Level", "value": 0.0},
                {"index": 2, "name": "Filter Cutoff", "value": 0.65},
                {"index": 3, "name": "Filter Resonance", "value": 0.3},
                {"index": 4, "name": "Master Volume", "value": 0.75},
            ],
        },
        "Sytrus": {
            "name": "Sytrus",
            "channel_index": 3,
            "mixer_track": -1,
            "mixer_slot": -1,
            "param_count": 3,
            "parameters": [
                {"index": 0, "name": "Op 1 Level", "value": 1.0},
                {"index": 1, "name": "Op 2 Level", "value": 0.5},
                {"index": 2, "name": "Filter Cutoff", "value": 0.4},
            ],
        },
    }

    return {
        "transport": {
            "playing": True,
            "recording": False,
            "tempo": 150.0,
            "time_signature_num": 4,
            "time_signature_den": 4,
            "song_position": 32.0,
            "loop_mode": True,
        },
        "mixer_tracks": mixer_tracks,
        "channels": channels,
        "plugins": plugins,
        "selected_channel": 4,
        "focused_window": "Mixer",
        "pattern_count": 4,
        "current_pattern": 2,
    }


SCENARIOS: dict[str, callable] = {
    "empty_project": _empty_project_state,
    "basic_beat": _basic_beat_state,
    "full_mix": _full_mix_state,
}


# ---------------------------------------------------------------------------
# Mock FL Studio IPC process
# ---------------------------------------------------------------------------


@dataclass
class MockFLStudio:
    """Simulates FL Studio by reading commands from file-based IPC and writing responses.

    The mock runs as an async background task, polling the commands file and
    processing them with realistic fake data.  It maintains internal state
    that matches the scenarios and can be mutated by commands.
    """

    ipc_dir: str = ""
    scenario: str = "basic_beat"
    poll_interval: float = 0.05  # 50ms — fast for tests
    state: dict = field(default_factory=dict)
    _task: asyncio.Task | None = field(default=None, repr=False)
    _running: bool = False

    def __post_init__(self):
        if not self.ipc_dir:
            self.ipc_dir = os.path.join(tempfile.gettempdir(), "dawmind_ipc")
        if not self.state:
            factory = SCENARIOS.get(self.scenario, _basic_beat_state)
            self.state = factory()

    async def start(self) -> None:
        """Start the mock FL Studio IPC loop."""
        os.makedirs(self.ipc_dir, exist_ok=True)
        # Ensure IPC files exist
        for name in ("commands.jsonl", "responses.jsonl"):
            path = os.path.join(self.ipc_dir, name)
            if not os.path.exists(path):
                with open(path, "w") as f:
                    f.write("")

        # Write initial state
        self._write_state()

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the mock FL Studio."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self) -> None:
        """Main loop: read commands, process them, write responses + state."""
        while self._running:
            try:
                commands = self._read_commands()
                for cmd in commands:
                    response = self._handle_command(cmd)
                    self._write_response(response)
                # Always write current state (simulates FL Studio's OnIdle)
                self._write_state()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            await asyncio.sleep(self.poll_interval)

    # -- IPC file operations --

    def _read_commands(self) -> list[dict]:
        """Read and consume pending commands from commands.jsonl."""
        path = os.path.join(self.ipc_dir, "commands.jsonl")
        commands = []
        try:
            with open(path) as f:
                lines = f.readlines()
            if lines:
                with open(path, "w") as f:
                    f.write("")
                for line in lines:
                    line = line.strip()
                    if line:
                        try:
                            commands.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except FileNotFoundError:
            pass
        return commands

    def _write_response(self, response: dict) -> None:
        """Append a response to responses.jsonl."""
        path = os.path.join(self.ipc_dir, "responses.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(response) + "\n")

    def _write_state(self) -> None:
        """Write current state to state.json (atomic-ish) and update heartbeat."""
        path = os.path.join(self.ipc_dir, "state.json")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        if os.path.exists(path):
            os.remove(path)
        os.rename(tmp, path)
        # Write heartbeat so the bridge detects us as connected
        heartbeat_path = os.path.join(self.ipc_dir, "heartbeat")
        with open(heartbeat_path, "w") as f:
            f.write(str(time.time()))

    # -- Command dispatch --

    def _handle_command(self, cmd: dict) -> dict:
        """Dispatch a command and return a response dict."""
        cmd_id = cmd.get("id", "unknown")
        module = cmd.get("module", "")
        action = cmd.get("action", "")
        params = cmd.get("params", {})

        try:
            result = self._dispatch(module, action, params)
            return {"id": cmd_id, "status": "ok", "result": result}
        except Exception as exc:
            return {"id": cmd_id, "status": "error", "error": str(exc)}

    def _dispatch(self, module: str, action: str, params: dict) -> dict:
        """Route to the appropriate handler. Mirrors device_DAWMind.py dispatch."""
        handlers = {
            ("transport", "play"): self._transport_play,
            ("transport", "stop"): self._transport_stop,
            ("transport", "record"): self._transport_record,
            ("transport", "setTempo"): self._transport_set_tempo,
            ("mixer", "getTrackVolume"): self._mixer_get_volume,
            ("mixer", "setTrackVolume"): self._mixer_set_volume,
            ("mixer", "getTrackPan"): self._mixer_get_pan,
            ("mixer", "setTrackPan"): self._mixer_set_pan,
            ("mixer", "muteTrack"): self._mixer_mute_track,
            ("mixer", "soloTrack"): self._mixer_solo_track,
            ("channels", "getChannelName"): self._channel_get_name,
            ("channels", "setChannelVolume"): self._channel_set_volume,
            ("channels", "channelCount"): self._channel_count,
            ("channels", "selectChannel"): self._channel_select,
            ("plugins", "getPluginName"): self._plugin_get_name,
            ("plugins", "getParamCount"): self._plugin_get_param_count,
            ("plugins", "getParamName"): self._plugin_get_param_name,
            ("plugins", "getParamValue"): self._plugin_get_param_value,
            ("plugins", "setParamValue"): self._plugin_set_param_value,
            ("state", "full"): self._state_full,
        }
        handler = handlers.get((module, action))
        if handler is None:
            raise ValueError(f"Unknown command: {module}.{action}")
        return handler(params)

    # -- Transport handlers --

    def _transport_play(self, _params: dict) -> dict:
        self.state["transport"]["playing"] = True
        return {"playing": True}

    def _transport_stop(self, _params: dict) -> dict:
        self.state["transport"]["playing"] = False
        self.state["transport"]["song_position"] = 0.0
        return {"playing": False}

    def _transport_record(self, _params: dict) -> dict:
        recording = not self.state["transport"]["recording"]
        self.state["transport"]["recording"] = recording
        return {"recording": recording}

    def _transport_set_tempo(self, params: dict) -> dict:
        bpm = params["bpm"]
        old = self.state["transport"]["tempo"]
        self.state["transport"]["tempo"] = bpm
        return {"previous": old, "current": bpm}

    # -- Mixer handlers --

    def _find_mixer_track(self, index: int) -> dict | None:
        for track in self.state.get("mixer_tracks", []):
            if track["index"] == index:
                return track
        return None

    def _mixer_get_volume(self, params: dict) -> dict:
        track = self._find_mixer_track(params["track"])
        if track is None:
            raise ValueError(f"Mixer track {params['track']} not found")
        return {"track": params["track"], "volume": track["volume"]}

    def _mixer_set_volume(self, params: dict) -> dict:
        track = self._find_mixer_track(params["track"])
        if track is None:
            raise ValueError(f"Mixer track {params['track']} not found")
        old = track["volume"]
        track["volume"] = params["volume"]
        return {"track": params["track"], "previous": old, "current": params["volume"]}

    def _mixer_get_pan(self, params: dict) -> dict:
        track = self._find_mixer_track(params["track"])
        if track is None:
            raise ValueError(f"Mixer track {params['track']} not found")
        return {"track": params["track"], "pan": track["pan"]}

    def _mixer_set_pan(self, params: dict) -> dict:
        track = self._find_mixer_track(params["track"])
        if track is None:
            raise ValueError(f"Mixer track {params['track']} not found")
        old = track["pan"]
        track["pan"] = params["pan"]
        return {"track": params["track"], "previous": old, "current": params["pan"]}

    def _mixer_mute_track(self, params: dict) -> dict:
        track = self._find_mixer_track(params["track"])
        if track is None:
            raise ValueError(f"Mixer track {params['track']} not found")
        track["muted"] = not track["muted"]
        return {"track": params["track"], "muted": track["muted"]}

    def _mixer_solo_track(self, params: dict) -> dict:
        track = self._find_mixer_track(params["track"])
        if track is None:
            raise ValueError(f"Mixer track {params['track']} not found")
        track["solo"] = not track["solo"]
        return {"track": params["track"], "solo": track["solo"]}

    # -- Channel handlers --

    def _find_channel(self, index: int) -> dict | None:
        for ch in self.state.get("channels", []):
            if ch["index"] == index:
                return ch
        return None

    def _channel_get_name(self, params: dict) -> dict:
        ch = self._find_channel(params["index"])
        if ch is None:
            raise ValueError(f"Channel {params['index']} not found")
        return {"index": params["index"], "name": ch["name"]}

    def _channel_set_volume(self, params: dict) -> dict:
        ch = self._find_channel(params["index"])
        if ch is None:
            raise ValueError(f"Channel {params['index']} not found")
        old = ch["volume"]
        ch["volume"] = params["volume"]
        return {"index": params["index"], "previous": old, "current": params["volume"]}

    def _channel_count(self, _params: dict) -> dict:
        return {"count": len(self.state.get("channels", []))}

    def _channel_select(self, params: dict) -> dict:
        index = params["index"]
        for ch in self.state.get("channels", []):
            ch["selected"] = ch["index"] == index
        self.state["selected_channel"] = index
        return {"selected": index}

    # -- Plugin handlers --

    def _find_plugin_by_channel(self, channel: int) -> tuple[str, dict] | None:
        ch = self._find_channel(channel)
        if ch is None:
            return None
        plugin_name = ch.get("plugin_name", "")
        plugin = self.state.get("plugins", {}).get(plugin_name)
        if plugin:
            return plugin_name, plugin
        # Return a synthetic plugin for channels without detailed plugin state
        return plugin_name, {
            "name": plugin_name,
            "channel_index": channel,
            "mixer_track": -1,
            "mixer_slot": -1,
            "param_count": 0,
            "parameters": [],
        }

    def _plugin_get_name(self, params: dict) -> dict:
        result = self._find_plugin_by_channel(params["channel"])
        if result is None:
            raise ValueError(f"Channel {params['channel']} not found")
        name, _ = result
        return {"channel": params["channel"], "name": name}

    def _plugin_get_param_count(self, params: dict) -> dict:
        result = self._find_plugin_by_channel(params["channel"])
        if result is None:
            raise ValueError(f"Channel {params['channel']} not found")
        _, plugin = result
        return {"channel": params["channel"], "count": plugin["param_count"]}

    def _plugin_get_param_name(self, params: dict) -> dict:
        result = self._find_plugin_by_channel(params["channel"])
        if result is None:
            raise ValueError(f"Channel {params['channel']} not found")
        _, plugin = result
        for p in plugin.get("parameters", []):
            if p["index"] == params["param_index"]:
                return {
                    "channel": params["channel"],
                    "param_index": params["param_index"],
                    "name": p["name"],
                }
        raise ValueError(f"Parameter {params['param_index']} not found")

    def _plugin_get_param_value(self, params: dict) -> dict:
        result = self._find_plugin_by_channel(params["channel"])
        if result is None:
            raise ValueError(f"Channel {params['channel']} not found")
        _, plugin = result
        for p in plugin.get("parameters", []):
            if p["index"] == params["param_index"]:
                return {
                    "channel": params["channel"],
                    "param_index": params["param_index"],
                    "value": p["value"],
                }
        raise ValueError(f"Parameter {params['param_index']} not found")

    def _plugin_set_param_value(self, params: dict) -> dict:
        result = self._find_plugin_by_channel(params["channel"])
        if result is None:
            raise ValueError(f"Channel {params['channel']} not found")
        _, plugin = result
        for p in plugin.get("parameters", []):
            if p["index"] == params["param_index"]:
                old = p["value"]
                p["value"] = params["value"]
                return {
                    "channel": params["channel"],
                    "param_index": params["param_index"],
                    "previous": old,
                    "current": params["value"],
                }
        raise ValueError(f"Parameter {params['param_index']} not found")

    # -- State handler --

    def _state_full(self, _params: dict) -> dict:
        return self.state
