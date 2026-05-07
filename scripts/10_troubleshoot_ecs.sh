#!/usr/bin/env bash
set -euo pipefail

source config/generated.env

SERVICE_NAME="${PROJECT_NAME}-${ENVIRONMENT}-service"
CLUSTER_NAME="${PROJECT_NAME}-${ENVIRONMENT}-cluster"
LOG_GROUP="/ecs/${PROJECT_NAME}-${ENVIRONMENT}"

echo "== ECS service events =="
aws ecs describe-services \
  --region "$AWS_REGION" \
  --cluster "$CLUSTER_NAME" \
  --services "$SERVICE_NAME" \
  --query 'services[0].events[0:10].[createdAt,message]' \
  --output table || true

echo

echo "== Running tasks =="
TASK_ARNS=$(aws ecs list-tasks \
  --region "$AWS_REGION" \
  --cluster "$CLUSTER_NAME" \
  --service-name "$SERVICE_NAME" \
  --query 'taskArns[]' \
  --output text || true)

echo "${TASK_ARNS:-No tasks found}"

if [[ -n "${TASK_ARNS:-}" && "$TASK_ARNS" != "None" ]]; then
  aws ecs describe-tasks \
    --region "$AWS_REGION" \
    --cluster "$CLUSTER_NAME" \
    --tasks $TASK_ARNS \
    --query 'tasks[].{lastStatus:lastStatus,desiredStatus:desiredStatus,healthStatus:healthStatus,stoppedReason:stoppedReason,containers:containers[].{name:name,lastStatus:lastStatus,reason:reason,exitCode:exitCode}}' \
    --output yaml || true
fi

echo

echo "== Últimos logs de CloudWatch =="
aws logs describe-log-streams \
  --region "$AWS_REGION" \
  --log-group-name "$LOG_GROUP" \
  --order-by LastEventTime \
  --descending \
  --max-items 3 \
  --query 'logStreams[].logStreamName' \
  --output text | tr '\t' '\n' | while read -r stream; do
    [[ -z "$stream" ]] && continue
    echo "-- $stream --"
    aws logs get-log-events \
      --region "$AWS_REGION" \
      --log-group-name "$LOG_GROUP" \
      --log-stream-name "$stream" \
      --limit 20 \
      --query 'events[].message' \
      --output text || true
  done
