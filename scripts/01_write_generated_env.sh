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
GENERATED_ENV="${GENERATED_ENV:-config/generated.env}"

get_output() {
  local key="$1"
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$FOUNDATION_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='${key}'].OutputValue | [0]" \
    --output text
}

DATA_BUCKET="$(get_output DataBucketName)"
ECR_URI="$(get_output EcrRepositoryUri)"

cat > "$GENERATED_ENV" <<ENV
PROJECT_NAME=$PROJECT_NAME
ENVIRONMENT=$ENVIRONMENT
AWS_REGION=$AWS_REGION
FOUNDATION_STACK=$FOUNDATION_STACK
ECS_STACK=${PROJECT_NAME}-${ENVIRONMENT}-ecs
DATA_BUCKET=$DATA_BUCKET
S3_BUCKET=$DATA_BUCKET
ECR_REPOSITORY_URI=$ECR_URI
IMAGE_TAG=app-latest
IMAGE_URI=$ECR_URI:app-latest
ENV

echo "Wrote $GENERATED_ENV"
cat "$GENERATED_ENV"
