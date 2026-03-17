# DAWMind Setup Guide

Complete guide to setting up DAWMind — the AI agent for FL Studio.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [API Key Configuration](#api-key-configuration)
- [FL Studio Script Installation](#fl-studio-script-installation)
- [First Run](#first-run)
- [Troubleshooting](#troubleshooting)
- [OmniParser GCP Setup (Optional)](#omniparser-gcp-setup-optional)

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.12+ | 3.13 also supported |
| **uv** | Latest | Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/)) |
| **FL Studio** | 21+ | Producer Edition or higher recommended |
| **OS** | Windows 10/11 | FL Studio runs on Windows; WSL2 not supported for GUI control |

### Install uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-org/dawmind.git
cd dawmind
```

### 2. Install dependencies

```bash
uv sync --all-extras
```

This installs all runtime and development dependencies into a virtual environment managed by uv.

### 3. Verify installation

```bash
uv run dawmind --help
```

You should see the DAWMind CLI help output with available commands.

---

## API Key Configuration

DAWMind uses multiple AI models. You need at least one API key to get started.

### Required: Gemini (Vision)

The vision pipeline uses Gemini 2.5 Flash to analyze FL Studio screenshots.

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Create an API key
3. Set the environment variable:

```bash
export GOOGLE_API_KEY=your-gemini-api-key
```

### Required: Anthropic (Planning)

The planning engine uses Claude for reasoning and task decomposition.

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Create an API key
3. Set the environment variable:

```bash
export ANTHROPIC_API_KEY=your-anthropic-api-key
```

### Optional: OpenAI

Only needed if using OpenAI models for specific tasks.

```bash
export OPENAI_API_KEY=your-openai-api-key
```

### Persistent Configuration

For permanent setup, add the exports to your shell profile (`~/.bashrc`, `~/.zshrc`, or `$PROFILE` on PowerShell).

Alternatively, you can set keys in `config/dawmind.toml` directly (not recommended for shared machines):

```toml
[llm.anthropic]
api_key = "sk-ant-..."

[llm.google]
api_key = "AI..."
```

---

## FL Studio Script Installation

DAWMind communicates with FL Studio via a MIDI controller script that runs inside FL Studio.

### 1. Locate FL Studio's Hardware folder

The default path is:

```
Windows: %USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Hardware\
```

Typically this resolves to:

```
C:\Users\YourName\Documents\Image-Line\FL Studio\Settings\Hardware\
```

### 2. Copy the DAWMind scripts

Copy the entire `fl_script/` folder into the Hardware directory:

```
Documents/
  Image-Line/
    FL Studio/
      Settings/
        Hardware/
          DAWMind/               <-- Create this folder
            device_DAWMind.py    <-- Copy from fl_script/
            ipc_handler.py       <-- Copy from fl_script/
```

On Windows (PowerShell):

```powershell
$dest = "$env:USERPROFILE\Documents\Image-Line\FL Studio\Settings\Hardware\DAWMind"
New-Item -ItemType Directory -Path $dest -Force
Copy-Item fl_script\* $dest
```

### 3. Enable in FL Studio

1. Open FL Studio
2. Go to **Options > MIDI Settings**
3. In the **Controller type** dropdown, find **DAWMind**
4. Select it and click **Enable**
5. FL Studio will load the script and start the IPC handler

---

## First Run

### 1. Start the bridge server

The bridge server connects DAWMind to FL Studio via WebSocket:

```bash
uv run dawmind start
```

This will:
- Load configuration from `config/dawmind.toml`
- Start the WebSocket bridge on `ws://127.0.0.1:9500`
- Start the API server on `http://127.0.0.1:9501`
- Connect to FL Studio's named pipe

### 2. Check status

In a separate terminal:

```bash
uv run dawmind status
```

This shows the connection status, loaded models, and FL Studio state.

### 3. Send a command

Use the chat interface to interact with FL Studio:

```bash
uv run dawmind chat
```

Example commands:
- *"Set the tempo to 128 BPM"*
- *"Mute track 3 in the mixer"*
- *"Turn up the filter cutoff on the Serum instance"*

The last example will use the vision pipeline (OmniParser + Gemini) to find and adjust the knob in the plugin GUI.

---

## Troubleshooting

### "No config file found, using defaults"

Make sure you're running commands from the project root directory (where `config/dawmind.toml` lives).

### "Connection refused" on WebSocket

1. Ensure FL Studio is running with the DAWMind script enabled
2. Check that no other process is using port 9500:
   ```bash
   netstat -an | findstr 9500
   ```
3. Verify the pipe name matches in `dawmind.toml` and `device_DAWMind.py`

### "Gemini API error: 403"

- Verify your `GOOGLE_API_KEY` is set and valid
- Check that the Gemini API is enabled in your Google Cloud project
- Ensure you have billing enabled (free tier has generous limits)

### "Anthropic API error: 401"

- Verify your `ANTHROPIC_API_KEY` is set and valid
- Check your API key hasn't expired

### Vision actions are inaccurate

- Make sure `capture_monitor` in `dawmind.toml` points to the monitor where FL Studio is running (0 = entire virtual screen, 1 = primary monitor, 2 = secondary, etc.)
- For better accuracy, deploy OmniParser on GCP (see below) instead of relying on Gemini alone

### FL Studio script not appearing in MIDI Settings

- Verify the script files are in the correct directory
- The folder must be named exactly `DAWMind` (case-sensitive)
- Restart FL Studio after copying the scripts
- Check FL Studio's **View > Script output** for error messages

---

## OmniParser GCP Setup (Optional)

OmniParser V2 dramatically improves UI element detection for plugin GUIs. It runs as a separate microservice on Google Cloud with a GPU.

### Prerequisites

- Google Cloud account with billing enabled
- `gcloud` CLI installed and authenticated
- GPU quota for NVIDIA L4 in `europe-west1` (or your preferred region)

### Deploy

```bash
export GCP_PROJECT_ID=your-project-id
cd omniparser/
./deploy_gcp.sh
```

The script will output the endpoint URL. Update your config:

```toml
[vision]
omniparser_endpoint = "http://<EXTERNAL_IP>:8080/parse"
```

### Cost

Running OmniParser costs approximately **$0.70/hour** on a `g2-standard-4` instance with L4 GPU. Stop the instance when not producing music:

```bash
gcloud compute instances stop omniparser-v2 --zone=europe-west1-b
```

See `omniparser/README.md` for full deployment details.

---

## Configuration Reference

All settings live in `config/dawmind.toml`. Key sections:

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `general` | `log_level` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `fl_studio` | `pipe_name` | `dawmind` | Named pipe identifier |
| `server` | `ws_port` | `9500` | WebSocket server port |
| `server` | `api_port` | `9501` | REST API server port |
| `llm` | `planning_model` | `claude-sonnet-4-20250514` | Model for task planning |
| `llm` | `vision_model` | `gemini-2.5-flash` | Model for screenshot analysis |
| `llm` | `router_strategy` | `auto` | `auto`, `force_api`, or `force_vision` |
| `vision` | `omniparser_endpoint` | `http://localhost:8080/parse` | OmniParser service URL |
| `vision` | `capture_monitor` | `0` | Monitor index for screenshots |
