# FAQ del producto

## 1. ¿Qué tecnologías se utilizan?

La solución usa Python 3.12, pandas, scikit-learn, Plotly y Streamlit. En AWS usa Amazon S3 para data lake, Amazon ECR para imágenes Docker, Amazon ECS Fargate para ejecutar la app, Application Load Balancer para exponerla, IAM Roles para permisos, CloudWatch Logs para observabilidad y Amazon Bedrock opcional para resumir consultas. La infraestructura se define con AWS CloudFormation y el entorno local se administra con uv.

## 2. ¿Cómo se utiliza la solución?

El usuario abre la URL pública del Application Load Balancer. En la app puede revisar un resumen de sentimiento, hacer preguntas sobre el corpus, ver temas de riesgo y descargar datos procesados. En la barra lateral puede subir un CSV/Parquet con columna `text` o activar búsqueda live si hay un bearer token de Twitter/X configurado.

## 3. ¿Cómo se adquieren y usan los datos?

El producto acepta tres fuentes:

1. Dataset de demo incluido en `data/sample_tweets.csv`.
2. Archivo cargado por usuario con textos financieros.
3. Twitter/X recent search opcional mediante bearer token.

Después de la adquisición, el pipeline limpia texto, elimina URLs/menciones, extrae tickers o aliases de empresa, clasifica sentimiento, asigna tema de negocio y guarda el dataset procesado. En AWS se escribe en:

```text
s3://<bucket>/processed/tweets/financial_sentiment_latest.parquet
s3://<bucket>/raw/tweets/<tipo>_<timestamp>.parquet
```

## 4. ¿Qué analítica o inteligencia se aplica?

La inteligencia del MVP combina cuatro capas:

- **Extracción de entidades**: regex y diccionario de aliases para tickers como NVDA, TSLA, AAPL, MSFT, BBVA.
- **Sentimiento financiero ligero**: scorer léxico interpretable con términos positivos y negativos financieros.
- **Temas de negocio**: reglas por keywords para earnings, tasas, AI/chips, lanzamientos, riesgo/compliance y acción de mercado.
- **Consulta de evidencia**: recuperación TF-IDF con similitud coseno. Si `USE_BEDROCK=true`, la evidencia recuperada se resume con Amazon Bedrock; si no, se genera una respuesta extractiva local.

## 5. ¿Cuáles son los inputs y outputs del producto?

### Inputs

- CSV/Parquet con columna `text`.
- Opcional: `tweet_id`, `created_at`, `author`, `source`.
- Query live de Twitter/X si hay token.
- Pregunta del usuario en lenguaje natural.

### Outputs

- Dashboard de sentimiento por ticker.
- Tendencia temporal de sentimiento.
- Tabla de temas con concentración negativa.
- Respuesta a preguntas con evidencia.
- Dataset procesado descargable.
- Archivos procesados guardados en S3.
- Logs de operación en CloudWatch.

## 6. ¿Cómo consume el usuario final los outputs?

El usuario consume outputs en Streamlit. Puede ver gráficos, tablas, evidencia textual y descargar CSV. El instructor puede entrar a la URL pública del ALB sin ejecutar código. El equipo técnico puede auditar archivos S3 y logs CloudWatch.

## 7. ¿Cuánto costaría la solución a un año?

Escenario base de clase en `us-east-1`:

| Servicio | Supuesto | Costo anual aproximado |
|---|---:|---:|
| ECS Fargate | 1 task, 0.5 vCPU, 1 GB, 24/7 | USD 216 |
| Application Load Balancer | cargo fijo + 1 LCU bajo tráfico | USD 267 |
| Amazon S3 | 10 GB Standard | USD 3 |
| Amazon ECR | 2 GB imagen privada | USD 2 |
| CloudWatch Logs | 1 GB/mes | USD 6 |
| Amazon Bedrock | opcional, bajo volumen | USD 0-20 |
| Total | sin NAT Gateway ni RDS | USD 488-508/año |

La forma más efectiva de reducir el costo es apagar el servicio ECS cuando no se evalúe (`desired-count=0`) o destruir los stacks al terminar. La solución evita NAT Gateway para no agregar un costo fijo alto.

## 8. ¿Por qué no se usa Google Colab?

Porque el objetivo de la clase es transformar el análisis en un producto de datos productivo y reproducible. El pipeline corre localmente, en Docker y en AWS Fargate. Los modelos no dependen de notebooks de Colab.

## 9. ¿Por qué el modelo de sentimiento es ligero y no FinBERT?

FinBERT es valioso, pero aumenta tamaño de imagen, memoria y tiempo de arranque. Para un MVP con presupuesto controlado, un scorer léxico financiero + recuperación + Bedrock opcional demuestra inteligencia y valor sin depender de GPU. En siguientes iteraciones se puede reemplazar por FinBERT en SageMaker, Amazon Comprehend Custom Classification o una clasificación vía Bedrock.

## 10. ¿Qué componentes mínimos de la rúbrica cubre?

- Adquisición de datos: upload CSV/Parquet, dataset demo y Twitter/X opcional.
- Preprocesamiento: limpieza, fechas, tickers, deduplicación.
- Analítica/inteligencia: sentimiento, temas, recuperación de evidencia y Bedrock opcional.
- Consumo: Streamlit público en ECS Fargate.
- AWS: S3, ECR, ECS Fargate, ALB, CloudFormation, IAM, CloudWatch Logs.

## 11. ¿Qué se debe subir a Canvas?

- `product_definition.pdf`
- `product_faq.pdf`
- `architecture_solution.pdf`
- `architecture_financial_sentiment_radar.drawio`
- `presentacion_ejecutiva_15min.pptx`
- URL pública de Streamlit
- URL del repositorio con acceso al instructor

## 12. ¿Qué riesgos o limitaciones tiene?

El producto no debe interpretarse como recomendación financiera. Social media puede contener ruido, bots, ironía y sesgos. El scorer ligero no entiende todo el contexto lingüístico. El alcance del MVP es demostrar arquitectura, trazabilidad y experiencia de producto; no maximizar accuracy de NLP.
