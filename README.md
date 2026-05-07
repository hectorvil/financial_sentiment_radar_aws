# Financial Sentiment Radar en AWS

Producto de datos para monitorear sentimiento financiero en textos de social media, consultar evidencia sobre compañías específicas y convertir un prototipo tipo `financial_tweet_agent` en una aplicación desplegable con AWS.

La solución está diseñada para una entrega de clase: es acotada, reproducible, documentada y desplegable con CloudFormation + Amazon ECR + Amazon ECS Fargate + Application Load Balancer + Amazon S3 + CloudWatch Logs. La app se consume en Streamlit.


## 0. Guía rápida: crear repo, migrar y desplegar

La guía completa está en [`docs/GUIA_MIGRACION_DESPLIEGUE.md`](docs/GUIA_MIGRACION_DESPLIEGUE.md). Esta sección resume el camino recomendado desde cero.

### 0.1 Crear repo nuevo recomendado

```bash
mkdir financial_sentiment_radar_aws
cd financial_sentiment_radar_aws
git init
```

Copia aquí los archivos de esta solución. Si descargaste el ZIP:

```bash
# Ejecuta desde la raíz vacía del repo nuevo
unzip ../financial_sentiment_radar_aws_solution_v2.zip -d /tmp/fsr_solution
rsync -av /tmp/fsr_solution/financial_sentiment_radar_aws/ ./
```

### 0.2 Pasar tu repo original sin romperlo

```bash
cd ..
git clone https://github.com/hectorvil/financial_tweet_agent.git financial_tweet_agent_original
cd financial_sentiment_radar_aws
mkdir -p legacy/financial_tweet_agent_original
rsync -av ../financial_tweet_agent_original/ legacy/financial_tweet_agent_original/ \
  --exclude .git \
  --exclude .env \
  --exclude '*.env' \
  --exclude .venv \
  --exclude venv \
  --exclude __pycache__ \
  --exclude .ipynb_checkpoints \
  --exclude '*.pem' \
  --exclude '*.key' \
  --exclude credentials
```

Esto preserva tu proyecto anterior como evidencia, pero la aplicación evaluable queda en `app/streamlit_app.py` y el código productivo en `src/financial_sentiment/`. No copies credenciales, ambientes virtuales ni datos privados a GitHub.

### 0.3 Validar localmente antes de subir a GitHub

```bash
uv sync --all-groups
PYTHONPATH=src uv run pytest -q
uv run ruff check .
./scripts/04_local_smoke_test.sh
docker build -t financial-sentiment-radar:local .
```

También puedes ejecutar todo el preflight:

```bash
./scripts/02_preflight_local.sh
```

Si todavía no tienes AWS configurado:

```bash
SKIP_AWS=true ./scripts/02_preflight_local.sh
```

### 0.4 Primer commit y push

```bash
git status
git add README.md pyproject.toml requirements.txt Dockerfile docker-compose.yml Makefile .gitignore .dockerignore .python-version .pre-commit-config.yaml
git add app src tests infra scripts docs data/sample_tweets.csv .github
# Solo si copiaste el repo original como referencia:
git add legacy/financial_tweet_agent_original
git commit -m "Convert financial tweet agent into AWS data product"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/financial_sentiment_radar_aws.git
git push -u origin main
```

### 0.5 Desplegar en AWS

```bash
export PROJECT_NAME=financial-sentiment-radar
export ENVIRONMENT=dev
export AWS_REGION=us-east-1

./scripts/03_validate_cloudformation.sh
./scripts/00_deploy_foundation.sh
source config/generated.env
./scripts/06_build_push_app.sh
./scripts/07_deploy_ecs.sh
./scripts/09_print_outputs.sh
./scripts/08_smoke_test_cloud.sh
```

El output `AppURL` es la URL pública que debes entregar en Canvas.

---

## 1. Qué problema resuelve

Analistas financieros, equipos de relación con inversionistas o áreas de riesgo reputacional necesitan entender rápidamente qué se está diciendo sobre empresas como NVIDIA, Tesla, Apple, BBVA o Microsoft. Revisar social media manualmente es lento, poco trazable y difícil de convertir en una señal de negocio.

Este producto permite:

- Cargar o adquirir textos financieros desde CSV/Parquet o Twitter/X recent search.
- Preprocesar textos y extraer tickers/compañías.
- Clasificar sentimiento (`positive`, `neutral`, `negative`) con un modelo ligero e interpretable.
- Clasificar tema de negocio (`earnings`, `macro_rates`, `ai_chips`, etc.).
- Consultar el corpus con preguntas en lenguaje natural.
- Opcionalmente resumir la evidencia con Amazon Bedrock.
- Persistir datos procesados y outputs en Amazon S3.
- Exponer la app en AWS con ECS Fargate y ALB.

---

## 2. Arquitectura

```text
Usuario / Instructor
       |
       v
Application Load Balancer (HTTP :80)
       |
       v
Amazon ECS Fargate - Streamlit app (:8501)
       |
       +--> Amazon S3: raw/, processed/, outputs/
       +--> Amazon Bedrock: resumen opcional de consultas
       +--> Twitter/X API: adquisición live opcional
       +--> CloudWatch Logs: trazabilidad de ejecución
       |
       v
Amazon ECR: imagen Docker de la app
```

La arquitectura usa subnets públicas y `AssignPublicIp=ENABLED` para evitar NAT Gateway y mantener costos bajos. Para una prueba de concepto de clase esto reduce complejidad y costo. En producción real se moverían las tareas a subnets privadas con VPC endpoints para S3/Bedrock.

Diagrama editable en draw.io: [`docs/architecture_financial_sentiment_radar.drawio`](docs/architecture_financial_sentiment_radar.drawio).

---

## 3. Estructura del repositorio

```text
.
├── README.md
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── app/
│   └── streamlit_app.py              # UI Streamlit
├── src/financial_sentiment/
│   ├── preprocessing.py              # limpieza, extracción de tickers
│   ├── sentiment.py                  # scoring de sentimiento financiero
│   ├── topics.py                     # clasificación temática ligera
│   ├── pipeline.py                   # pipeline end-to-end
│   ├── retrieval.py                  # búsqueda TF-IDF para consultas
│   ├── bedrock.py                    # resumen opcional con Amazon Bedrock
│   ├── storage.py                    # LocalStorage y S3Storage
│   ├── twitter_live.py               # Twitter/X recent search opcional
│   └── charts.py                     # visualizaciones Plotly
├── infra/cloudformation/
│   ├── 00_foundation.yml             # S3 + ECR
│   └── 01_fargate_streamlit.yml      # VPC + ALB + ECS Fargate + IAM + Logs
├── scripts/
│   ├── 00_deploy_foundation.sh
│   ├── 01_write_generated_env.sh
│   ├── 02_preflight_local.sh          # validación integral antes de deploy
│   ├── 03_validate_cloudformation.sh  # validación de templates AWS
│   ├── 04_local_smoke_test.sh         # healthcheck local Streamlit
│   ├── 06_build_push_app.sh
│   ├── 07_deploy_ecs.sh
│   ├── 08_smoke_test_cloud.sh
│   ├── 09_print_outputs.sh
│   ├── 10_troubleshoot_ecs.sh         # diagnóstico ECS/CloudWatch
│   ├── 20_process_sample_to_s3.py
│   └── 99_destroy.sh
├── data/
│   └── sample_tweets.csv             # dataset de demo permitido para repo
├── tests/
│   └── test_*.py                     # pruebas unitarias
└── docs/
    ├── product_definition.md / .pdf
    ├── product_faq.md / .pdf
    ├── architecture_solution.md / .pdf
    ├── architecture_financial_sentiment_radar.drawio
    └── presentacion_ejecutiva_15min.pptx
```

---

## 4. Requisitos

### Local

- Python 3.12
- `uv`
- Docker
- AWS CLI v2 configurado
- Cuenta AWS con permisos para CloudFormation, S3, ECR, ECS, EC2, IAM, ELB, Logs y opcional Bedrock

### Opcional

- Acceso habilitado a Amazon Bedrock para el modelo `amazon.titan-text-lite-v1` o un modelo Claude.
- Twitter/X bearer token si se quiere probar adquisición live.

---

## 5. Ejecución local

```bash
# 1. Clonar tu repo o copiar estos archivos al repo final
git clone <URL_DE_TU_REPO>
cd financial_sentiment_radar_aws

# 2. Instalar dependencias
uv sync

# 3. Ejecutar pruebas
PYTHONPATH=src uv run pytest -q

# 4. Correr app local
PYTHONPATH=src uv run streamlit run app/streamlit_app.py
```

Abre la URL que imprime Streamlit, normalmente `http://localhost:8501`.

La app cargará automáticamente `data/sample_tweets.csv` si no hay S3 configurado.

---

## 6. Ejecución local con Docker

```bash
docker build -t financial-sentiment-radar:local .
docker run --rm -p 8501:8501 \
  -e DATA_BACKEND=local \
  -e AWS_REGION=us-east-1 \
  financial-sentiment-radar:local
```

Luego abre `http://localhost:8501`.

---

## 7. Despliegue en AWS paso a paso

> Región recomendada para clase: `us-east-1`.

### 7.1 Configurar AWS CLI

```bash
aws configure
aws sts get-caller-identity
```

Asegúrate de trabajar con un usuario IAM/Identity Center y no con el usuario root.

### 7.2 Desplegar recursos base: S3 + ECR

```bash
export PROJECT_NAME=financial-sentiment-radar
export ENVIRONMENT=dev
export AWS_REGION=us-east-1

./scripts/00_deploy_foundation.sh
```

Esto crea:

- Un bucket S3 cifrado, con versionado y bloqueo de acceso público.
- Un repositorio ECR para la imagen Docker.
- `config/generated.env` con outputs del stack.

Revisa:

```bash
cat config/generated.env
```

### 7.3 Construir y subir imagen Docker a ECR

```bash
source config/generated.env
./scripts/06_build_push_app.sh
```

### 7.4 Opcional: crear secreto para Twitter/X

Si quieres habilitar la pestaña de búsqueda live en X/Twitter:

```bash
aws secretsmanager create-secret \
  --region "$AWS_REGION" \
  --name financial-sentiment-radar/twitter-bearer \
  --secret-string "TU_BEARER_TOKEN"

export TWITTER_BEARER_SECRET_ARN="arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:financial-sentiment-radar/twitter-bearer-xxxx"
```

Si no quieres live search, no hagas este paso.

### 7.5 Opcional: habilitar Bedrock

Para usar Amazon Bedrock en la pestaña de consultas:

1. En la consola de AWS, abre Amazon Bedrock.
2. En `Model access`, solicita/habilita el modelo que usarás.
3. Exporta variables:

```bash
export USE_BEDROCK=true
export BEDROCK_MODEL_ID=amazon.titan-text-lite-v1
```

Si no quieres usar Bedrock, deja `USE_BEDROCK=false`. La app seguirá respondiendo con un resumen extractivo local.

### 7.6 Desplegar ECS Fargate + ALB

```bash
source config/generated.env
./scripts/07_deploy_ecs.sh
```

Esto crea:

- VPC y dos subnets públicas.
- Application Load Balancer.
- ECS Cluster.
- ECS Service con una task Fargate.
- IAM Task Role con permisos a S3 y Bedrock.
- CloudWatch Log Group con retención de 14 días.

### 7.7 Obtener URL pública

```bash
./scripts/09_print_outputs.sh
```

Busca el output `AppURL`, por ejemplo:

```text
http://financial-sentiment-radar-dev-alb-xxxxx.us-east-1.elb.amazonaws.com
```

Esa es la URL que debes entregar para que el instructor pueda usar la app.

### 7.8 Smoke test

```bash
./scripts/08_smoke_test_cloud.sh
```

Debe responder el endpoint de salud de Streamlit.

---

## 8. Cómo usa la app el usuario final

1. Entra a la URL pública del ALB.
2. Revisa el tab **Resumen** para ver KPIs, ranking de tickers y tendencia.
3. En **Consultas**, escribe una pregunta como:
   - `¿Qué se dice de NVIDIA?`
   - `¿Qué riesgos aparecen para Tesla?`
   - `¿Hay tono negativo sobre BBVA?`
4. La app recupera textos relevantes y genera una respuesta con evidencia.
5. En **Temas/Riesgo**, identifica temas con mayor concentración negativa.
6. En **Datos procesados**, revisa y descarga el dataset enriquecido.
7. Si tiene permisos/API token, usa la barra lateral para buscar tweets recientes.

---

## 9. Inputs y outputs

### Inputs

- CSV/Parquet con columna obligatoria `text`.
- Columnas opcionales: `tweet_id`, `created_at`, `author`, `source`.
- Twitter/X recent search opcional.
- Dataset de demo: `data/sample_tweets.csv`.

### Outputs

- Dataset procesado en S3:

```text
s3://<bucket>/processed/tweets/financial_sentiment_latest.parquet
```

- Copias por carga/evento:

```text
s3://<bucket>/raw/tweets/<tipo>_<timestamp>.parquet
```

- Descarga CSV desde la app.
- Respuesta de consulta con evidencia recuperada.
- Logs de ejecución en CloudWatch:

```text
/ecs/financial-sentiment-radar-dev
```

---

## 10. Pruebas y calidad de código

```bash
PYTHONPATH=src uv run pytest -q
uv run ruff check .
uv run ruff format .
```

Los tests cubren:

- Limpieza de texto.
- Extracción de tickers.
- Sentimiento positivo/negativo.
- Pipeline end-to-end.
- Recuperación de evidencia para consultas.
- Manejo robusto de búsquedas sin vocabulario útil.

---

## 11. Estimación de costo anual

Escenario base para la entrega:

- 1 task Fargate siempre encendida.
- 0.5 vCPU / 1 GB RAM.
- 1 ALB público.
- 10 GB en S3.
- 2 GB en ECR.
- 1 GB/mes de logs.
- Bedrock opcional con bajo volumen de consultas.

Estimación aproximada en `us-east-1`:

| Servicio | Supuesto | Costo anual aprox. |
|---|---:|---:|
| ECS Fargate | 0.5 vCPU + 1 GB, 24/7 | USD 216 |
| ALB | cargo fijo + ~1 LCU | USD 267 |
| S3 | 10 GB Standard | USD 3 |
| ECR | 2 GB imagen privada | USD 2 |
| CloudWatch Logs | ~1 GB/mes, retención 14 días | USD 6 |
| Bedrock | opcional, consultas bajas | USD 0-20 |
| **Total base** | sin NAT Gateway, sin RDS | **USD 488-508/año** |

Para bajar costo durante la clase, puedes apagar el servicio ECS cuando no se use:

```bash
source config/generated.env
aws ecs update-service \
  --region "$AWS_REGION" \
  --cluster "${PROJECT_NAME}-${ENVIRONMENT}-cluster" \
  --service "${PROJECT_NAME}-${ENVIRONMENT}-service" \
  --desired-count 0
```

Y volverlo a prender:

```bash
aws ecs update-service \
  --region "$AWS_REGION" \
  --cluster "${PROJECT_NAME}-${ENVIRONMENT}-cluster" \
  --service "${PROJECT_NAME}-${ENVIRONMENT}-service" \
  --desired-count 1
```

---

## 12. Borrar recursos

Para evitar cargos cuando termine la evaluación:

```bash
source config/generated.env
./scripts/99_destroy.sh
```

Esto elimina el stack ECS, vacía el bucket y elimina el stack foundation.

---

## 13. Qué subir a Canvas

Sube:

1. `docs/product_definition.pdf`
2. `docs/product_faq.pdf`
3. `docs/architecture_solution.pdf`
4. `docs/architecture_financial_sentiment_radar.drawio`
5. `docs/presentacion_ejecutiva_15min.pptx`
6. URL pública de Streamlit (`AppURL` del stack ECS).
7. URL del repositorio GitHub con acceso para el instructor.
8. Capturas de AWS si el instructor las pide: ECS, ECR, S3, CloudFormation, CloudWatch y ALB.

---

## 14. Limitaciones y siguientes pasos

Este MVP no es recomendación financiera. Es un radar de percepción basado en textos. Para producción real:

- Reemplazar el scorer ligero por FinBERT desplegado en SageMaker, Bedrock classification prompt o Comprehend Custom Classification.
- Agregar autenticación con Cognito o IAM Identity Center.
- Mover Fargate a subnets privadas y usar VPC endpoints.
- Agregar scheduled ingestion con EventBridge + Lambda/ECS RunTask.
- Agregar monitoreo de drift, calidad de datos y evaluación contra eventos de mercado.
- Separar almacenamiento operacional en DynamoDB o RDS si hay feedback de usuarios.

---

## 15. Ruta de evaluación para el instructor

- App pública: pegar aquí el `AppURL` generado por CloudFormation.
- Repositorio: pegar aquí la URL de GitHub y confirmar acceso.
- Comando de verificación cloud:

```bash
./scripts/08_smoke_test_cloud.sh
```
