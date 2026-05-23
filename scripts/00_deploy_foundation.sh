#!/usr/bin/env bash
# Utility script for Financial Sentiment Radar.
#
# Run from the repository root after loading the environment variables
# required by the command being executed.
# Documented by Financial Sentiment Radar documentation patch.

set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-financial-sentiment-radar}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
FOUNDATION_STACK="${FOUNDATION_STACK:-${PROJECT_NAME}-${ENVIRONMENT}-foundation}"
DATA_BUCKET_NAME="${DATA_BUCKET_NAME:-}"

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$FOUNDATION_STACK" \
  --template-file infra/cloudformation/00_foundation.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName="$PROJECT_NAME" \
    Environment="$ENVIRONMENT" \
    DataBucketName="$DATA_BUCKET_NAME"

mkdir -p config
./scripts/01_write_generated_env.sh
