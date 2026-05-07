#!/usr/bin/env bash
set -euo pipefail

source config/generated.env

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
echo "Building image for account $ACCOUNT_ID in $AWS_REGION"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker build -t "financial-sentiment-radar:${IMAGE_TAG}" .
docker tag "financial-sentiment-radar:${IMAGE_TAG}" "$IMAGE_URI"
docker push "$IMAGE_URI"

echo "Pushed $IMAGE_URI"
