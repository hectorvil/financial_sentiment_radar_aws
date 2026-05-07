#!/usr/bin/env bash
set -euo pipefail

source config/generated.env

USE_BEDROCK="${USE_BEDROCK:-false}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-amazon.titan-text-lite-v1}"
TWITTER_BEARER_SECRET_ARN="${TWITTER_BEARER_SECRET_ARN:-}"
DESIRED_COUNT="${DESIRED_COUNT:-1}"
TASK_CPU="${TASK_CPU:-512}"
TASK_MEMORY="${TASK_MEMORY:-1024}"

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$ECS_STACK" \
  --template-file infra/cloudformation/01_fargate_streamlit.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName="$PROJECT_NAME" \
    Environment="$ENVIRONMENT" \
    ImageUri="$IMAGE_URI" \
    DataBucketName="$DATA_BUCKET" \
    DesiredCount="$DESIRED_COUNT" \
    TaskCpu="$TASK_CPU" \
    TaskMemory="$TASK_MEMORY" \
    UseBedrock="$USE_BEDROCK" \
    BedrockModelId="$BEDROCK_MODEL_ID" \
    TwitterBearerSecretArn="$TWITTER_BEARER_SECRET_ARN"

./scripts/09_print_outputs.sh
