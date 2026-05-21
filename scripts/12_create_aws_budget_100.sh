#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUDGET_NAME="${BUDGET_NAME:-financial-sentiment-radar-100-usd}"
EMAIL="${BUDGET_EMAIL:-}"

if [[ -z "${EMAIL}" ]]; then
  echo "ERROR: set BUDGET_EMAIL before running this script." >&2
  echo "Example: export BUDGET_EMAIL=you@example.com" >&2
  exit 1
fi

cat > /tmp/budget.json <<'JSON'
{
  "BudgetName": "financial-sentiment-radar-100-usd",
  "BudgetLimit": {"Amount": "100", "Unit": "USD"},
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST",
  "CostFilters": {},
  "CostTypes": {
    "IncludeTax": true,
    "IncludeSubscription": true,
    "UseBlended": false,
    "IncludeRefund": false,
    "IncludeCredit": false,
    "IncludeUpfront": true,
    "IncludeRecurring": true,
    "IncludeOtherSubscription": true,
    "IncludeSupport": true,
    "IncludeDiscount": true,
    "UseAmortized": false
  }
}
JSON

python3 - <<PY
import json
path = '/tmp/budget.json'
with open(path) as f:
    data = json.load(f)
data['BudgetName'] = '${BUDGET_NAME}'
with open(path, 'w') as f:
    json.dump(data, f)
PY

cat > /tmp/notifications.json <<JSON
[
  {
    "Notification": {
      "NotificationType": "ACTUAL",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 80,
      "ThresholdType": "PERCENTAGE"
    },
    "Subscribers": [
      {"SubscriptionType": "EMAIL", "Address": "${EMAIL}"}
    ]
  },
  {
    "Notification": {
      "NotificationType": "FORECASTED",
      "ComparisonOperator": "GREATER_THAN",
      "Threshold": 100,
      "ThresholdType": "PERCENTAGE"
    },
    "Subscribers": [
      {"SubscriptionType": "EMAIL", "Address": "${EMAIL}"}
    ]
  }
]
JSON

aws budgets create-budget \
  --account-id "${ACCOUNT_ID}" \
  --budget file:///tmp/budget.json \
  --notifications-with-subscribers file:///tmp/notifications.json

echo "Created AWS budget ${BUDGET_NAME} for account ${ACCOUNT_ID}. Confirm the email subscription if AWS sends a confirmation email."
