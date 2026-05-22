# Fase final: búsqueda live con preview antes de ingesta

La búsqueda live vive en **Consultas** y ahora trabaja en dos pasos:

1. Buscar y etiquetar tweets: la app consulta X/Twitter, etiqueta ruido/no ruido con Bedrock o fallback local, clasifica los relevantes con FinBERT y muestra todo antes de escribir en S3.
2. Ingestar relevantes: solo cuando el usuario confirma, los tweets relevantes se escriben a bronze/silver/gold y actualizan `gold/twitter_live/latest.parquet`.

Esto evita ingestar ruido por accidente y permite revisar evidencia antes de contaminar el dashboard live.

## Rutas S3

- `bronze/twitter_live/`: JSON raw de X, solo después de confirmar ingesta.
- `silver/tweets/source=twitter_live/`: tweets relevantes procesados.
- `gold/sentiment_by_ticker_daily/source=twitter_live/`: agregados para Athena.
- `gold/twitter_live/latest.parquet`: snapshot operativo para Streamlit.

## Cambios clave

- Slider mínimo: 3 tweets.
- Slider máximo: 25 tweets.
- Si la query principal devuelve 0 resultados, se reintenta con query menos restrictiva.
- `Tweets live` solo grafica datos ya ingeridos.
- `Temas/Riesgo` agrega una gráfica de temas con mejor perspectiva positiva.
