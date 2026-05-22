# Fase final: Consultas live con X/Twitter, traders/influencers, Bedrock y FinBERT

Esta fase mueve la búsqueda live a la pestaña **Consultas**. La pestaña **Tweets live** queda como tablero de lo que ya fue ingerido.

## Experiencia final

El usuario pregunta en lenguaje natural:

```text
¿Qué se dice de Google? ¿Va mal?
¿Se prevé que suba la tasa de interés en México?
¿Qué opinan traders sobre Nvidia?
¿Qué riesgos geopolíticos están moviendo al mercado?
```

La app hace:

```text
Consulta en X/Twitter con máximo 25 tweets
  ↓
Búsqueda amplia en todo X con filtros financieros y sin retweets
  ↓
Bedrock etiqueta ruido/no ruido
  ↓
FinBERT clasifica sentimiento en tweets relevantes
  ↓
Bedrock resume en español
  ↓
Se ingesta a S3 medallion bronze/silver/gold
  ↓
Tweets live actualiza dashboards
```

## Por qué no se limita únicamente a cuentas

Para no perder conversación relevante, la búsqueda interactiva usa el modo:

```text
broad_all_x
```

Esto busca en el universo amplio de X, pero con:

- términos financieros y macro;
- exclusión de retweets;
- exclusión de spam obvio;
- máximo 25 tweets;
- Bedrock para ruido/no ruido;
- FinBERT para sentimiento.

El catálogo de cuentas curadas se usa como señal de confiabilidad para Bedrock y como modo opcional conservador.

## Cuentas curadas

El catálogo incluye medios, instituciones, research y traders/influencers:

### Instituciones

```text
@federalreserve, @NewYorkFed, @ChicagoFed, @USTreasury, @Banxico,
@Hacienda_Mexico, @ecb, @bankofengland, @BIS_org, @IMFNews,
@FMInoticias, @WorldBank
```

### Medios financieros y mercado

```text
@Reuters, @ReutersBiz, @ReutersMarkets, @business, @markets, @CNBC,
@CNBCi, @SquawkCNBC, @FT, @FTMarkets, @FTAlphaville, @ftfinancenews,
@WSJ, @WSJmarkets, @WSJbusiness, @MarketWatch, @YahooFinance,
@Investingcom, @Benzinga, @Stocktwits, @nytimesbusiness, @IBDinvestors
```

### México / LatAm

```text
@ElFinanciero_Mx, @ExpansionMx, @ExpEconomia, @BloombergLinea_,
@eleconomista, @ElEconomistaMx, @Reforma, @BMVMercados, @GBMplus
```

### Research, traders e influencers de mercado

```text
@bespokeinvest, @BreakoutStocks, @KoyfinCharts, @SoberLook,
@KobeissiLetter, @DataArbor, @MacroMicroMe, @ritholtz,
@PeterLBrandt, @elerianm, @morganhousel, @Stephanie_Link,
@jimcramer, @hmeisler, @LynAldenContact, @TheStalwart,
@PiQSuite, @allstarcharts, @CarterBWorth, @LizAnnSonders,
@SvenHenrich, @chamath
```

### Watchlist de ruido

```text
@ZeroHedge, @DeItaone, @FirstSquawk
```

Estas cuentas pueden mover narrativas, pero no se tratan como fuente confiable por default. La query amplia las excluye para reducir riesgo de ruido o desinformación.

## Archivos modificados

```text
src/financial_sentiment/live_query_catalog.py
src/financial_sentiment/live_search_service.py
src/financial_sentiment/live_relevance.py
src/financial_sentiment/streamlit_live_tab.py
src/financial_sentiment/x_api_client.py
src/financial_sentiment/medallion.py
src/financial_sentiment/jobs/live_twitter_ingest.py
app/streamlit_app.py
infra/cloudformation/01_fargate_streamlit.yml
infra/cloudformation/02_live_ingestion_athena.yml
scripts/07_deploy_ecs.sh
scripts/11_deploy_live_ingestion_athena.sh
sql/final_consultas_live_queries.sql
tests/
```

## Aplicar patch

```bash
unzip ~/Downloads/final_consultas_live_search_traders_patch.zip -d /tmp/final_traders_patch
/tmp/final_traders_patch/final_consultas_live_traders_patch/apply_final_consultas_live_extension.sh "$PWD"
```

## Validar

```bash
uv sync --all-groups
PYTHONPATH=src uv run pytest -q
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
```

## Deploy app principal

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
export BEDROCK_MODEL_ID=amazon.titan-text-lite-v1

export TASK_CPU=1024
export TASK_MEMORY=4096

./scripts/06_build_push_app.sh
./scripts/07_deploy_ecs.sh
./scripts/09_print_outputs.sh
```

## Deploy ingesta programada

```bash
./scripts/11_deploy_live_ingestion_athena.sh
```

## Validar S3

```bash
aws s3 ls "s3://$APP_BUCKET/bronze/twitter_live/" --recursive
aws s3 ls "s3://$APP_BUCKET/silver/tweets/source=twitter_live/" --recursive
aws s3 ls "s3://$APP_BUCKET/gold/sentiment_by_ticker_daily/source=twitter_live/" --recursive
aws s3 ls "s3://$APP_BUCKET/gold/twitter_live/" --recursive
```

## Athena

Ver consultas en:

```text
sql/final_consultas_live_queries.sql
```

## Costo y límite

- Cada búsqueda interactiva consulta máximo 25 tweets.
- La ingesta programada sigue usando 10 tweets cada 2 horas.
- El bearer token vive en Secrets Manager.
- Mantén el spending limit de X API menor o igual a USD 100.
- Mantén AWS Budget mensual en USD 100.
