#!/usr/bin/env bash
# Utility script for Financial Sentiment Radar.
#
# Run from the repository root after loading the environment variables
# required by the command being executed.
# Documented by Financial Sentiment Radar documentation patch.

set -euo pipefail

source config/generated.env

echo "Deleting ECS stack $ECS_STACK"
aws cloudformation delete-stack --region "$AWS_REGION" --stack-name "$ECS_STACK"
aws cloudformation wait stack-delete-complete --region "$AWS_REGION" --stack-name "$ECS_STACK"

echo "Emptying bucket $DATA_BUCKET"
aws s3 rm "s3://${DATA_BUCKET}" --recursive || true

echo "Deleting foundation stack $FOUNDATION_STACK"
aws cloudformation delete-stack --region "$AWS_REGION" --stack-name "$FOUNDATION_STACK"
aws cloudformation wait stack-delete-complete --region "$AWS_REGION" --stack-name "$FOUNDATION_STACK"
