# Guía completa: crear repo, migrar `financial_tweet_agent` y desplegar en AWS

Esta guía convierte el repositorio original `financial_tweet_agent` en un producto de datos completo en AWS llamado **Financial Sentiment Radar en AWS**.

La idea es mantener lo mejor del proyecto original —análisis de tweets financieros, sentimiento, temas, consultas y dashboard—, pero empaquetarlo como una aplicación reproducible con estructura de producción, pruebas, Docker, CloudFormation, ECS Fargate, ALB, ECR, S3 y CloudWatch.

---

## 0. Resultado esperado

Al terminar tendrás:

1. Un repositorio nuevo o una rama nueva con toda la solución.
2. Tu código original preservado como referencia en `legacy/financial_tweet_agent_original/`.
3. La versión productiva en:
   - `app/streamlit_app.py`
   - `src/financial_sentiment/`
   - `infra/cloudformation/`
   - `scripts/`
   - `docs/`
4. Una imagen Docker subida a Amazon ECR.
5. Una app Streamlit pública en ECS Fargate detrás de un Application Load Balancer.
6. Datos procesados persistidos en S3.
7. Logs en CloudWatch.
8. PDFs, draw.io y presentación listos para Canvas.

---

## 1. Prerrequisitos

### 1.1 Herramientas locales

Instala y verifica:

```bash
git --version
uv --version
python --version
docker --version
aws --version
```

Si no tienes `uv`, instálalo:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Cierra y abre la terminal después de instalarlo.

### 1.2 AWS CLI configurado

Configura credenciales de AWS. Usa un usuario IAM o IAM Identity Center, no el usuario root.

```bash
aws configure
aws sts get-caller-identity
```

Región recomendada para clase:

```bash
export AWS_REGION=us-east-1
```

### 1.3 Docker corriendo

En macOS/Windows abre Docker Desktop. En Linux inicia el daemon.

Verifica:

```bash
docker info
```

---

## 2. Crear el repositorio de entrega

Tienes dos formas seguras. Recomiendo la **opción A** porque no rompe tu repo original.

---

## Opción A — repo nuevo recomendado

### 2.1 Crear carpeta local

```bash
mkdir financial_sentiment_radar_aws
cd financial_sentiment_radar_aws
git init
```

### 2.2 Copiar esta solución AWS dentro de la carpeta

Si descargaste el ZIP entregado por ChatGPT:

```bash
# Desde la raíz vacía del repo nuevo
unzip ../financial_sentiment_radar_aws_solution_v2.zip -d /tmp/fsr_solution
rsync -av /tmp/fsr_solution/financial_sentiment_radar_aws/ ./
```

Si el ZIP se descomprime dentro de una carpeta con el mismo nombre, entra a esa carpeta y copia su contenido al repo final.

Verifica que existan estos archivos:

```bash
ls README.md Dockerfile pyproject.toml
ls app/streamlit_app.py
ls infra/cloudformation
ls docs
```

### 2.3 Copiar tu repo original como referencia, sin secretos

Clona tu repo original en una carpeta hermana:

```bash
cd ..
git clone https://github.com/hectorvil/financial_tweet_agent.git financial_tweet_agent_original
cd financial_sentiment_radar_aws
```

Crea carpeta `legacy/` y copia el original:

```bash
mkdir -p legacy/financial_tweet_agent_original
rsync -av ../financial_tweet_agent_original/ legacy/financial_tweet_agent_original/ \
  --exclude .git \
  --exclude .env \
  --exclude '*.env' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '.ipynb_checkpoints' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  --exclude '*.pem' \
  --exclude '*.key' \
  --exclude 'credentials'
```

Esto conserva tus notebooks, código anterior, README anterior y archivos de referencia, pero evita subir credenciales y ambientes virtuales.

**Importante:** si tu carpeta `data/` original tiene datos grandes, privados o no públicos, no los subas a GitHub. Súbelos a S3 o deja solo una muestra pequeña y documentada.

### 2.4 Crear repo remoto en GitHub

Con GitHub CLI:

```bash
gh repo create financial_sentiment_radar_aws --private --source=. --remote=origin
```

O desde GitHub web:

1. Entra a GitHub.
2. Crea un repositorio nuevo llamado `financial_sentiment_radar_aws`.
3. No agregues README desde GitHub, porque ya existe uno local.
4. Copia la URL del repo.
5. En terminal:

```bash
git remote add origin https://github.com/TU_USUARIO/financial_sentiment_radar_aws.git
```

---

## Opción B — transformar el repo original en una rama nueva

Usa esta opción si quieres que el repo final siga siendo `financial_tweet_agent`.

```bash
git clone https://github.com/hectorvil/financial_tweet_agent.git
cd financial_tweet_agent
git checkout -b aws-product-data-mvp
```

Copia los archivos de la solución AWS encima del repo:

```bash
# Ajusta esta ruta a donde hayas descomprimido el ZIP
rsync -av ../financial_sentiment_radar_aws/ ./ \
  --exclude .git \
  --exclude .venv \
  --exclude config/generated.env
```

Preserva tu app original en `legacy/`:

```bash
mkdir -p legacy/original_root
# Mueve los archivos originales que ya no serán la app principal.
# Ejemplo, si existen:
[ -f app.py ] && git mv app.py legacy/original_root/app.py
[ -f run_agent.ipynb ] && git mv run_agent.ipynb legacy/original_root/run_agent.ipynb
```

Después, la app principal debe ser `app/streamlit_app.py`, no `app.py`.

---

## 3. Validar que la migración quedó bien

Desde la raíz del repo final:

```bash
pwd
find . -maxdepth 2 -type d | sort
```

Debe verse algo así:

```text
.
./app
./config
./data
./docs
./infra
./infra/cloudformation
./scripts
./src
./src/financial_sentiment
./tests
```

Si usaste la opción A y preservaste tu repo original:

```bash
ls legacy/financial_tweet_agent_original
```

---

## 4. Validación local completa antes de GitHub

### 4.1 Sincronizar ambiente

```bash
uv sync --all-groups
```

### 4.2 Ejecutar pruebas

```bash
PYTHONPATH=src uv run pytest -q
```

Resultado esperado:

```text
9 passed
```

### 4.3 Ejecutar lint

```bash
uv run ruff check .
```

Si ruff encuentra errores auto-corregibles:

```bash
uv run ruff check --fix .
uv run ruff format .
```

Vuelve a correr pruebas:

```bash
PYTHONPATH=src uv run pytest -q
```

### 4.4 Smoke test local de Streamlit

```bash
./scripts/04_local_smoke_test.sh
```

Resultado esperado:

```text
OK: Streamlit responde en http://localhost:8501
```

### 4.5 Docker build local

```bash
docker build -t financial-sentiment-radar:local .
```

Ejecutar contenedor local:

```bash
docker run --rm -p 8501:8501 \
  -e DATA_BACKEND=local \
  -e AWS_REGION=us-east-1 \
  financial-sentiment-radar:local
```

Abre:

```text
http://localhost:8501
```

---

## 5. Preflight automático recomendado

Este script revisa herramientas, estructura, secretos, tests, lint, CloudFormation y Docker.

```bash
./scripts/02_preflight_local.sh
```

Si todavía no tienes AWS configurado, puedes correr:

```bash
SKIP_AWS=true ./scripts/02_preflight_local.sh
```

Si Docker no está corriendo:

```bash
SKIP_DOCKER=true ./scripts/02_preflight_local.sh
```

No sigas al despliegue si el preflight falla.

---

## 6. Primer commit y push

Revisa qué se va a subir:

```bash
git status
```

Verifica que NO aparezcan:

```text
.env
*.pem
*.key
.aws/
.venv/
venv/
config/generated.env
```

Agrega archivos por grupos:

```bash
git add README.md pyproject.toml requirements.txt Dockerfile docker-compose.yml Makefile .gitignore .dockerignore .python-version .pre-commit-config.yaml
git add app src tests infra scripts docs data/sample_tweets.csv .github
```

Si copiaste el repo original como referencia:

```bash
git add legacy/financial_tweet_agent_original
```

Commit:

```bash
git commit -m "Convert financial tweet agent into AWS data product"
```

Push:

```bash
git branch -M main
git push -u origin main
```

Confirma en GitHub que el repo contiene la estructura esperada y que el instructor tendrá acceso.

---

## 7. Despliegue en AWS

### 7.1 Variables base

```bash
export PROJECT_NAME=financial-sentiment-radar
export ENVIRONMENT=dev
export AWS_REGION=us-east-1
```

### 7.2 Validar CloudFormation

```bash
./scripts/03_validate_cloudformation.sh
```

### 7.3 Desplegar foundation: S3 + ECR

```bash
./scripts/00_deploy_foundation.sh
```

El script crea `config/generated.env`.

Verifica:

```bash
cat config/generated.env
```

Debe contener:

```text
DATA_BUCKET=...
ECR_REPOSITORY_URI=...
IMAGE_URI=...
```

### 7.4 Build y push de imagen a ECR

```bash
source config/generated.env
./scripts/06_build_push_app.sh
```

### 7.5 Opcional: Twitter/X live search

Crea el secreto solo si tienes bearer token:

```bash
aws secretsmanager create-secret \
  --region "$AWS_REGION" \
  --name financial-sentiment-radar/twitter-bearer \
  --secret-string "TU_BEARER_TOKEN"
```

Obtén el ARN:

```bash
aws secretsmanager describe-secret \
  --region "$AWS_REGION" \
  --secret-id financial-sentiment-radar/twitter-bearer \
  --query ARN \
  --output text
```

Exporta:

```bash
export TWITTER_BEARER_SECRET_ARN="ARN_QUE_TE_REGRESO_AWS"
```

Si no tienes bearer token, no hagas este paso. La app seguirá funcionando con carga de archivos y dataset demo.

### 7.6 Opcional: Bedrock

Si tienes acceso a Bedrock:

```bash
export USE_BEDROCK=true
export BEDROCK_MODEL_ID=amazon.titan-text-lite-v1
```

Si no tienes Bedrock:

```bash
export USE_BEDROCK=false
```

La app usará respuesta extractiva local.

### 7.7 Desplegar ECS Fargate + ALB

```bash
source config/generated.env
./scripts/07_deploy_ecs.sh
```

### 7.8 Obtener URL pública

```bash
./scripts/09_print_outputs.sh
```

Busca `AppURL`. Debe verse así:

```text
http://financial-sentiment-radar-dev-alb-xxxxx.us-east-1.elb.amazonaws.com
```

### 7.9 Smoke test cloud

```bash
./scripts/08_smoke_test_cloud.sh
```

Debe responder el healthcheck de Streamlit.

---

## 8. Qué hacer si algo falla

### 8.1 CloudFormation falla

Ver eventos:

```bash
aws cloudformation describe-stack-events \
  --region "$AWS_REGION" \
  --stack-name "${PROJECT_NAME}-${ENVIRONMENT}-ecs" \
  --max-items 20 \
  --output table
```

Problemas comunes:

| Error | Causa probable | Solución |
|---|---|---|
| `CAPABILITY_NAMED_IAM` | CloudFormation crea roles IAM | Usa los scripts, ya incluyen `--capabilities CAPABILITY_NAMED_IAM` |
| `Bucket name already exists` | Nombre S3 no es globalmente único | No definas `DATA_BUCKET_NAME` o usa uno único |
| `AccessDenied` | Usuario AWS sin permisos | Revisa permisos de IAM/Identity Center |
| `Model access denied` | Bedrock no habilitado | Usa `USE_BEDROCK=false` o habilita modelo en Bedrock |

### 8.2 ECS no levanta

Ejecuta:

```bash
./scripts/10_troubleshoot_ecs.sh
```

Esto muestra:

- eventos recientes del servicio ECS,
- tareas corriendo o detenidas,
- razones de stop,
- últimos logs de CloudWatch.

### 8.3 ALB abre pero la app no responde

Revisa logs:

```bash
aws logs describe-log-groups --region "$AWS_REGION" --log-group-name-prefix /ecs/financial-sentiment-radar
```

Luego usa el script:

```bash
./scripts/10_troubleshoot_ecs.sh
```

### 8.4 Docker push falla

Vuelve a autenticar ECR:

```bash
source config/generated.env
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

Después:

```bash
./scripts/06_build_push_app.sh
```

### 8.5 Streamlit falla localmente

Prueba imports:

```bash
PYTHONPATH=src uv run python - <<'PY'
from financial_sentiment.pipeline import process_tweets
import pandas as pd
raw = pd.DataFrame({'text': ['NVIDIA $NVDA has strong demand']})
print(process_tweets(raw).head())
PY
```

Si eso funciona, prueba:

```bash
./scripts/04_local_smoke_test.sh
```

---

## 9. Apagar la app para ahorrar

Cuando no la estés usando:

```bash
source config/generated.env
aws ecs update-service \
  --region "$AWS_REGION" \
  --cluster "${PROJECT_NAME}-${ENVIRONMENT}-cluster" \
  --service "${PROJECT_NAME}-${ENVIRONMENT}-service" \
  --desired-count 0
```

Encenderla otra vez:

```bash
aws ecs update-service \
  --region "$AWS_REGION" \
  --cluster "${PROJECT_NAME}-${ENVIRONMENT}-cluster" \
  --service "${PROJECT_NAME}-${ENVIRONMENT}-service" \
  --desired-count 1
```

---

## 10. Borrar todo al terminar

```bash
source config/generated.env
./scripts/99_destroy.sh
```

Esto borra:

1. Stack ECS.
2. Objetos del bucket S3.
3. Stack foundation.

Revisa en AWS Console que no queden recursos activos.

---

## 11. Checklist final para Canvas

Antes de subir:

```bash
PYTHONPATH=src uv run pytest -q
./scripts/08_smoke_test_cloud.sh
./scripts/09_print_outputs.sh
```

Sube a Canvas:

1. `docs/product_definition.pdf`
2. `docs/product_faq.pdf`
3. `docs/architecture_solution.pdf`
4. `docs/architecture_financial_sentiment_radar.drawio`
5. `docs/presentacion_ejecutiva_15min.pptx`
6. URL pública `AppURL`.
7. URL de GitHub.
8. Ruta del repo y rama, por ejemplo:

```text
Repositorio: https://github.com/TU_USUARIO/financial_sentiment_radar_aws
Rama: main
App Streamlit: http://...
```

---

## 12. Orden de ejecución recomendado

Ejecuta exactamente en este orden:

```bash
# Local
uv sync --all-groups
PYTHONPATH=src uv run pytest -q
uv run ruff check .
./scripts/04_local_smoke_test.sh
docker build -t financial-sentiment-radar:local .

# GitHub
git status
git add README.md pyproject.toml requirements.txt Dockerfile docker-compose.yml Makefile .gitignore .dockerignore .python-version .pre-commit-config.yaml
git add app src tests infra scripts docs data/sample_tweets.csv .github
git commit -m "Convert financial tweet agent into AWS data product"
git push -u origin main

# AWS
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

---

## 13. Qué cambió respecto al repo original

| Componente original | Transformación en producto AWS |
|---|---|
| `app.py` Streamlit simple | `app/streamlit_app.py` con UI modular, S3, Bedrock opcional y consultas |
| Notebook/Colab | Scripts reproducibles, Docker y CloudFormation |
| `.env` local | Variables de entorno, Secrets Manager opcional y roles IAM |
| Datos locales | S3 como data lake: `raw/`, `processed/`, `outputs/` |
| Modelo/RAG pesado | MVP ligero con TF-IDF local + Bedrock opcional para mantener costo bajo |
| Ejecución local | ECS Fargate + ALB público |
| Sin pruebas formales | `tests/`, `ruff`, GitHub Actions y preflight |

---

## 14. Reglas de seguridad

No subas nunca:

```text
.env
OPENAI_API_KEY
TWITTER_BEARER
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
*.pem
*.key
.aws/
config/generated.env
```

Guarda secretos en:

- AWS Secrets Manager, o
- variables de entorno locales no versionadas.

---

## 15. Ruta de presentación ejecutiva

Para la demo de 15 minutos:

1. Problema: monitoreo manual de percepción financiera es lento y poco trazable.
2. Usuario: analista financiero/riesgo reputacional/relación con inversionistas.
3. Arquitectura: usuario → ALB → ECS Fargate Streamlit → S3/Bedrock/Twitter/CloudWatch.
4. Datos: tweets/textos financieros con columna `text`.
5. Demo:
   - abrir AppURL,
   - mostrar KPIs,
   - subir CSV,
   - preguntar “¿Qué se dice de NVIDIA?”,
   - mostrar evidencia,
   - mostrar persistencia S3/logs CloudWatch.
