# Patch final de estabilidad: Docker CPU, Bedrock Claude, filtros live y +10 empresas

Este patch corrige el fallo de Docker por descarga de paquetes CUDA/NVIDIA, deja Bedrock en Claude 3.5 Haiku, endurece el filtro de ruido para consultas live, mantiene el flujo preview -> ingesta confirmada y agrega 10 empresas al catálogo de Tweets live.

## Cambios principales

- `requirements.txt`: fija `torch==2.5.1+cpu` y usa el índice CPU de PyTorch.
- `Dockerfile`: agrega timeout/retries a `pip install`.
- `pyproject.toml`: actualiza `torch` y configura índice CPU para uv.
- Defaults de Bedrock: cambia `amazon.titan-text-lite-v1` por `anthropic.claude-3-5-haiku-20241022-v1:0`.
- `live_relevance.py`: invoca Bedrock correctamente con formato Claude o Titan, y filtra ruido social/político sin canal financiero.
- `live_search_service.py`: corrige pérdida de `tweet_id` antes de hacer merge.
- `x_api_client.py`: permite que el usuario pida mínimo 3 tweets, aunque X API internamente pida mínimo 10 y luego recorte.
- `live_query_catalog.py`: añade 10 empresas: `META`, `AMD`, `AVGO`, `INTC`, `NFLX`, `ORCL`, `BAC`, `GS`, `WMT`, `DIS`.

## Aplicación

```bash
cd financial_sentiment_radar_aws
git checkout feature/engine
unzip ~/Downloads/final_stability_cpu_bedrock_filters_patch.zip -d /tmp/final_stability_patch
bash /tmp/final_stability_patch/final_stability_patch/apply_final_stability_patch.sh "$PWD"
```

## Validación

```bash
uv sync --all-groups
PYTHONPATH=src uv run pytest -q
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
```

## Build y deploy

```bash
source config/generated.env

export DATA_BACKEND=s3
export APP_BUCKET=financial-sentiment-radar-dev-foundatio-databucket-coafx0g9hqds
export S3_BUCKET="$APP_BUCKET"
export DATA_BUCKET="$APP_BUCKET"

export TWITTER_BEARER_SECRET_ARN=$(aws secretsmanager describe-secret \
  --region us-east-1 \
  --secret-id financial-sentiment-radar/twitter-bearer \
  --query ARN \
  --output text)

export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16

export USE_BEDROCK=true
export USE_BEDROCK_SCHEMA=true
export USE_BEDROCK_RELEVANCE=true
export BEDROCK_MODEL_ID=anthropic.claude-3-5-haiku-20241022-v1:0

export TASK_CPU=1024
export TASK_MEMORY=4096

./scripts/06_build_push_app.sh
./scripts/07_deploy_ecs.sh
./scripts/09_print_outputs.sh
```

## Si Docker vuelve a bajar paquetes NVIDIA

Verifica:

```bash
grep -n "torch\|pytorch" requirements.txt
```

Debe mostrar:

```text
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.5.1+cpu
```

No debe descargar `nvidia_cublas`, `nvidia_cusolver`, etc.

## Validación AWS

```bash
aws ecs describe-task-definition \
  --region us-east-1 \
  --task-definition financial-sentiment-radar-dev-task \
  --query "taskDefinition.containerDefinitions[0].environment[?name=='BEDROCK_MODEL_ID']" \
  --output json
```

Debe devolver:

```json
[
  {
    "name": "BEDROCK_MODEL_ID",
    "value": "anthropic.claude-3-5-haiku-20241022-v1:0"
  }
]
```

## Commit

```bash
git status --short
git add app src tests infra scripts docs sql Dockerfile requirements.txt pyproject.toml
git commit -m "Stabilize final live search build and Bedrock filters"
git push
```
