#!/bin/bash
# Deploy OmniParser V2 to Google Cloud Run with L4 GPU
#
# This uses Cloud Build (no local Docker needed) and Cloud Run with
# scale-to-zero so you only pay when the service is actually processing.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - A GCP project with billing enabled
#
# Usage:
#   export GCP_PROJECT_ID=my-project
#   bash omniparser/deploy_cloudrun.sh
#
# Estimated cost: ~$0.70/hr ONLY when processing requests.
# Scale-to-zero means $0/hr when idle.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="europe-west1"
SERVICE_NAME="omniparser-v2"
REPO_NAME="dawmind"
IMAGE_NAME="omniparser-v2"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:latest"

# Cloud Run GPU config
CPU="8"
MEMORY="32Gi"
GPU_TYPE="nvidia-l4"
GPU_COUNT="1"
MIN_INSTANCES="0"    # Scale to zero!
MAX_INSTANCES="1"    # Max 1 to control costs
PORT="8080"
TIMEOUT="300"        # 5 min request timeout (large screenshots)
CONCURRENCY="4"      # Max concurrent requests per instance

echo "=============================================="
echo "  OmniParser V2 → Cloud Run (L4 GPU)"
echo "=============================================="
echo ""

if [ -z "${PROJECT_ID}" ]; then
    echo "ERROR: Set GCP_PROJECT_ID environment variable first."
    echo ""
    echo "  export GCP_PROJECT_ID=my-project-id"
    echo "  bash omniparser/deploy_cloudrun.sh"
    echo ""
    echo "Find your project ID:"
    echo "  gcloud projects list"
    exit 1
fi

echo "  Project:       ${PROJECT_ID}"
echo "  Region:        ${REGION}"
echo "  Service:       ${SERVICE_NAME}"
echo "  GPU:           ${GPU_TYPE} x${GPU_COUNT}"
echo "  CPU/Memory:    ${CPU} vCPU / ${MEMORY}"
echo "  Min instances: ${MIN_INSTANCES} (scale to zero)"
echo "  Max instances: ${MAX_INSTANCES}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Set project and enable APIs
# ---------------------------------------------------------------------------
echo ">>> Step 1/5: Setting project and enabling APIs..."
gcloud config set project "${PROJECT_ID}" --quiet

gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    --project="${PROJECT_ID}" --quiet

echo "    APIs enabled."

# ---------------------------------------------------------------------------
# Step 2: Create Artifact Registry repository
# ---------------------------------------------------------------------------
echo ">>> Step 2/5: Creating Artifact Registry repository..."
if gcloud artifacts repositories describe "${REPO_NAME}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" 2>/dev/null; then
    echo "    Repository '${REPO_NAME}' already exists."
else
    gcloud artifacts repositories create "${REPO_NAME}" \
        --project="${PROJECT_ID}" \
        --location="${REGION}" \
        --repository-format=docker \
        --description="DAWMind container images" \
        --quiet
    echo "    Repository created."
fi

# ---------------------------------------------------------------------------
# Step 3: Build with Cloud Build (no local Docker needed!)
# ---------------------------------------------------------------------------
echo ">>> Step 3/5: Building Docker image with Cloud Build..."
echo "    This takes 5-10 minutes (downloading OmniParser V2 weights: ~3GB)..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

gcloud builds submit "${SCRIPT_DIR}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --tag="${REGISTRY}" \
    --timeout=1800 \
    --quiet

echo "    Image built and pushed: ${REGISTRY}"

# ---------------------------------------------------------------------------
# Step 4: Deploy to Cloud Run with L4 GPU
# ---------------------------------------------------------------------------
echo ">>> Step 4/5: Deploying to Cloud Run..."

gcloud run deploy "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --image="${REGISTRY}" \
    --cpu="${CPU}" \
    --memory="${MEMORY}" \
    --gpu="${GPU_COUNT}" \
    --gpu-type="${GPU_TYPE}" \
    --min-instances="${MIN_INSTANCES}" \
    --max-instances="${MAX_INSTANCES}" \
    --port="${PORT}" \
    --timeout="${TIMEOUT}" \
    --concurrency="${CONCURRENCY}" \
    --no-cpu-throttling \
    --execution-environment=gen2 \
    --allow-unauthenticated \
    --no-use-http2 \
    --set-env-vars="NVIDIA_VISIBLE_DEVICES=all" \
    --quiet

echo "    Service deployed."

# ---------------------------------------------------------------------------
# Step 5: Get URL and test
# ---------------------------------------------------------------------------
echo ">>> Step 5/5: Fetching service URL..."

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format='value(status.url)')

echo ""
echo "=============================================="
echo "  Deployment Complete!"
echo "=============================================="
echo ""
echo "  Service URL:  ${SERVICE_URL}"
echo ""
echo "  Health check:"
echo "    curl ${SERVICE_URL}/health"
echo ""
echo "  Parse screenshot:"
echo "    curl -X POST ${SERVICE_URL}/parse -F 'file=@screenshot.png'"
echo ""
echo "  Update config/dawmind.toml:"
echo "    [vision]"
echo "    omniparser_endpoint = \"${SERVICE_URL}/parse\""
echo ""
echo "  Cost: ~\$0.70/hr ONLY when processing."
echo "  At idle (scale-to-zero): \$0.00/hr"
echo ""
echo "  To check current cost:"
echo "    gcloud run services describe ${SERVICE_NAME} --region=${REGION}"
echo ""
echo "  To delete (stop all billing):"
echo "    gcloud run services delete ${SERVICE_NAME} --region=${REGION} --quiet"
echo ""
