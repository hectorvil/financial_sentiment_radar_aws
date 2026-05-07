#!/usr/bin/env bash
set -euo pipefail

source config/generated.env

aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$ECS_STACK" \
  --query "Stacks[0].Outputs" \
  --output table
