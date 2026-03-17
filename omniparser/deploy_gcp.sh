#!/bin/bash
# Deploy OmniParser V2 to Google Cloud (GCE with L4 GPU)
#
# Prerequisites:
#   - gcloud CLI authenticated (gcloud auth login)
#   - Docker installed locally
#   - Artifact Registry API enabled
#   - Compute Engine API enabled
#
# Usage:
#   export GCP_PROJECT_ID=my-project
#   ./deploy_gcp.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="europe-west1"
ZONE="europe-west1-b"
INSTANCE_NAME="omniparser-v2"
MACHINE_TYPE="g2-standard-4"  # 1x NVIDIA L4 GPU, 4 vCPU, 16 GB RAM
IMAGE_NAME="omniparser-v2"
REPO_NAME="dawmind"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:latest"
BOOT_DISK_SIZE="80GB"

echo "=== OmniParser V2 GCP Deployment ==="
echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Zone:     ${ZONE}"
echo "Machine:  ${MACHINE_TYPE}"
echo "Image:    ${FULL_IMAGE}"
echo ""

if [ "${PROJECT_ID}" = "your-project-id" ]; then
    echo "ERROR: Set GCP_PROJECT_ID environment variable first."
    echo "  export GCP_PROJECT_ID=my-project"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: Create Artifact Registry repository (if needed)
# ---------------------------------------------------------------------------
echo ">>> Step 1/5: Creating Artifact Registry repository..."
gcloud artifacts repositories describe "${REPO_NAME}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" 2>/dev/null || \
gcloud artifacts repositories create "${REPO_NAME}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --repository-format=docker \
    --description="DAWMind container images"

# ---------------------------------------------------------------------------
# Step 2: Build Docker image
# ---------------------------------------------------------------------------
echo ">>> Step 2/5: Building Docker image..."
docker build -t "${FULL_IMAGE}" .

# ---------------------------------------------------------------------------
# Step 3: Push to Artifact Registry
# ---------------------------------------------------------------------------
echo ">>> Step 3/5: Pushing to Artifact Registry..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker push "${FULL_IMAGE}"

# ---------------------------------------------------------------------------
# Step 4: Create GCE instance with L4 GPU
# ---------------------------------------------------------------------------
echo ">>> Step 4/5: Creating GCE instance..."

# Delete existing instance if present (user must confirm)
if gcloud compute instances describe "${INSTANCE_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" 2>/dev/null; then
    echo "Instance '${INSTANCE_NAME}' already exists. Delete it first:"
    echo "  gcloud compute instances delete ${INSTANCE_NAME} --zone=${ZONE} --project=${PROJECT_ID}"
    exit 1
fi

gcloud compute instances create-with-container "${INSTANCE_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    --machine-type="${MACHINE_TYPE}" \
    --accelerator=type=nvidia-l4,count=1 \
    --maintenance-policy=TERMINATE \
    --boot-disk-size="${BOOT_DISK_SIZE}" \
    --image-family=cos-stable \
    --image-project=cos-cloud \
    --container-image="${FULL_IMAGE}" \
    --container-restart-policy=always \
    --tags=omniparser-http \
    --metadata=google-logging-enabled=true

# Allow HTTP traffic on port 8080
gcloud compute firewall-rules describe allow-omniparser-8080 \
    --project="${PROJECT_ID}" 2>/dev/null || \
gcloud compute firewall-rules create allow-omniparser-8080 \
    --project="${PROJECT_ID}" \
    --allow=tcp:8080 \
    --target-tags=omniparser-http \
    --source-ranges=0.0.0.0/0 \
    --description="Allow OmniParser V2 HTTP traffic"

# Install NVIDIA GPU drivers on Container-Optimized OS
gcloud compute ssh "${INSTANCE_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    --command="sudo cos-extensions install gpu && sudo mount --bind /var/lib/nvidia /var/lib/nvidia && sudo mount -o remount,exec /var/lib/nvidia" \
    2>/dev/null || echo "Note: GPU driver install may need manual SSH setup"

# ---------------------------------------------------------------------------
# Step 5: Print endpoint
# ---------------------------------------------------------------------------
echo ">>> Step 5/5: Fetching endpoint..."
EXTERNAL_IP=$(gcloud compute instances describe "${INSTANCE_NAME}" \
    --project="${PROJECT_ID}" \
    --zone="${ZONE}" \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "OmniParser V2 endpoint:"
echo "  http://${EXTERNAL_IP}:8080"
echo ""
echo "Health check:"
echo "  curl http://${EXTERNAL_IP}:8080/health"
echo ""
echo "Parse screenshot:"
echo "  curl -X POST http://${EXTERNAL_IP}:8080/parse -F 'file=@screenshot.png'"
echo ""
echo "Update dawmind.toml:"
echo "  [vision]"
echo "  omniparser_endpoint = \"http://${EXTERNAL_IP}:8080/parse\""
echo ""
echo "Estimated cost: ~\$0.70/hr (g2-standard-4 with L4 GPU)"
echo "Stop when not in use:"
echo "  gcloud compute instances stop ${INSTANCE_NAME} --zone=${ZONE} --project=${PROJECT_ID}"
