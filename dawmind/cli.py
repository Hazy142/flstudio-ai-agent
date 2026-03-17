"""DAWMind CLI -- Rich-based command-line interface."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from dawmind import __version__
from dawmind.config import load_config

console = Console()

BANNER = r"""
  ____    ___  _      ____  __ _           _
 |  _ \  / _ \| |    / /  \/  (_)_ __   __| |
 | | | |/ /_\ \ | /\ / /| |\/| | | '_ \ / _` |
 | |_| / /_  _\ |/  V / | |  | | | | | | (_| |
 |____/\/ /_\  \_/\_/  |_|  |_|_|_| |_|\__,_|

     AI Agent for FL Studio
"""


def _print_banner() -> None:
    text = Text(BANNER, style="bold cyan")
    panel = Panel(
        text,
        subtitle=f"v{__version__}",
        border_style="bright_blue",
    )
    console.print(panel)


def cmd_start() -> None:
    """Start the DAWMind orchestrator and bridge server."""
    _print_banner()
    config = load_config()

    console.print(f"[green]Starting DAWMind v{config.general.version}[/green]")
    console.print(f"  Bridge server: ws://{config.server.host}:{config.server.ws_port}")
    console.print(f"  API server:    http://{config.server.host}:{config.server.api_port}")
    console.print(f"  Planning LLM:  {config.llm.planning_model}")
    console.print(f"  Vision LLM:    {config.llm.vision_model}")
    console.print()

    from dawmind.api_layer.bridge_server import run_bridge

    run_bridge(config)


def cmd_status() -> None:
    """Check FL Studio connection status."""
    config = load_config()
    console.print("[bold]DAWMind Status[/bold]")
    console.print()

    import httpx

    health_url = f"http://{config.server.host}:{config.server.ws_port}/health"
    try:
        resp = httpx.get(health_url, timeout=3.0)
        data = resp.json()
        fl_connected = data.get("fl_studio_connected", False)
        clients = data.get("connected_clients", 0)

        console.print("  Bridge Server: [green]Running[/green]")
        fl_status = "[green]Connected[/green]" if fl_connected else "[red]Disconnected[/red]"
        console.print(f"  FL Studio:     {fl_status}")
        console.print(f"  WS Clients:    {clients}")
    except httpx.HTTPError:
        console.print("  Bridge Server: [red]Not Running[/red]")
        console.print("  [dim]Start with: dawmind start[/dim]")


def cmd_ipc_test() -> None:
    """Diagnostic tool for the FL Studio <-> Bridge IPC layer."""
    console.print("[bold]DAWMind IPC Diagnostics[/bold]")
    console.print()

    ipc_dir = os.path.join(os.environ.get("TEMP", "/tmp"), "dawmind_ipc")

    # 1. Check IPC directory
    console.print(f"  IPC directory: [cyan]{ipc_dir}[/cyan]")
    if os.path.isdir(ipc_dir):
        console.print("  Directory exists: [green]Yes[/green]")
    else:
        console.print("  Directory exists: [red]No[/red]")
        console.print("  [dim]The IPC directory is created automatically when the bridge or FL Studio script starts.[/dim]")
        return

    # 2. List files
    try:
        files = sorted(os.listdir(ipc_dir))
        if files:
            console.print(f"  Files: {', '.join(files)}")
        else:
            console.print("  Files: [yellow]None[/yellow]")
    except OSError as exc:
        console.print(f"  Files: [red]Error listing: {exc}[/red]")

    console.print()

    # 3. Check heartbeat
    heartbeat_path = os.path.join(ipc_dir, "heartbeat")
    if os.path.isfile(heartbeat_path):
        try:
            with open(heartbeat_path) as f:
                ts = float(f.read().strip())
            age = time.time() - ts
            fresh = age < 5.0
            status = "[green]Fresh[/green]" if fresh else "[red]Stale[/red]"
            console.print(f"  Heartbeat: {status} (age: {age:.1f}s)")
        except (ValueError, OSError) as exc:
            console.print(f"  Heartbeat: [red]Error reading: {exc}[/red]")
    else:
        console.print("  Heartbeat: [red]Not found[/red] -- FL Studio script has not written state yet")

    # 4. Check state.json
    state_path = os.path.join(ipc_dir, "state.json")
    if os.path.isfile(state_path):
        try:
            with open(state_path) as f:
                state = json.load(f)
            console.print("  state.json: [green]Present[/green]")
            if "transport" in state:
                t = state["transport"]
                console.print(f"    Playing: {t.get('playing', '?')}, Tempo: {t.get('tempo', '?')}")
            if "channels" in state and isinstance(state["channels"], list):
                console.print(f"    Channels: {len(state['channels'])}")
        except (json.JSONDecodeError, OSError) as exc:
            console.print(f"  state.json: [red]Error: {exc}[/red]")
    else:
        console.print("  state.json: [yellow]Not found[/yellow]")

    console.print()

    # 5. Write a test command
    cmd_path = os.path.join(ipc_dir, "commands.jsonl")
    test_cmd = {
        "id": "ipc_test_001",
        "module": "state",
        "action": "full",
        "params": {},
    }
    try:
        with open(cmd_path, "a") as f:
            f.write(json.dumps(test_cmd) + "\n")
        console.print("  Wrote test command: state.full (id=ipc_test_001)")
    except OSError as exc:
        console.print(f"  [red]Failed to write test command: {exc}[/red]")
        return

    # 6. Wait and check for response
    console.print("  Waiting 3 seconds for response...")
    time.sleep(3)

    rsp_path = os.path.join(ipc_dir, "responses.jsonl")
    found_response = False
    if os.path.isfile(rsp_path):
        try:
            with open(rsp_path) as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                    if resp.get("id") == "ipc_test_001":
                        found_response = True
                        status = resp.get("status", "?")
                        if status == "ok":
                            console.print(f"  Response: [green]{status}[/green]")
                        else:
                            console.print(f"  Response: [red]{status}[/red] -- {resp.get('error', '')}")
                        break
                except (json.JSONDecodeError, ValueError):
                    pass
        except OSError:
            pass

    if not found_response:
        console.print("  Response: [red]No response received[/red]")
        console.print("  [dim]FL Studio may not be running or the script is not loaded.[/dim]")

    console.print()

    # 7. Connection summary
    heartbeat_ok = False
    if os.path.isfile(heartbeat_path):
        try:
            with open(heartbeat_path) as f:
                ts = float(f.read().strip())
            heartbeat_ok = (time.time() - ts) < 5.0
        except (ValueError, OSError):
            pass

    if heartbeat_ok and found_response:
        console.print("[bold green]FL Studio is connected and responding.[/bold green]")
    elif heartbeat_ok:
        console.print("[bold yellow]FL Studio heartbeat OK but no command response (may be busy).[/bold yellow]")
    else:
        console.print("[bold red]FL Studio is NOT connected.[/bold red]")
        console.print("[dim]Ensure FL Studio is running with the DAWMind MIDI script loaded.[/dim]")


def cmd_chat() -> None:
    """Interactive chat mode -- send commands to FL Studio via natural language."""
    _print_banner()
    config = load_config()

    console.print("[bold green]Chat Mode[/bold green] -- Type commands for FL Studio.")
    console.print("[dim]Type 'quit' or 'exit' to leave. Type 'status' to check connection.[/dim]")
    console.print()

    from dawmind.orchestrator import Orchestrator

    orchestrator = Orchestrator(config)

    async def _run_chat() -> None:
        try:
            await orchestrator.connect()
            console.print("[green]Connected to bridge server.[/green]")
        except Exception as exc:
            console.print(f"[red]Could not connect to bridge server: {exc}[/red]")
            console.print("[dim]Start the bridge first with: dawmind start[/dim]")
            return

        while True:
            try:
                user_input = console.input("[bold cyan]dawmind>[/bold cyan] ")
            except (EOFError, KeyboardInterrupt):
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit"):
                break
            if user_input.lower() == "status":
                status = await orchestrator.get_status()
                console.print(status)
                continue

            try:
                with console.status("[bold]Thinking...[/bold]"):
                    result = await orchestrator.process_input(user_input)
                console.print(f"[green]{result}[/green]")
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/red]")

        await orchestrator.disconnect()
        console.print("[dim]Goodbye![/dim]")

    asyncio.run(_run_chat())


def main() -> None:
    """CLI entry point."""
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        _print_banner()
        console.print("[bold]Usage:[/bold] dawmind <command>")
        console.print()
        console.print("[bold]Commands:[/bold]")
        console.print("  start     Start the bridge server and orchestrator")
        console.print("  status    Check FL Studio connection status")
        console.print("  chat      Interactive chat mode")
        console.print("  ipc-test  Diagnose the FL Studio IPC connection")
        console.print("  version   Show version")
        return

    command = args[0].lower()
    match command:
        case "start":
            cmd_start()
        case "status":
            cmd_status()
        case "chat":
            cmd_chat()
        case "ipc-test":
            cmd_ipc_test()
        case "version":
            console.print(f"DAWMind v{__version__}")
        case _:
            console.print(f"[red]Unknown command: {command}[/red]")
            console.print("Run 'dawmind help' for usage.")
            sys.exit(1)
