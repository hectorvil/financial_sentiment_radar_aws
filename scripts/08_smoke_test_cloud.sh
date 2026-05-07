#!/usr/bin/env bash
set -euo pipefail

source config/generated.env

APP_URL="$(aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$ECS_STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='AppURL'].OutputValue | [0]" \
  --output text)"

echo "Testing $APP_URL/_stcore/health"
curl -fsS "$APP_URL/_stcore/health"
echo

echo "App URL: $APP_URL"
