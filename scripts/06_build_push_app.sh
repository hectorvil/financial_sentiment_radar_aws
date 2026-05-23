#!/usr/bin/env bash
# Build and push the Streamlit/ECS Docker image.
#
# Required environment variables usually come from config/generated.env.
# The script logs in to ECR, builds the app image, and pushes the tag used by ECS.
# Documented by Financial Sentiment Radar documentation patch.

set -euo pipefail

source config/generated.env

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
PRELOAD_FINBERT="${PRELOAD_FINBERT:-false}"
FINBERT_MODEL_NAME="${FINBERT_MODEL_NAME:-ProsusAI/finbert}"

echo "Building image for account ${ACCOUNT_ID} in ${AWS_REGION}"
echo "Image URI: ${IMAGE_URI}"
echo "PRELOAD_FINBERT=${PRELOAD_FINBERT}"

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Fargate expects linux/amd64. On Mac, a plain docker build can create an
# incompatible arm64 image.
docker buildx build \
  --no-cache \
  --platform linux/amd64 \
  --build-arg PRELOAD_FINBERT="${PRELOAD_FINBERT}" \
  --build-arg FINBERT_MODEL_NAME="${FINBERT_MODEL_NAME}" \
  -t "${IMAGE_URI}" \
  --push .

echo "Pushed ${IMAGE_URI}"
