# Implementación FinBERT + Bedrock para Financial Sentiment Radar

Esta guía secundaria explica cómo instalar, probar y desplegar la extensión que agrega:

1. **FinBERT** para clasificar sentimiento financiero tweet por tweet.
2. **Amazon Bedrock** para inferir la columna de texto cuando los archivos CSV/Parquet tienen esquemas variables.
3. **Amazon Bedrock** para responder consultas del usuario con evidencia recuperada del corpus procesado.
4. Persistencia de `raw/`, `schema-mappings/`, `processed/` y `outputs/` en S3.

La arquitectura resultante mantiene Streamlit en ECS Fargate y conserva el modelo léxico como default para que el producto siga siendo barato y estable.

---

## 1. Qué cambia en el repo

Archivos nuevos:

```text
src/financial_sentiment/schema_inference.py
src/financial_sentiment/finbert.py
src/financial_sentiment/jobs/__init__.py
src/financial_sentiment/jobs/batch_process.py
tests/test_schema_inference.py
tests/test_finbert_interface.py
docs/README_FINBERT_BEDROCK_IMPLEMENTACION.md
```

Archivos modificados:

```text
app/streamlit_app.py
src/financial_sentiment/config.py
src/financial_sentiment/pipeline.py
src/financial_sentiment/storage.py
infra/cloudformation/01_fargate_streamlit.yml
scripts/06_build_push_app.sh
scripts/07_deploy_ecs.sh
Dockerfile
pyproject.toml
requirements.txt
```

---

## 2. Modelo de operación

### Flujo batch

```text
CSV/Parquet cargado en Streamlit
  ↓
Reglas locales detectan columna de texto
  ↓
Si hay ambigüedad y USE_BEDROCK_SCHEMA=true, Bedrock decide columna
  ↓
Usuario confirma o cambia la columna en la UI
  ↓
Dataset se estandariza a columna text
  ↓
Lexicon o FinBERT clasifica sentimiento
  ↓
Resultados se guardan en S3/local
  ↓
Streamlit muestra dashboard y consultas
```

### Flujo de consulta

```text
Usuario pregunta: “¿qué pasa con Tesla?”
  ↓
Retriever TF-IDF recupera evidencia del corpus
  ↓
Si USE_BEDROCK=true, Bedrock genera respuesta ejecutiva
  ↓
Si Bedrock falla o está apagado, respuesta extractiva local
```

---

## 3. Variables de entorno nuevas

| Variable | Default | Descripción |
|---|---|---|
| `SENTIMENT_MODEL` | `lexicon` | `lexicon` o `finbert`. |
| `FINBERT_MODEL_NAME` | `ProsusAI/finbert` | Modelo Hugging Face a cargar. |
| `FINBERT_BATCH_SIZE` | `16` | Batch size para inferencia en CPU. |
| `USE_BEDROCK` | `false` | Activa Bedrock para respuestas en consultas. |
| `USE_BEDROCK_SCHEMA` | igual a `USE_BEDROCK` | Activa Bedrock para inferencia de esquema. |
| `BEDROCK_MODEL_ID` | `amazon.titan-text-lite-v1` | Modelo Bedrock para schema/chat. |
| `S3_RAW_PREFIX` | `raw/` | Prefijo para archivos raw. |
| `S3_PROCESSED_PREFIX` | `processed/` | Prefijo para archivos procesados. |
| `S3_SCHEMA_PREFIX` | `schema-mappings/` | Prefijo para mappings de esquema. |
| `S3_OUTPUTS_PREFIX` | `outputs/` | Prefijo para outputs. |

---

## 4. Instalación local

Desde la raíz del repo:

```bash
uv sync --all-groups
```

Si `uv` no está instalado:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
```

---

## 5. Validar que no se rompió el proyecto

```bash
PYTHONPATH=src uv run pytest -q
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
```

El modelo FinBERT **no se descarga durante los tests**. Los tests usan mocks o validan la interfaz sin cargar pesos reales.

---

## 6. Correr Streamlit local con modelo léxico

Este modo es barato y rápido:

```bash
export SENTIMENT_MODEL=lexicon
export USE_BEDROCK=false
export USE_BEDROCK_SCHEMA=false
PYTHONPATH=src uv run streamlit run app/streamlit_app.py
```

Abre:

```text
http://localhost:8501
```

---

## 7. Correr Streamlit local con FinBERT

Este modo descargará `ProsusAI/finbert` la primera vez:

```bash
export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16
export USE_BEDROCK=false
export USE_BEDROCK_SCHEMA=false
PYTHONPATH=src uv run streamlit run app/streamlit_app.py
```

Notas:

- La primera ejecución puede tardar por la descarga del modelo.
- En CPU es más lento que el modelo léxico.
- Para archivos grandes, procesa muestras pequeñas o usa el job batch.

---

## 8. Correr Bedrock para inferencia de esquema

Primero habilita acceso al modelo en la consola de Amazon Bedrock.

Luego localmente:

```bash
export AWS_REGION=us-east-1
export USE_BEDROCK=true
export USE_BEDROCK_SCHEMA=true
export BEDROCK_MODEL_ID=amazon.titan-text-lite-v1
PYTHONPATH=src uv run streamlit run app/streamlit_app.py
```

La app usa reglas primero. Bedrock solo se invoca si la columna de texto es ambigua.

---

## 9. Job batch CLI

Procesar CSV/Parquet local con el modelo léxico:

```bash
PYTHONPATH=src uv run python -m financial_sentiment.jobs.batch_process \
  --input-path data/sample_tweets.csv \
  --output-path data/processed/sample_processed.parquet \
  --sentiment-model lexicon
```

Procesar archivo en S3 con FinBERT y Bedrock schema inference:

```bash
PYTHONPATH=src uv run python -m financial_sentiment.jobs.batch_process \
  --input-path s3://TU_BUCKET/raw/tweets/dataset.parquet \
  --output-path s3://TU_BUCKET/processed/tweets/dataset_processed.parquet \
  --use-bedrock-schema \
  --sentiment-model finbert \
  --aws-region us-east-1 \
  --bedrock-model-id amazon.titan-text-lite-v1 \
  --finbert-model-name ProsusAI/finbert \
  --finbert-batch-size 16
```

---

## 10. Docker local

Para construir imagen compatible con Fargate:

```bash
docker buildx build \
  --platform linux/amd64 \
  -t financial-sentiment-radar:finbert-local \
  --load .
```

Correr con modelo léxico:

```bash
docker run --rm -p 8501:8501 \
  -e DATA_BACKEND=local \
  -e AWS_REGION=us-east-1 \
  -e SENTIMENT_MODEL=lexicon \
  financial-sentiment-radar:finbert-local
```

Correr con FinBERT:

```bash
docker run --rm -p 8501:8501 \
  -e DATA_BACKEND=local \
  -e AWS_REGION=us-east-1 \
  -e SENTIMENT_MODEL=finbert \
  -e FINBERT_MODEL_NAME=ProsusAI/finbert \
  -e FINBERT_BATCH_SIZE=16 \
  financial-sentiment-radar:finbert-local
```

---

## 11. Despliegue AWS con modelo léxico

```bash
export PROJECT_NAME=financial-sentiment-radar
export ENVIRONMENT=dev
export AWS_REGION=us-east-1
export SENTIMENT_MODEL=lexicon
export USE_BEDROCK=false
export USE_BEDROCK_SCHEMA=false

./scripts/03_validate_cloudformation.sh
./scripts/00_deploy_foundation.sh
source config/generated.env
./scripts/06_build_push_app.sh
./scripts/07_deploy_ecs.sh
./scripts/09_print_outputs.sh
./scripts/08_smoke_test_cloud.sh
```

---

## 12. Despliegue AWS con FinBERT + Bedrock

FinBERT necesita más memoria que el modelo léxico. Usa 1 vCPU y 4 GB RAM para reducir riesgo de que la task se caiga.

```bash
export PROJECT_NAME=financial-sentiment-radar
export ENVIRONMENT=dev
export AWS_REGION=us-east-1

export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16

export USE_BEDROCK=true
export USE_BEDROCK_SCHEMA=true
export BEDROCK_MODEL_ID=amazon.titan-text-lite-v1

export TASK_CPU=1024
export TASK_MEMORY=4096

source config/generated.env
./scripts/06_build_push_app.sh
./scripts/07_deploy_ecs.sh
./scripts/09_print_outputs.sh
./scripts/08_smoke_test_cloud.sh
```

Si quieres que la imagen ya incluya el modelo FinBERT descargado durante build:

```bash
export PRELOAD_FINBERT=true
./scripts/06_build_push_app.sh
```

Eso reduce latencia de primer arranque, pero sube mucho el tamaño de la imagen.

---

## 13. Diagnóstico en AWS

Ver estado del stack:

```bash
aws cloudformation describe-stacks \
  --region us-east-1 \
  --stack-name financial-sentiment-radar-dev-ecs \
  --query "Stacks[0].StackStatus" \
  --output text
```

Ver eventos ECS:

```bash
aws ecs describe-services \
  --region us-east-1 \
  --cluster financial-sentiment-radar-dev-cluster \
  --services financial-sentiment-radar-dev-service \
  --query "services[0].events[0:10].[createdAt,message]" \
  --output json
```

Ver logs:

```bash
aws logs tail "/ecs/financial-sentiment-radar-dev" \
  --region us-east-1 \
  --since 30m
```

O usa:

```bash
./scripts/10_troubleshoot_ecs.sh
```

---

## 14. Costos y recomendaciones

- `SENTIMENT_MODEL=lexicon` es el default y el más barato.
- `SENTIMENT_MODEL=finbert` consume más memoria y CPU.
- Bedrock debe usarse solo para:
  - inferir esquema en archivos ambiguos;
  - resumir evidencia recuperada, no miles de tweets completos.
- Para ahorrar cuando no estén evaluando la app:

```bash
aws ecs update-service \
  --region us-east-1 \
  --cluster financial-sentiment-radar-dev-cluster \
  --service financial-sentiment-radar-dev-service \
  --desired-count 0
```

Encender de nuevo:

```bash
aws ecs update-service \
  --region us-east-1 \
  --cluster financial-sentiment-radar-dev-cluster \
  --service financial-sentiment-radar-dev-service \
  --desired-count 1
```

---

## 15. Checklist final

Antes de hacer commit:

```bash
git status --short
PYTHONPATH=src uv run pytest -q
uv run ruff check .
```

No subas:

```text
.env
config/generated.env
*.pem
*.key
.venv/
```

Commit sugerido:

```bash
git add app src tests infra scripts docs Dockerfile pyproject.toml requirements.txt
git commit -m "Add FinBERT and Bedrock schema inference pipeline"
git push
```
