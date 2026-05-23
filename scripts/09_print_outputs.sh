#!/usr/bin/env bash
# Utility script for Financial Sentiment Radar.
#
# Run from the repository root after loading the environment variables
# required by the command being executed.
# Documented by Financial Sentiment Radar documentation patch.

set -euo pipefail

source config/generated.env

aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$ECS_STACK" \
  --query "Stacks[0].Outputs" \
  --output table
