#!/usr/bin/env bash
# deploy.sh — deploy to Google Cloud Run
#
# Usage:
#   ./scripts/deploy.sh --project my-gcp-project --region us-central1
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - Artifact Registry repository created
#   - Cloud SQL instance running
#   - Redis (Memorystore) instance running
#   - Secrets created in Secret Manager

set -euo pipefail

PROJECT_ID=""
REGION="us-central1"
IMAGE_TAG=$(git rev-parse --short HEAD)

while [[ $# -gt 0 ]]; do
  case $1 in
    --project) PROJECT_ID="$2"; shift 2 ;;
    --region)  REGION="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$PROJECT_ID" ]]; then
  echo "Error: --project is required"
  exit 1
fi

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/aiengos"
BACKEND_IMAGE="${REGISTRY}/backend:${IMAGE_TAG}"

echo "▶ Building backend image..."
docker build \
  -f apps/backend/Dockerfile \
  -t "${BACKEND_IMAGE}" \
  .

echo "▶ Pushing to Artifact Registry..."
docker push "${BACKEND_IMAGE}"

echo "▶ Deploying to Cloud Run..."
# Substitute PROJECT_ID and REGION in the Cloud Run config
sed \
  -e "s/PROJECT_ID/${PROJECT_ID}/g" \
  -e "s/REGION/${REGION}/g" \
  infrastructure/cloudrun/backend.yaml \
  | sed "s|backend:latest|backend:${IMAGE_TAG}|g" \
  > /tmp/backend-deploy.yaml

gcloud run services replace /tmp/backend-deploy.yaml \
  --project="${PROJECT_ID}" \
  --region="${REGION}"

echo ""
echo "✓ Deployment complete"
echo "  Service URL: $(gcloud run services describe aiengos-backend --project=${PROJECT_ID} --region=${REGION} --format='value(status.url)')"
