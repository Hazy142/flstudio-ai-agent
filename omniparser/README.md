# OmniParser V2 - GCP Deployment

Self-contained deployment package for running [OmniParser V2](https://github.com/microsoft/OmniParser) as a FastAPI microservice on Google Cloud (GCE with L4 GPU).

DAWMind uses OmniParser to detect UI elements (knobs, sliders, buttons) in FL Studio and VST plugin screenshots.

## Architecture

```
DAWMind Agent  ──POST /parse──>  OmniParser V2 (GCE + L4 GPU)
  (local)                          ├── FastAPI server
                                   ├── Icon detection model
                                   └── Icon caption model (Florence)
```

## Quick Start

### Prerequisites

- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`) authenticated
- Docker installed locally
- GCP project with **Compute Engine API** and **Artifact Registry API** enabled
- GPU quota for `NVIDIA_L4` in your target region

### Deploy

```bash
export GCP_PROJECT_ID=my-project
cd omniparser/
chmod +x deploy_gcp.sh
./deploy_gcp.sh
```

The script will:
1. Create an Artifact Registry repository
2. Build the Docker image (~15 min, downloads models)
3. Push to Artifact Registry
4. Create a GCE `g2-standard-4` instance with L4 GPU
5. Print the endpoint URL

### Configure DAWMind

After deployment, update `config/dawmind.toml`:

```toml
[vision]
omniparser_endpoint = "http://<EXTERNAL_IP>:8080/parse"
```

### Test

```bash
# Health check
curl http://<EXTERNAL_IP>:8080/health

# Parse a screenshot
curl -X POST http://<EXTERNAL_IP>:8080/parse \
  -F 'file=@screenshot.png'

# Or with base64 JSON
curl -X POST http://<EXTERNAL_IP>:8080/parse \
  -H 'Content-Type: application/json' \
  -d '{"image": "<base64-encoded-png>"}'
```

### Response Format

```json
{
    "elements": [
        {
            "id": 0,
            "type": "button",
            "label": "Filter Cutoff",
            "bbox": [120, 340, 180, 400],
            "confidence": 0.92
        }
    ],
    "image_size": [1920, 1080],
    "parse_time_ms": 150
}
```

## Cost Estimate

| Resource | Spec | Cost (approx.) |
|----------|------|-----------------|
| GCE instance | `g2-standard-4` (4 vCPU, 16 GB RAM) | ~$0.55/hr |
| GPU | 1x NVIDIA L4 (24 GB VRAM) | ~$0.15/hr |
| Boot disk | 80 GB SSD | ~$12/mo |
| **Total (running)** | | **~$0.70/hr** |

**Tip:** Stop the instance when not in use to avoid charges:

```bash
# Stop
gcloud compute instances stop omniparser-v2 --zone=europe-west1-b --project=$GCP_PROJECT_ID

# Resume
gcloud compute instances start omniparser-v2 --zone=europe-west1-b --project=$GCP_PROJECT_ID
```

## Local Development

Run the server locally (without GPU / real models) for testing the API interface:

```bash
pip install fastapi uvicorn python-multipart pillow
python server.py
# Server starts on http://localhost:8080 with stub parser
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check and model status |
| `/parse` | POST | Parse screenshot, returns UI elements |
| `/docs` | GET | Interactive Swagger UI |
