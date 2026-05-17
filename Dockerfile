FROM python:3.12-slim

ARG PRELOAD_FINBERT=false
ARG FINBERT_MODEL_NAME=ProsusAI/finbert

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Optional: bake FinBERT weights into the image to reduce first-start latency.
# Keep PRELOAD_FINBERT=false by default because the image becomes much larger.
RUN if [ "$PRELOAD_FINBERT" = "true" ]; then \
      python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; model='${FINBERT_MODEL_NAME}'; AutoTokenizer.from_pretrained(model); AutoModelForSequenceClassification.from_pretrained(model)"; \
    fi

COPY app ./app
COPY src ./src
COPY data ./data

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
