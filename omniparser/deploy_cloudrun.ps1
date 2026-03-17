# Deploy OmniParser V2 to Google Cloud Run with L4 GPU (Windows PowerShell)
#
# Prerequisites:
#   - Google Cloud CLI installed (https://cloud.google.com/sdk/docs/install)
#   - Authenticated: gcloud auth login
#   - A GCP project with billing enabled
#
# Usage:
#   $env:GCP_PROJECT_ID = "my-project-id"
#   .\omniparser\deploy_cloudrun.ps1
#
# Cost: ~$0.70/hr ONLY when processing. $0/hr at idle (scale-to-zero).

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
$PROJECT_ID = $env:GCP_PROJECT_ID
$REGION = "europe-west1"
$SERVICE_NAME = "omniparser-v2"
$REPO_NAME = "dawmind"
$IMAGE_NAME = "omniparser-v2"
$REGISTRY = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/${IMAGE_NAME}:latest"

# Cloud Run GPU config
$CPU = "8"
$MEMORY = "32Gi"
$GPU_TYPE = "nvidia-l4"
$GPU_COUNT = "1"
$MIN_INSTANCES = "0"
$MAX_INSTANCES = "1"
$PORT = "8080"
$TIMEOUT = "300"
$CONCURRENCY = "4"

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  OmniParser V2 -> Cloud Run (L4 GPU)" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

if (-not $PROJECT_ID) {
    Write-Host "ERROR: Set GCP_PROJECT_ID environment variable first." -ForegroundColor Red
    Write-Host ""
    Write-Host '  $env:GCP_PROJECT_ID = "my-project-id"'
    Write-Host "  .\omniparser\deploy_cloudrun.ps1"
    Write-Host ""
    Write-Host "Find your project ID:"
    Write-Host "  gcloud projects list"
    exit 1
}

Write-Host "  Project:       $PROJECT_ID"
Write-Host "  Region:        $REGION"
Write-Host "  Service:       $SERVICE_NAME"
Write-Host "  GPU:           $GPU_TYPE x$GPU_COUNT"
Write-Host "  CPU/Memory:    $CPU vCPU / $MEMORY"
Write-Host "  Min instances: $MIN_INSTANCES (scale to zero)"
Write-Host "  Max instances: $MAX_INSTANCES"
Write-Host ""

# ---------------------------------------------------------------------------
# Step 1: Set project and enable APIs
# ---------------------------------------------------------------------------
Write-Host ">>> Step 1/5: Setting project and enabling APIs..." -ForegroundColor Yellow
gcloud config set project $PROJECT_ID --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to set project" }

gcloud services enable `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    --project=$PROJECT_ID --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable APIs" }

Write-Host "    APIs enabled." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Step 2: Create Artifact Registry repository
# ---------------------------------------------------------------------------
Write-Host ">>> Step 2/5: Creating Artifact Registry repository..." -ForegroundColor Yellow

$repoExists = gcloud artifacts repositories describe $REPO_NAME `
    --project=$PROJECT_ID `
    --location=$REGION 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "    Repository '$REPO_NAME' already exists." -ForegroundColor Green
} else {
    gcloud artifacts repositories create $REPO_NAME `
        --project=$PROJECT_ID `
        --location=$REGION `
        --repository-format=docker `
        --description="DAWMind container images" `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to create repository" }
    Write-Host "    Repository created." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Step 3: Build with Cloud Build (no local Docker needed!)
# ---------------------------------------------------------------------------
Write-Host ">>> Step 3/5: Building Docker image with Cloud Build..." -ForegroundColor Yellow
Write-Host "    This takes 5-10 minutes (downloading OmniParser V2 weights: ~3GB)..."

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

gcloud builds submit $ScriptDir `
    --project=$PROJECT_ID `
    --region=$REGION `
    --tag=$REGISTRY `
    --timeout=1800 `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Cloud Build failed" }

Write-Host "    Image built and pushed: $REGISTRY" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Step 4: Deploy to Cloud Run with L4 GPU
# ---------------------------------------------------------------------------
Write-Host ">>> Step 4/5: Deploying to Cloud Run..." -ForegroundColor Yellow

gcloud run deploy $SERVICE_NAME `
    --project=$PROJECT_ID `
    --region=$REGION `
    --image=$REGISTRY `
    --cpu=$CPU `
    --memory=$MEMORY `
    --gpu=$GPU_COUNT `
    --gpu-type=$GPU_TYPE `
    --min-instances=$MIN_INSTANCES `
    --max-instances=$MAX_INSTANCES `
    --port=$PORT `
    --timeout=$TIMEOUT `
    --concurrency=$CONCURRENCY `
    --no-cpu-throttling `
    --execution-environment=gen2 `
    --allow-unauthenticated `
    --no-use-http2 `
    --set-env-vars="NVIDIA_VISIBLE_DEVICES=all" `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Cloud Run deployment failed" }

Write-Host "    Service deployed." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Step 5: Get URL and test
# ---------------------------------------------------------------------------
Write-Host ">>> Step 5/5: Fetching service URL..." -ForegroundColor Yellow

$SERVICE_URL = gcloud run services describe $SERVICE_NAME `
    --project=$PROJECT_ID `
    --region=$REGION `
    --format='value(status.url)'

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Deployment Complete!" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Service URL:  $SERVICE_URL" -ForegroundColor Green
Write-Host ""
Write-Host "  Health check:"
Write-Host "    curl $SERVICE_URL/health"
Write-Host ""
Write-Host "  Parse screenshot:"
Write-Host "    curl -X POST $SERVICE_URL/parse -F 'file=@screenshot.png'"
Write-Host ""
Write-Host "  Update config/dawmind.toml:"
Write-Host "    [vision]"
Write-Host "    omniparser_endpoint = `"$SERVICE_URL/parse`""
Write-Host ""
Write-Host "  Cost: ~`$0.70/hr ONLY when processing." -ForegroundColor Yellow
Write-Host "  At idle (scale-to-zero): `$0.00/hr" -ForegroundColor Green
Write-Host ""
Write-Host "  To delete (stop all billing):"
Write-Host "    gcloud run services delete $SERVICE_NAME --region=$REGION --quiet"
Write-Host ""
