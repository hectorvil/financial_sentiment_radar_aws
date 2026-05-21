#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-financial-sentiment-radar}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
ECS_STACK_NAME="${ECS_STACK_NAME:-${PROJECT_NAME}-${ENVIRONMENT}-ecs}"
LIVE_STACK_NAME="${LIVE_STACK_NAME:-${PROJECT_NAME}-${ENVIRONMENT}-live-ingestion-athena}"
DATA_BUCKET="${DATA_BUCKET:-${APP_BUCKET:-${S3_BUCKET:-}}}"
TWITTER_BEARER_SECRET_ARN="${TWITTER_BEARER_SECRET_ARN:-}"
SENTIMENT_MODEL="${SENTIMENT_MODEL:-finbert}"
FINBERT_MODEL_NAME="${FINBERT_MODEL_NAME:-ProsusAI/finbert}"
FINBERT_BATCH_SIZE="${FINBERT_BATCH_SIZE:-16}"
LIVE_MAX_RESULTS="${LIVE_MAX_RESULTS:-10}"
LIVE_TICKERS="${LIVE_TICKERS:-NVDA,TSLA,AAPL,GOOGL,MSFT,AMZN,JPM,BBVA}"
TASK_CPU="${TASK_CPU:-1024}"
TASK_MEMORY="${TASK_MEMORY:-4096}"

if [[ -f config/generated.env ]]; then
  # shellcheck disable=SC1091
  source config/generated.env
  DATA_BUCKET="${DATA_BUCKET:-${APP_BUCKET:-${S3_BUCKET:-}}}"
fi

if [[ -z "${DATA_BUCKET}" ]]; then
  echo "ERROR: DATA_BUCKET/APP_BUCKET/S3_BUCKET is required." >&2
  exit 1
fi

if [[ -z "${TWITTER_BEARER_SECRET_ARN}" ]]; then
  echo "ERROR: TWITTER_BEARER_SECRET_ARN is required." >&2
  echo "Create it with: aws secretsmanager create-secret --name financial-sentiment-radar/twitter-bearer --secret-string 'TOKEN'" >&2
  exit 1
fi

echo "Discovering ECS service network configuration from ${PROJECT_NAME}-${ENVIRONMENT}-service"
SERVICE_JSON=$(aws ecs describe-services \
  --region "${AWS_REGION}" \
  --cluster "${PROJECT_NAME}-${ENVIRONMENT}-cluster" \
  --services "${PROJECT_NAME}-${ENVIRONMENT}-service" \
  --query 'services[0]' \
  --output json)

CLUSTER_ARN=$(echo "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["clusterArn"])')
TASK_DEF_ARN=$(echo "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["taskDefinition"])')
SUBNET_IDS=$(echo "${SERVICE_JSON}" | python3 -c 'import json,sys; print(",".join(json.load(sys.stdin)["networkConfiguration"]["awsvpcConfiguration"]["subnets"]))')
SECURITY_GROUP_ID=$(echo "${SERVICE_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["networkConfiguration"]["awsvpcConfiguration"]["securityGroups"][0])')
IMAGE_URI=$(aws ecs describe-task-definition \
  --region "${AWS_REGION}" \
  --task-definition "${TASK_DEF_ARN}" \
  --query 'taskDefinition.containerDefinitions[0].image' \
  --output text)

echo "Cluster ARN: ${CLUSTER_ARN}"
echo "Image URI: ${IMAGE_URI}"
echo "Subnets: ${SUBNET_IDS}"
echo "Security Group: ${SECURITY_GROUP_ID}"
echo "Data bucket: ${DATA_BUCKET}"

aws cloudformation deploy \
  --region "${AWS_REGION}" \
  --stack-name "${LIVE_STACK_NAME}" \
  --template-file infra/cloudformation/02_live_ingestion_athena.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName="${PROJECT_NAME}" \
    Environment="${ENVIRONMENT}" \
    AwsRegion="${AWS_REGION}" \
    DataBucket="${DATA_BUCKET}" \
    ImageUri="${IMAGE_URI}" \
    ClusterArn="${CLUSTER_ARN}" \
    SubnetIds="${SUBNET_IDS}" \
    SecurityGroupId="${SECURITY_GROUP_ID}" \
    TwitterBearerSecretArn="${TWITTER_BEARER_SECRET_ARN}" \
    LiveMaxResults="${LIVE_MAX_RESULTS}" \
    LiveTickers="${LIVE_TICKERS}" \
    SentimentModel="${SENTIMENT_MODEL}" \
    FinbertModelName="${FINBERT_MODEL_NAME}" \
    FinbertBatchSize="${FINBERT_BATCH_SIZE}" \
    TaskCpu="${TASK_CPU}" \
    TaskMemory="${TASK_MEMORY}"

aws cloudformation describe-stacks \
  --region "${AWS_REGION}" \
  --stack-name "${LIVE_STACK_NAME}" \
  --query 'Stacks[0].Outputs' \
  --output table
