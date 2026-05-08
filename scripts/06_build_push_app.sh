#!/usr/bin/env bash
set -euo pipefail

source config/generated.env

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

echo "Building image for account ${ACCOUNT_ID} in ${AWS_REGION}"
echo "Image URI: ${IMAGE_URI}"

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Fargate espera una imagen linux/amd64. En Mac, especialmente Apple Silicon,
# un docker build normal puede generar una imagen incompatible.
docker buildx build \
  --platform linux/amd64 \
  -t "${IMAGE_URI}" \
  --push .

echo "Pushed ${IMAGE_URI}"
