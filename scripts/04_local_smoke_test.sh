#!/usr/bin/env bash
# Utility script for Financial Sentiment Radar.
#
# Run from the repository root after loading the environment variables
# required by the command being executed.
# Documented by Financial Sentiment Radar documentation patch.

set -euo pipefail

PORT="${PORT:-8501}"
LOG_FILE="${LOG_FILE:-/tmp/financial_sentiment_streamlit.log}"

cleanup() {
  if [[ -n "${STREAMLIT_PID:-}" ]]; then
    kill "$STREAMLIT_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

PYTHONPATH=src uv run streamlit run app/streamlit_app.py \
  --server.port "$PORT" \
  --server.address 0.0.0.0 \
  --server.headless true \
  >"$LOG_FILE" 2>&1 &
STREAMLIT_PID=$!

for _ in {1..30}; do
  if curl -fsS "http://localhost:${PORT}/_stcore/health" >/dev/null; then
    echo "OK: Streamlit responde en http://localhost:${PORT}"
    exit 0
  fi
  sleep 2
done

echo "Streamlit no respondió. Log:" >&2
cat "$LOG_FILE" >&2
exit 1
