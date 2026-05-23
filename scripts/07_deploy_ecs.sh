#!/usr/bin/env bash
# Deploy the main Streamlit application service to ECS/Fargate.
#
# This script sends CloudFormation parameters such as bucket names, Bedrock flags,
# task CPU/memory, and image URI. If the image tag is unchanged, ECS may require a
# forced new deployment to pull the latest image.
# Documented by Financial Sentiment Radar documentation patch.

set -euo pipefail

source config/generated.env

USE_BEDROCK="${USE_BEDROCK:-false}"
USE_BEDROCK_SCHEMA="${USE_BEDROCK_SCHEMA:-$USE_BEDROCK}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-3-5-haiku-20241022-v1:0}"
SENTIMENT_MODEL="${SENTIMENT_MODEL:-lexicon}"
FINBERT_MODEL_NAME="${FINBERT_MODEL_NAME:-ProsusAI/finbert}"
FINBERT_BATCH_SIZE="${FINBERT_BATCH_SIZE:-16}"
TWITTER_BEARER_SECRET_ARN="${TWITTER_BEARER_SECRET_ARN:-}"
DESIRED_COUNT="${DESIRED_COUNT:-1}"
TASK_CPU="${TASK_CPU:-512}"
TASK_MEMORY="${TASK_MEMORY:-1024}"

# FinBERT is heavier than the lexicon baseline. Use a safer default unless the
# caller explicitly set task resources.
if [ "${SENTIMENT_MODEL}" = "finbert" ]; then
  if [ "${TASK_CPU}" = "512" ]; then
    TASK_CPU="1024"
  fi
  if [ "${TASK_MEMORY}" = "1024" ]; then
    TASK_MEMORY="4096"
  fi
fi

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
    UseBedrockSchema="$USE_BEDROCK_SCHEMA" \
    BedrockModelId="$BEDROCK_MODEL_ID" \
    SentimentModel="$SENTIMENT_MODEL" \
    FinbertModelName="$FINBERT_MODEL_NAME" \
    FinbertBatchSize="$FINBERT_BATCH_SIZE" \
    TwitterBearerSecretArn="$TWITTER_BEARER_SECRET_ARN"

./scripts/09_print_outputs.sh
