# IPC handler for FL Studio MIDI scripts.
#
# Uses file-based IPC as the primary (and currently only) transport.
# Named Pipes were attempted but are too fragile with FL Studio's
# limited Python interpreter.  They may be re-added as an optimisation
# once the file-based path is proven stable.
#
# This file runs inside FL Studio's limited Python interpreter:
#   - No pip packages
#   - Limited stdlib (no asyncio)
#   - Must be non-blocking
#
# File-based IPC protocol:
#   - Commands:   {ipc_dir}/commands.jsonl  (bridge writes, script reads & truncates)
#   - Responses:  {ipc_dir}/responses.jsonl (script writes, bridge reads & truncates)
#   - State:      {ipc_dir}/state.json      (script writes, bridge reads)
#   - Heartbeat:  {ipc_dir}/heartbeat       (script writes timestamp, bridge checks)

import json
import os
import time

# IPC directory -- shared between the bridge server and FL Studio script
_IPC_DIR = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "dawmind_ipc")

# Named Pipe name (reserved for future use)
_PIPE_NAME = r"\\.\pipe\dawmind"


def _log(msg):
    """Log a message (visible in FL Studio's script console)."""
    try:
        print("[DAWMind IPC] " + str(msg))
    except Exception:
        pass


def _ensure_ipc_dir():
    """Create the IPC directory if it does not exist."""
    if not os.path.isdir(_IPC_DIR):
        try:
            os.makedirs(_IPC_DIR, exist_ok=True)
        except OSError as exc:
            _log("Failed to create IPC dir %s: %s" % (_IPC_DIR, exc))


class _FileFallbackIPC:
    """File-based IPC -- the primary transport for FL Studio communication.

    Commands are written one-per-line to ``commands.jsonl`` by the bridge
    server.  The FL Studio script reads lines, processes them, and writes
    responses to ``responses.jsonl``.  State snapshots go to ``state.json``.
    A heartbeat file is updated on every state push so the bridge can
    detect whether FL Studio is alive.
    """

    def __init__(self):
        _ensure_ipc_dir()
        self._cmd_path = os.path.join(_IPC_DIR, "commands.jsonl")
        self._rsp_path = os.path.join(_IPC_DIR, "responses.jsonl")
        self._state_path = os.path.join(_IPC_DIR, "state.json")
        self._heartbeat_path = os.path.join(_IPC_DIR, "heartbeat")
        # Touch files so they exist
        for p in (self._cmd_path, self._rsp_path):
            if not os.path.exists(p):
                try:
                    with open(p, "w") as f:
                        f.write("")
                except OSError as exc:
                    _log("Failed to touch %s: %s" % (p, exc))
        _log("File IPC initialised at %s" % _IPC_DIR)

    @property
    def ipc_dir(self):
        """Return the IPC directory path."""
        return _IPC_DIR

    def read_commands(self):
        """Read and consume all pending commands. Returns list of dicts."""
        commands = []
        try:
            with open(self._cmd_path, "r") as f:
                lines = f.readlines()
            if lines:
                # Truncate the file after reading
                with open(self._cmd_path, "w") as f:
                    f.write("")
                for line in lines:
                    line = line.strip()
                    if line:
                        try:
                            commands.append(json.loads(line))
                        except (json.JSONDecodeError, ValueError) as exc:
                            _log("Bad command JSON: %s" % exc)
        except (OSError, IOError) as exc:
            _log("read_commands error: %s" % exc)
        return commands

    def write_response(self, response):
        """Append a response dict as a JSON line."""
        try:
            with open(self._rsp_path, "a") as f:
                f.write(json.dumps(response) + "\n")
        except (OSError, IOError) as exc:
            _log("write_response error: %s" % exc)

    def write_state(self, state):
        """Write the current state snapshot (overwrites previous) and update heartbeat."""
        try:
            tmp = self._state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f)
            # Atomic-ish rename
            if os.path.exists(self._state_path):
                os.remove(self._state_path)
            os.rename(tmp, self._state_path)
        except (OSError, IOError) as exc:
            _log("write_state error: %s" % exc)

        # Update heartbeat
        self._write_heartbeat()

    def _write_heartbeat(self):
        """Write the current timestamp to the heartbeat file."""
        try:
            with open(self._heartbeat_path, "w") as f:
                f.write(str(time.time()))
        except (OSError, IOError) as exc:
            _log("heartbeat write error: %s" % exc)

    def close(self):
        pass


def create_ipc():
    """Create the file-based IPC handler.

    Always uses file-based IPC for reliability.  Named Pipes may be
    re-introduced as an optional optimisation in a future release.
    """
    _log("Creating file-based IPC (dir=%s)" % _IPC_DIR)
    return _FileFallbackIPC()
