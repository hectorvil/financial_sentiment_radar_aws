# Documento de definición del producto

## Producto

**Financial Sentiment Radar** es un producto de datos en AWS que transforma textos financieros de social media en señales accionables de sentimiento, tema y evidencia consultable. El usuario final consume el producto en una aplicación Streamlit pública desplegada en Amazon ECS Fargate.

## 1. ¿Quién es el cliente o usuario final?

El usuario final principal es un analista financiero, analista de riesgo reputacional o integrante de un equipo de relación con inversionistas que monitorea empresas públicas. También puede usarlo un instructor del curso para evaluar el ciclo completo de producto de datos: adquisición, procesamiento, inteligencia, almacenamiento en nube y consumo en una app.

## 2. ¿Cuál es el problema u oportunidad que tiene el cliente?

El cliente necesita detectar rápidamente cambios de percepción sobre empresas como NVIDIA, Tesla, Apple, Microsoft, BBVA o bancos. Social media contiene señales tempranas de preocupación, entusiasmo o incertidumbre, pero leer tweets manualmente no escala y no deja trazabilidad. La oportunidad es convertir ese ruido textual en un radar consultable: ¿qué se dice?, ¿con qué tono?, ¿sobre qué tema?, ¿qué evidencia lo respalda?

## 3. ¿Cuál es el beneficio más importante que el producto le entrega al cliente?

El beneficio central es **reducir el tiempo de detección e interpretación de señales de sentimiento financiero**. En lugar de revisar cientos de textos, el usuario entra a una app, filtra por compañía, revisa ratios de sentimiento y pregunta en lenguaje natural. La salida no es un dato crudo: es una síntesis con evidencia recuperada y métricas agregadas.

## 4. ¿Cómo sabes cuál es la necesidad del cliente?

La necesidad se infiere del flujo original del repositorio `financial_tweet_agent`, que ya buscaba clasificar tweets financieros por sentimiento, hacer consultas históricas y visualizar sentimiento por ticker. La rúbrica del curso también exige que el proyecto tenga adquisición de datos, transformación, analítica/inteligencia y un mecanismo de consumo en Streamlit. Esta versión convierte ese prototipo en un producto de datos operable en AWS, con almacenamiento S3, contenedores, Fargate, ALB y logs.

## 5. ¿Cómo es la experiencia del cliente al usar el producto?

El usuario abre una URL pública de Streamlit. Primero ve un resumen con KPIs: número de textos procesados, ratio positivo, ratio negativo y menciones mapeadas a tickers. Después puede consultar rankings por compañía, tendencias de sentimiento y temas con concentración negativa. En la pestaña de consultas escribe preguntas como “¿Qué se dice de NVIDIA?” o “¿qué riesgos aparecen para Tesla?”. La app recupera evidencia textual, genera una respuesta extractiva local o un resumen con Amazon Bedrock si está habilitado, y muestra los textos fuente. El usuario también puede subir nuevos CSV/Parquet o, si tiene token, consultar Twitter/X en vivo.
