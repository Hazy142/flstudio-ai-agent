"""DAWMind CLI – Rich-based command-line interface."""

from __future__ import annotations

import asyncio
import sys

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


def cmd_chat() -> None:
    """Interactive chat mode – send commands to FL Studio via natural language."""
    _print_banner()
    config = load_config()

    console.print("[bold green]Chat Mode[/bold green] – Type commands for FL Studio.")
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
        console.print("  start    Start the bridge server and orchestrator")
        console.print("  status   Check FL Studio connection status")
        console.print("  chat     Interactive chat mode")
        console.print("  version  Show version")
        return

    command = args[0].lower()
    match command:
        case "start":
            cmd_start()
        case "status":
            cmd_status()
        case "chat":
            cmd_chat()
        case "version":
            console.print(f"DAWMind v{__version__}")
        case _:
            console.print(f"[red]Unknown command: {command}[/red]")
            console.print("Run 'dawmind help' for usage.")
            sys.exit(1)
