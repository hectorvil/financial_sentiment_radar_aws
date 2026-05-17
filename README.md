# Financial Sentiment Radar AWS

## 1. Descripción general

**Financial Sentiment Radar AWS** es un producto de datos construido en AWS para analizar sentimiento financiero a partir de textos tipo tweet, publicaciones financieras o archivos tabulares cargados por el usuario.

El objetivo del proyecto es transformar una aplicación de análisis de sentimiento financiero en un producto de datos desplegable, reproducible y consultable desde una interfaz web en **Streamlit**, usando servicios de AWS como **ECS Fargate, ECR, S3, CloudWatch, IAM, Application Load Balancer y CloudFormation**.

El producto permite:

- Cargar archivos `.csv` o `.parquet` con tweets o textos financieros.
- Detectar automáticamente cuál columna contiene el texto a analizar.
- Clasificar sentimiento financiero por texto.
- Identificar empresas o tickers mencionados.
- Agregar métricas por sentimiento, empresa y tema.
- Consultar en lenguaje natural qué ocurre con una empresa.
- Guardar datos crudos, procesados y outputs en S3.
- Desplegar la app en AWS mediante contenedores Docker.

---

## 2. Problema que resuelve

En finanzas, redes sociales y noticias generan señales útiles sobre percepción de mercado, riesgos, eventos corporativos y expectativas de inversionistas. Sin embargo, estos textos suelen venir en formatos no estructurados, con columnas distintas, ruido, diferentes idiomas y alto volumen.

Este producto busca responder preguntas como:

- ¿Qué sentimiento domina sobre Tesla, Google, Nvidia o BBVA?
- ¿El tono reciente es positivo, neutral o negativo?
- ¿Qué temas explican el sentimiento?
- ¿Qué tweets o publicaciones sirven como evidencia?
- ¿Cómo puedo analizar archivos nuevos aunque no tengan el mismo esquema de columnas?

La solución no se limita a graficar datos crudos. Enriquecemos los textos con capas analíticas: inferencia de esquema, clasificación de sentimiento, detección de empresas, temas y recuperación de evidencia para consultas.

---

## 3. Usuario final

El usuario final puede ser:

- Un analista financiero.
- Un equipo de riesgos de mercado.
- Un equipo de estrategia o research.
- Un área de comunicación corporativa.
- Un inversionista que quiere monitorear percepción pública.
- Un equipo académico que busca demostrar un producto de datos en AWS.

La experiencia esperada es que el usuario entre a una aplicación web, cargue un archivo o use datos de ejemplo, obtenga métricas de sentimiento y pueda preguntar en lenguaje natural qué está ocurriendo con una empresa.

---

## 4. Arquitectura general

La arquitectura combina una aplicación Streamlit con infraestructura administrada en AWS.

```text
Usuario
  ↓
Application Load Balancer
  ↓
ECS Fargate
  ↓
Contenedor Docker con Streamlit + Python
  ↓
Pipeline analítico
  ├── Inferencia de esquema
  ├── Clasificación de sentimiento
  ├── Detección de tickers
  ├── Clasificación temática
  └── Consulta con evidencia
  ↓
S3
  ├── raw/
  ├── schema-mappings/
  ├── processed/
  └── outputs/
  ↓
CloudWatch Logs
```

---

## 5. Componentes principales de AWS

### 5.1 Amazon ECR

Amazon ECR funciona como repositorio privado de imágenes Docker. La app se empaqueta como imagen Docker y se sube a ECR.

Flujo:

```text
Dockerfile
  ↓
docker buildx build --platform linux/amd64
  ↓
Amazon ECR
  ↓
ECS Fargate descarga la imagen
```

El script principal es:

```bash
./scripts/06_build_push_app.sh
```

Este script construye la imagen en arquitectura `linux/amd64`, necesaria para que ECS Fargate pueda ejecutarla correctamente.

---

### 5.2 ECS Fargate

ECS Fargate ejecuta la app Streamlit como un contenedor administrado. No se administra una instancia EC2 manualmente.

ECS usa una task definition que indica:

- Imagen Docker en ECR.
- CPU y memoria asignada.
- Variables de entorno.
- Puerto del contenedor.
- Roles IAM.
- Configuración de logs.

La app escucha en el puerto:

```text
8501
```

---

### 5.3 Application Load Balancer

El Application Load Balancer expone la app al usuario final mediante una URL pública.

Flujo:

```text
Usuario → ALB → Target Group → ECS Fargate task → Streamlit
```

El ALB recibe tráfico HTTP y lo redirige a la task de Fargate.

---

### 5.4 Target Group

El Target Group conecta el ALB con la task de ECS y ejecuta health checks para verificar que la app esté viva.

El estado esperado es:

```text
healthy
```

---

### 5.5 Amazon S3

S3 es la capa de almacenamiento del producto de datos.

Se usa para guardar:

```text
raw/              archivos originales cargados por el usuario
schema-mappings/ resultados de inferencia de columnas
processed/        datasets enriquecidos con sentimiento y metadata
outputs/          descargas, resultados o artefactos generados
```

---

### 5.6 CloudWatch Logs

CloudWatch centraliza los logs de la aplicación y de las tasks de ECS.

Sirve para depurar:

- Errores de Python.
- Problemas de permisos.
- Fallas en lectura/escritura a S3.
- Fallas al invocar Bedrock.
- Problemas de carga del modelo.
- Errores de arranque del contenedor.

Comando útil:

```bash
aws logs tail "/ecs/financial-sentiment-radar-dev" \
  --region us-east-1 \
  --since 30m
```

---

### 5.7 IAM Roles

La aplicación no debe guardar credenciales en el código. ECS usa roles IAM para acceder a servicios de AWS.

Permisos principales:

- Leer/escribir en S3.
- Enviar logs a CloudWatch.
- Descargar imagen desde ECR.
- Invocar modelos de Bedrock si está habilitado.

---

### 5.8 CloudFormation

Toda la infraestructura se crea mediante CloudFormation.

Plantillas principales:

```text
infra/cloudformation/00_foundation.yml
infra/cloudformation/01_fargate_streamlit.yml
```

La primera crea recursos base como S3 y ECR.

La segunda crea:

- VPC.
- Subnets.
- Security Groups.
- ALB.
- Target Group.
- ECS Cluster.
- ECS Service.
- Task Definition.
- IAM Roles.
- CloudWatch Logs.

---

## 6. Pipeline analítico

El pipeline del producto tiene varias capas.

```text
Archivo CSV/Parquet
  ↓
Lectura de datos
  ↓
Inferencia de columna de texto
  ↓
Estandarización del esquema
  ↓
Preprocesamiento
  ↓
Clasificación de sentimiento
  ↓
Detección de tickers
  ↓
Clasificación temática
  ↓
Persistencia y visualización
```

---

## 7. Inferencia de esquema

Una mejora importante del proyecto es que ya no asumimos que todos los archivos tienen una columna llamada `text`.

El usuario puede subir archivos con columnas como:

```text
text
tweet
full_text
content
body
message
post
sentence
texto
comentario
```

El módulo:

```text
src/financial_sentiment/schema_inference.py
```

detecta cuál columna parece contener el texto principal.

Primero usa reglas determinísticas. Evalúa:

- Nombre de la columna.
- Tipo de dato.
- Longitud promedio del texto.
- Presencia de lenguaje natural.
- Presencia de cashtags como `$TSLA`.
- Presencia de hashtags.
- Presencia de menciones.
- Presencia de URLs.
- Términos financieros.

También penaliza columnas que parecen:

- IDs.
- Fechas.
- Usuarios.
- Etiquetas.
- Scores.
- Valores numéricos.

Si hay ambigüedad y Bedrock está activado, se manda a Bedrock un resumen pequeño del esquema y algunas muestras.

---

## 8. Uso de Bedrock

Bedrock se usa en dos lugares.

### 8.1 Bedrock para inferencia de esquema

Cuando el archivo tiene columnas ambiguas, Bedrock puede ayudar a decidir cuál contiene el texto principal.

Ejemplo de salida esperada:

```json
{
  "tweet_text_column": "content",
  "confidence": 0.91,
  "reason": "La columna contiene publicaciones completas con lenguaje natural y términos financieros.",
  "label_column": "label",
  "timestamp_column": "created_at",
  "ticker_column": null
}
```

Bedrock no recibe todo el dataset. Solo recibe:

- Nombres de columnas.
- Tipos de datos.
- Algunas muestras pequeñas.

Esto reduce costo y evita enviar datos innecesarios.

---

### 8.2 Bedrock para consultas del usuario

Cuando el usuario pregunta:

```text
¿Qué pasa con Tesla?
¿Qué ocurre con Google?
¿Qué riesgos aparecen para Nvidia?
```

La app recupera evidencia del corpus procesado y se la pasa a Bedrock para generar una respuesta ejecutiva.

Bedrock debe responder únicamente con base en la evidencia proporcionada. No debe inventar información ni dar recomendaciones de compra o venta.

---

## 9. Modelos de sentimiento

El producto soporta dos modos de clasificación.

### 9.1 Modelo léxico financiero

Es el modo default.

```bash
SENTIMENT_MODEL=lexicon
```

Ventajas:

- Rápido.
- Barato.
- Interpretable.
- No requiere descargar modelos pesados.
- Funciona bien para MVP y demos.

Desventajas:

- Menor capacidad para entender contexto.
- Puede confundirse con frases ambiguas o matices financieros.

---

### 9.2 FinBERT

FinBERT es un modelo transformer especializado en lenguaje financiero.

```bash
SENTIMENT_MODEL=finbert
```

El módulo principal es:

```text
src/financial_sentiment/finbert.py
```

FinBERT clasifica cada texto en:

```text
positive
neutral
negative
```

y genera probabilidades:

```text
positive_prob
neutral_prob
negative_prob
sentiment_confidence
```

Ventajas:

- Mejor comprensión de lenguaje financiero.
- Mejor manejo de contexto.
- Mejor interpretación de frases como earnings, guidance, downgrade, margins, delivery numbers, etc.

Desventajas:

- Mayor consumo de memoria.
- Mayor tamaño de imagen Docker.
- Mayor tiempo de arranque.
- Mayor costo en Fargate.

Para usar FinBERT en ECS se recomienda:

```bash
TASK_CPU=1024
TASK_MEMORY=4096
```

---

## 10. Diferencia entre FinBERT y Bedrock

FinBERT y Bedrock no cumplen la misma función.

| Componente | Función |
|---|---|
| FinBERT | Clasifica sentimiento tweet por tweet |
| Bedrock | Identifica columnas ambiguas y genera respuestas en lenguaje natural |
| Streamlit | Permite cargar archivos, visualizar resultados y consultar |
| S3 | Guarda raw, processed, schema mappings y outputs |

Arquitectura ideal:

```text
Tweets
  ↓
FinBERT clasifica sentimiento
  ↓
Pandas agrega métricas
  ↓
Retriever recupera evidencia
  ↓
Bedrock explica resultados al usuario
```

---

## 11. Estructura del repositorio

```text
financial_sentiment_radar_aws/
├── app/
│   └── streamlit_app.py
├── data/
│   └── sample_tweets.csv
├── docs/
│   └── README_FINBERT_BEDROCK_IMPLEMENTACION.md
├── infra/
│   └── cloudformation/
│       ├── 00_foundation.yml
│       └── 01_fargate_streamlit.yml
├── scripts/
│   ├── 00_deploy_foundation.sh
│   ├── 02_preflight_local.sh
│   ├── 03_validate_cloudformation.sh
│   ├── 04_local_smoke_test.sh
│   ├── 06_build_push_app.sh
│   ├── 07_deploy_ecs.sh
│   ├── 08_smoke_test_cloud.sh
│   ├── 09_print_outputs.sh
│   └── 10_troubleshoot_ecs.sh
├── src/
│   └── financial_sentiment/
│       ├── bedrock.py
│       ├── config.py
│       ├── finbert.py
│       ├── pipeline.py
│       ├── preprocessing.py
│       ├── retrieval.py
│       ├── schema_inference.py
│       ├── sentiment.py
│       ├── storage.py
│       ├── topics.py
│       └── jobs/
│           ├── __init__.py
│           └── batch_process.py
├── tests/
│   ├── test_finbert_interface.py
│   ├── test_schema_inference.py
│   └── ...
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── README.md
└── uv.lock
```

---

## 12. Variables de entorno principales

### Configuración general

```bash
export AWS_REGION=us-east-1
export DATA_BACKEND=local
```

Para S3:

```bash
export DATA_BACKEND=s3
export APP_BUCKET=nombre-del-bucket
```

### Modelo de sentimiento

Modo barato:

```bash
export SENTIMENT_MODEL=lexicon
```

Modo FinBERT:

```bash
export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16
```

### Bedrock

Desactivado:

```bash
export USE_BEDROCK=false
export USE_BEDROCK_SCHEMA=false
```

Activado:

```bash
export USE_BEDROCK=true
export USE_BEDROCK_SCHEMA=true
export BEDROCK_MODEL_ID=amazon.titan-text-lite-v1
```

---

## 13. Instalación local

### 13.1 Sincronizar ambiente

```bash
uv sync --all-groups
```

### 13.2 Ejecutar pruebas

```bash
PYTHONPATH=src uv run pytest -q
```

Resultado esperado:

```text
14 passed
```

### 13.3 Revisar estilo

```bash
uv run ruff check .
uv run ruff format .
```

---

## 14. Correr la app localmente

### 14.1 Modo default con modelo léxico

```bash
export SENTIMENT_MODEL=lexicon
export USE_BEDROCK=false
export USE_BEDROCK_SCHEMA=false

PYTHONPATH=src uv run streamlit run app/streamlit_app.py
```

Abrir:

```text
http://localhost:8501
```

---

### 14.2 Modo FinBERT local

```bash
export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16
export USE_BEDROCK=false
export USE_BEDROCK_SCHEMA=false

PYTHONPATH=src uv run streamlit run app/streamlit_app.py
```

La primera ejecución puede tardar porque descarga el modelo desde Hugging Face.

---

### 14.3 Modo Bedrock local

Primero se debe tener AWS CLI configurado:

```bash
aws sts get-caller-identity
```

Luego:

```bash
export AWS_REGION=us-east-1
export USE_BEDROCK=true
export USE_BEDROCK_SCHEMA=true
export BEDROCK_MODEL_ID=amazon.titan-text-lite-v1

PYTHONPATH=src uv run streamlit run app/streamlit_app.py
```

El modelo debe estar habilitado en Amazon Bedrock desde AWS Console.

---

## 15. Job batch por terminal

El proyecto incluye un job batch ejecutable.

Archivo:

```text
src/financial_sentiment/jobs/batch_process.py
```

Ejemplo local:

```bash
PYTHONPATH=src uv run python -m financial_sentiment.jobs.batch_process \
  --input-path data/sample_tweets.csv \
  --output-path data/processed/sample_processed.parquet \
  --sentiment-model lexicon
```

Ejemplo con S3:

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

## 16. Despliegue en AWS

### 16.1 Variables base

```bash
export PROJECT_NAME=financial-sentiment-radar
export ENVIRONMENT=dev
export AWS_REGION=us-east-1
```

### 16.2 Desplegar foundation

```bash
./scripts/00_deploy_foundation.sh
source config/generated.env
```

Esto crea:

- Bucket S3.
- Repositorio ECR.
- Archivo `config/generated.env`.

---

### 16.3 Construir y subir imagen a ECR

```bash
./scripts/06_build_push_app.sh
```

Este script usa:

```bash
docker buildx build --platform linux/amd64
```

Esto es necesario para evitar errores de arquitectura en Fargate.

---

### 16.4 Desplegar app con modelo léxico

Recomendado para primer despliegue porque es más rápido y barato.

```bash
export SENTIMENT_MODEL=lexicon
export USE_BEDROCK=false
export USE_BEDROCK_SCHEMA=false
export TASK_CPU=512
export TASK_MEMORY=1024

./scripts/07_deploy_ecs.sh
./scripts/09_print_outputs.sh
```

---

### 16.5 Desplegar app con FinBERT

```bash
export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16

export USE_BEDROCK=false
export USE_BEDROCK_SCHEMA=false

export TASK_CPU=1024
export TASK_MEMORY=4096

./scripts/06_build_push_app.sh
./scripts/07_deploy_ecs.sh
./scripts/09_print_outputs.sh
```

---

### 16.6 Desplegar app con FinBERT + Bedrock

```bash
export SENTIMENT_MODEL=finbert
export FINBERT_MODEL_NAME=ProsusAI/finbert
export FINBERT_BATCH_SIZE=16

export USE_BEDROCK=true
export USE_BEDROCK_SCHEMA=true
export BEDROCK_MODEL_ID=amazon.titan-text-lite-v1

export TASK_CPU=1024
export TASK_MEMORY=4096

./scripts/06_build_push_app.sh
./scripts/07_deploy_ecs.sh
./scripts/09_print_outputs.sh
```

---

## 17. Validar app en AWS

Obtener URL:

```bash
./scripts/09_print_outputs.sh
```

Smoke test:

```bash
./scripts/08_smoke_test_cloud.sh
```

Revisar logs:

```bash
aws logs tail "/ecs/financial-sentiment-radar-dev" \
  --region us-east-1 \
  --since 30m
```

Revisar estado ECS:

```bash
aws ecs describe-services \
  --region us-east-1 \
  --cluster financial-sentiment-radar-dev-cluster \
  --services financial-sentiment-radar-dev-service \
  --query "services[0].events[0:10].[createdAt,message]" \
  --output json
```

Revisar target group:

```bash
TG_ARN=$(aws elbv2 describe-target-groups \
  --region us-east-1 \
  --query "TargetGroups[?contains(TargetGroupName, 'financ')].TargetGroupArn | [0]" \
  --output text)

aws elbv2 describe-target-health \
  --region us-east-1 \
  --target-group-arn "$TG_ARN" \
  --output json
```

---

## 18. Errores comunes

### 18.1 Imagen incompatible con Fargate

Error:

```text
image Manifest does not contain descriptor matching platform 'linux/amd64'
```

Solución:

```bash
docker buildx build --platform linux/amd64 -t "${IMAGE_URI}" --push .
```

Ya está incorporado en:

```text
scripts/06_build_push_app.sh
```

---

### 18.2 FinBERT consume demasiada memoria

Síntoma:

```text
Task stopped
OutOfMemoryError
Container killed
```

Solución:

```bash
export TASK_CPU=1024
export TASK_MEMORY=4096
./scripts/07_deploy_ecs.sh
```

---

### 18.3 Bedrock no responde

Posibles causas:

- El modelo no está habilitado en la consola de Bedrock.
- La región no coincide.
- La task role no tiene permiso `bedrock:InvokeModel`.
- `USE_BEDROCK=true` pero `BEDROCK_MODEL_ID` no existe en la región.

Prueba:

```bash
aws bedrock list-foundation-models --region us-east-1
```

---

### 18.4 La app no carga archivos

Revisar:

- Que el archivo sea CSV o Parquet.
- Que no esté corrupto.
- Que tenga al menos una columna textual.
- Que el archivo no sea demasiado grande para la memoria de la task.

---

## 19. Costos y trade-offs

### Modelo léxico

Más barato y rápido.

Recomendado para:

- Pruebas.
- Demos.
- Validación inicial.
- Bajo costo.

### FinBERT

Más preciso, pero más costoso.

Recomendado para:

- Producto más serio.
- Clasificación financiera con mejor contexto.
- Archivos batch medianos.

### Bedrock

Útil para:

- Explicar resultados.
- Responder preguntas.
- Inferir esquemas ambiguos.

No se recomienda mandar todos los tweets a Bedrock. Es mejor mandar evidencia resumida o muestras pequeñas.

---

## 20. Comandos de desarrollo recomendados

Antes de cada commit:

```bash
uv sync --all-groups
PYTHONPATH=src uv run pytest -q
uv run ruff check . --fix
uv run ruff format .
uv run ruff check .
```

Commit:

```bash
git status --short
git add -A app src tests infra scripts docs
git add Dockerfile README.md README_PROYECTO.md pyproject.toml requirements.txt uv.lock
git commit -m "Update project documentation and FinBERT Bedrock pipeline"
git push
```

No usar `git add .` si no estás completamente seguro de qué archivos se van a subir.

---

## 21. Archivos que no deben subirse

No subir:

```text
.env
.env.local
config/generated.env
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.DS_Store
*.pem
*.key
data/schema-mappings/
data/raw/
data/processed/
```

---

## 22. Resumen ejecutivo

Este proyecto implementa un producto de datos financiero en AWS. La aplicación permite cargar archivos con tweets o textos financieros, detectar automáticamente la columna de texto, clasificar sentimiento, generar métricas por empresa y responder preguntas del usuario con evidencia.

La arquitectura usa:

- Streamlit para la interfaz.
- Python para el pipeline analítico.
- FinBERT para sentimiento financiero.
- Bedrock para razonamiento y explicación.
- S3 para almacenamiento.
- ECR para imágenes Docker.
- ECS Fargate para ejecución.
- ALB para exposición pública.
- CloudWatch para logs.
- IAM para permisos seguros.
- CloudFormation para infraestructura reproducible.

La solución está diseñada como MVP escalable: por default usa un clasificador léxico barato, pero puede activar FinBERT y Bedrock cuando se requiera mayor capacidad analítica.
