# Feature Engine: X/Twitter live ingestion + Medallion + Athena

Esta extensión agrega una ingesta programada de X/Twitter cada 2 horas, limitada a 10 tweets por corrida, con almacenamiento en S3 en capas medallion y tablas consultables en Athena.

## Objetivo

- Usar FinBERT o lexicon para clasificar tweets financieros.
- Usar Secrets Manager para guardar el bearer token de X/Twitter.
- Evitar búsquedas abiertas con ruido.
- Consultar solo compañías y cuentas financieras controladas.
- Ingestar 10 tweets cada 2 horas.
- Guardar datos en S3:
  - `bronze/twitter_live/` para respuestas raw de X API.
  - `silver/tweets/` para registros tweet-level estandarizados.
  - `gold/sentiment_by_ticker_daily/` para agregados por ticker/día.
  - `gold/twitter_live/latest.parquet` para la pestaña Streamlit `Tweets live`.
- Crear tablas Glue/Athena con partition projection.

## Costos y límites

La ingesta propuesta hace 12 corridas al día y lee 10 tweets por corrida:

```text
12 corridas/día * 10 tweets = 120 tweets/día
120 * 30 = 3,600 tweets/mes
```

Con pricing público actual de X para Posts Read alrededor de `0.005 USD` por recurso, el costo esperado de lectura sería aproximadamente:

```text
3,600 * 0.005 = 18 USD/mes
```

Para evitar sorpresas:

1. En X Developer Console configura spending limit de `50 USD` o máximo `100 USD` por ciclo.
2. Desactiva auto-recharge o usa un monto pequeño.
3. En AWS crea Budget de `100 USD` con el script `scripts/12_create_aws_budget_100.sh`.
4. Mantén la ingesta en `LIVE_MAX_RESULTS=10`.
5. No uses queries libres contra toda la red social.

## Crear cuenta y app de desarrollador X desde cero

1. Entra a `https://developer.x.com/` o `https://console.x.com/`.
2. Inicia sesión con tu cuenta de X.
3. Crea un proyecto/app.
4. Activa X API v2.
5. En Billing/Usage compra créditos mínimos necesarios para pruebas.
6. Configura un spending limit menor o igual a `100 USD` por ciclo.
7. Desactiva auto-recharge si no quieres cargos automáticos.
8. Genera el Bearer Token de la app.
9. No lo pegues en código, GitHub ni `.env` versionado.

## Guardar Bearer Token en Secrets Manager

```bash
aws secretsmanager create-secret \
  --region us-east-1 \
  --name financial-sentiment-radar/twitter-bearer \
  --secret-string "TU_BEARER_TOKEN"
```

Obtén el ARN:

```bash
export TWITTER_BEARER_SECRET_ARN=$(aws secretsmanager describe-secret \
  --region us-east-1 \
  --secret-id financial-sentiment-radar/twitter-bearer \
  --query ARN \
  --output text)

echo "$TWITTER_BEARER_SECRET_ARN"
```

## Crear branch feature/engine

```bash
git checkout main
git pull
git checkout -b feature/engine
```

Aplica el paquete:

```bash
/tmp/feature_engine_patch/apply_feature_engine_extension.sh "$PWD"
```

O copia manualmente `files_to_copy/` a la raíz del repo y luego ejecuta:

```bash
python3 /tmp/feature_engine_patch/apply_feature_engine_changes.py
```

## Validación local

```bash
uv sync --all-groups
PYTHONPATH=src uv run pytest -q
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
```

## Prueba manual de una corrida live

Puedes ejecutar una corrida local si tienes `TWITTER_BEARER` exportado:

```bash
source config/generated.env

export APP_BUCKET=financial-sentiment-radar-dev-foundatio-databucket-coafx0g9hqds
export S3_BUCKET="$APP_BUCKET"
export DATA_BUCKET="$APP_BUCKET"
export AWS_REGION=us-east-1
export TWITTER_BEARER="TU_BEARER_TOKEN"
export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16

PYTHONPATH=src uv run python -m financial_sentiment.jobs.live_twitter_ingest \
  --max-results 10 \
  --ticker NVDA
```

Verifica S3:

```bash
aws s3 ls "s3://$APP_BUCKET/bronze/twitter_live/" --recursive
aws s3 ls "s3://$APP_BUCKET/silver/tweets/" --recursive
aws s3 ls "s3://$APP_BUCKET/gold/sentiment_by_ticker_daily/" --recursive
aws s3 ls "s3://$APP_BUCKET/gold/twitter_live/" --recursive
```

## Deploy de ingesta programada + Athena

Primero asegúrate de tener la app principal ya desplegada y la imagen en ECR.

```bash
source config/generated.env

export PROJECT_NAME=financial-sentiment-radar
export ENVIRONMENT=dev
export AWS_REGION=us-east-1
export APP_BUCKET=financial-sentiment-radar-dev-foundatio-databucket-coafx0g9hqds
export S3_BUCKET="$APP_BUCKET"
export DATA_BUCKET="$APP_BUCKET"

export TWITTER_BEARER_SECRET_ARN="arn:aws:secretsmanager:us-east-1:494321812137:secret:financial-sentiment-radar/twitter-bearer-XXXX"
export LIVE_MAX_RESULTS=10
export LIVE_TICKERS=NVDA,TSLA,AAPL,GOOGL,MSFT,AMZN,JPM,BBVA
export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16
export TASK_CPU=1024
export TASK_MEMORY=4096

./scripts/11_deploy_live_ingestion_athena.sh
```

Este script descubre la red del servicio ECS existente y crea:

- Task definition de ingesta live.
- Schedule cada 2 horas.
- Roles IAM.
- Log group.
- Glue database.
- Glue tables para Athena.

## Ejecutar la tarea inmediatamente para probar

Después del deploy, puedes esperar a la siguiente ventana de 2 horas o correr manualmente una task desde ECS Console usando la task definition `financial-sentiment-radar-dev-live-ingestion-task`.

También puedes cambiar temporalmente el schedule a `rate(5 minutes)` para pruebas, pero vuelve a `rate(2 hours)` para controlar costos.

## Pestaña Streamlit: Tweets live

El patch agrega una pestaña llamada `Tweets live`.

La pestaña lee:

```text
gold/twitter_live/latest.parquet
```

Muestra:

- KPIs de tweets live.
- Ranking de tickers por `neg_ratio`.
- Tendencia temporal por sentimiento.
- Tabla de tweets capturados.

## Athena

La plantilla crea una base Glue:

```text
financial_sentiment_radar
```

Tablas:

```text
silver_tweets
gold_sentiment_by_ticker_daily
```

Consultas de ejemplo están en:

```text
sql/athena_queries.sql
```

Ejemplo:

```sql
SELECT ticker, created_date, sum(total) total_mentions, sum(negative) negative_mentions
FROM financial_sentiment_radar.gold_sentiment_by_ticker_daily
WHERE source = 'twitter_live'
GROUP BY ticker, created_date
ORDER BY created_date DESC, negative_mentions DESC;
```

## Manual uploads también entran a medallion

El patch modifica Streamlit para que cada archivo manual procesado también escriba:

```text
silver/tweets/source=manual_upload/ingestion_date=YYYY-MM-DD/*.parquet
gold/sentiment_by_ticker_daily/source=manual_upload/ingestion_date=YYYY-MM-DD/*.parquet
```

Así Athena puede consultar tanto ingestas manuales como Twitter live.

## Commit

```bash
git status --short
git add app src tests infra scripts docs sql
git commit -m "Add live Twitter ingestion and Athena medallion datasets"
git push -u origin feature/engine
```

## Merge a main

Cuando todo esté validado:

```bash
git checkout main
git pull
git merge feature/engine
git push
```
