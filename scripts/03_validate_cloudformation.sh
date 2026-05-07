#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"

echo "Validando CloudFormation en región ${AWS_REGION}"
aws cloudformation validate-template \
  --region "$AWS_REGION" \
  --template-body file://infra/cloudformation/00_foundation.yml >/dev/null

echo "OK: 00_foundation.yml"

aws cloudformation validate-template \
  --region "$AWS_REGION" \
  --template-body file://infra/cloudformation/01_fargate_streamlit.yml >/dev/null

echo "OK: 01_fargate_streamlit.yml"
