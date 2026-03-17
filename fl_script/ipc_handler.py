# IPC handler for FL Studio MIDI scripts.
# Tries Named Pipe first, falls back to file-based IPC.
#
# This file runs inside FL Studio's limited Python interpreter:
#   - No pip packages
#   - Limited stdlib (no asyncio)
#   - Must be non-blocking
#
# File-based IPC protocol:
#   - Commands:  {ipc_dir}/commands.jsonl  (bridge writes, script reads & truncates)
#   - Responses: {ipc_dir}/responses.jsonl (script writes, bridge reads & truncates)
#   - State:     {ipc_dir}/state.json      (script writes, bridge reads)

import json
import os
import sys
import time

# IPC directory – shared between the bridge server and FL Studio script
_IPC_DIR = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "dawmind_ipc")

# Named Pipe name (Windows)
_PIPE_NAME = r"\\.\pipe\dawmind"


def _ensure_ipc_dir():
    """Create the IPC directory if it does not exist."""
    if not os.path.isdir(_IPC_DIR):
        try:
            os.makedirs(_IPC_DIR, exist_ok=True)
        except OSError:
            pass


class _FileFallbackIPC:
    """File-based IPC when Named Pipes are unavailable.

    Commands are written one-per-line to ``commands.jsonl`` by the bridge
    server.  The FL Studio script reads lines, processes them, and writes
    responses to ``responses.jsonl``.  State snapshots go to ``state.json``.
    """

    def __init__(self):
        _ensure_ipc_dir()
        self._cmd_path = os.path.join(_IPC_DIR, "commands.jsonl")
        self._rsp_path = os.path.join(_IPC_DIR, "responses.jsonl")
        self._state_path = os.path.join(_IPC_DIR, "state.json")
        # Touch files so they exist
        for p in (self._cmd_path, self._rsp_path):
            if not os.path.exists(p):
                try:
                    with open(p, "w") as f:
                        f.write("")
                except OSError:
                    pass

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
                        except (json.JSONDecodeError, ValueError):
                            pass
        except (OSError, IOError):
            pass
        return commands

    def write_response(self, response):
        """Append a response dict as a JSON line."""
        try:
            with open(self._rsp_path, "a") as f:
                f.write(json.dumps(response) + "\n")
        except (OSError, IOError):
            pass

    def write_state(self, state):
        """Write the current state snapshot (overwrites previous)."""
        try:
            tmp = self._state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f)
            # Atomic-ish rename
            if os.path.exists(self._state_path):
                os.remove(self._state_path)
            os.rename(tmp, self._state_path)
        except (OSError, IOError):
            pass

    def close(self):
        pass


class _NamedPipeIPC:
    """Windows Named Pipe IPC client.

    Uses ctypes to call Windows API for non-blocking pipe I/O since
    FL Studio's Python may not have win32file.
    """

    def __init__(self):
        self._handle = None
        self._buffer = ""
        self._connected = False
        self._last_connect_attempt = 0.0
        self._connect_interval = 2.0  # seconds between reconnect attempts

    def _try_connect(self):
        """Attempt to open the named pipe. Non-blocking."""
        now = time.time()
        if now - self._last_connect_attempt < self._connect_interval:
            return
        self._last_connect_attempt = now

        try:
            import ctypes
            import ctypes.wintypes

            GENERIC_READ_WRITE = 0xC0000000
            OPEN_EXISTING = 3
            FILE_FLAG_OVERLAPPED = 0x40000000
            INVALID_HANDLE = -1

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateFileW(
                _PIPE_NAME,
                GENERIC_READ_WRITE,
                0,  # no sharing
                None,  # default security
                OPEN_EXISTING,
                0,  # no overlapped for simplicity in FL Studio
                None,
            )
            if handle == INVALID_HANDLE:
                return

            # Set pipe to message mode
            PIPE_READMODE_BYTE = 0x00000000
            mode = ctypes.wintypes.DWORD(PIPE_READMODE_BYTE)
            kernel32.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None)

            self._handle = handle
            self._connected = True
        except Exception:
            self._connected = False

    def _read_nonblocking(self):
        """Try to read from pipe without blocking. Returns bytes or empty."""
        if not self._connected or self._handle is None:
            return b""
        try:
            import ctypes
            import ctypes.wintypes

            kernel32 = ctypes.windll.kernel32
            buf_size = 4096
            buf = ctypes.create_string_buffer(buf_size)
            bytes_read = ctypes.wintypes.DWORD(0)
            bytes_available = ctypes.wintypes.DWORD(0)

            # Peek first to check if data is available
            result = kernel32.PeekNamedPipe(
                self._handle,
                None,
                0,
                None,
                ctypes.byref(bytes_available),
                None,
            )
            if not result or bytes_available.value == 0:
                return b""

            result = kernel32.ReadFile(
                self._handle,
                buf,
                buf_size,
                ctypes.byref(bytes_read),
                None,
            )
            if result and bytes_read.value > 0:
                return buf.raw[: bytes_read.value]
            return b""
        except Exception:
            self._connected = False
            self._handle = None
            return b""

    def _write(self, data):
        """Write bytes to the pipe."""
        if not self._connected or self._handle is None:
            return False
        try:
            import ctypes
            import ctypes.wintypes

            kernel32 = ctypes.windll.kernel32
            if isinstance(data, str):
                data = data.encode("utf-8")
            written = ctypes.wintypes.DWORD(0)
            result = kernel32.WriteFile(
                self._handle,
                data,
                len(data),
                ctypes.byref(written),
                None,
            )
            return bool(result)
        except Exception:
            self._connected = False
            self._handle = None
            return False

    def read_commands(self):
        """Read and parse pending commands from the pipe."""
        if not self._connected:
            self._try_connect()
        if not self._connected:
            return []

        raw = self._read_nonblocking()
        if raw:
            self._buffer += raw.decode("utf-8", errors="replace")

        commands = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                try:
                    commands.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    pass
        return commands

    def write_response(self, response):
        """Send a response dict over the pipe."""
        self._write(json.dumps(response) + "\n")

    def write_state(self, state):
        """Send a state update over the pipe."""
        msg = {"type": "state", "data": state}
        self._write(json.dumps(msg) + "\n")

    def close(self):
        """Close the pipe handle."""
        if self._handle is not None:
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None
            self._connected = False


def create_ipc():
    """Create the best available IPC handler.

    Tries Named Pipes first (Windows only), falls back to file-based IPC.
    """
    if sys.platform == "win32":
        try:
            pipe = _NamedPipeIPC()
            pipe._try_connect()
            if pipe._connected:
                return pipe
        except Exception:
            pass

    # Fall back to file-based IPC (always works)
    return _FileFallbackIPC()
