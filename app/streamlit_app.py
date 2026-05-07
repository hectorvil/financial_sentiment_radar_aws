"""Streamlit UI for Financial Sentiment Radar.

This is the product-consumption layer. It lets a financial analyst upload or
fetch social-media text, persist processed data to S3, explore sentiment metrics,
and ask grounded questions over the current corpus.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from financial_sentiment.analytics import sentiment_by_ticker, sentiment_trend, top_risk_topics
from financial_sentiment.bedrock import summarize_with_bedrock
from financial_sentiment.charts import build_ticker_bar, build_topic_bar, build_trend_line
from financial_sentiment.config import AppConfig
from financial_sentiment.io_helpers import read_uploaded_dataframe
from financial_sentiment.logging_utils import configure_logging
from financial_sentiment.pipeline import process_tweets
from financial_sentiment.retrieval import TweetRetriever, build_extractive_answer
from financial_sentiment.storage import LocalStorage, S3Storage
from financial_sentiment.twitter_live import fetch_recent_tweets

configure_logging()
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Financial Sentiment Radar",
    page_icon="📈",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def load_sample_data(sample_path: str) -> pd.DataFrame:
    """Load sample data from the container/local repository."""

    return pd.read_csv(sample_path)


def get_storage(config: AppConfig):
    """Return a storage backend based on app configuration."""

    if config.data_backend == "s3" and config.s3_bucket:
        return S3Storage(config.s3_bucket, config.aws_region)
    return LocalStorage(config.local_data_dir)


def bootstrap_state(config: AppConfig) -> None:
    """Initialize session state with a processed dataset."""

    if "processed_df" in st.session_state:
        return

    storage = get_storage(config)
    sample_path = Path("data/sample_tweets.csv")

    try:
        if isinstance(storage, S3Storage) and storage.exists(config.processed_key):
            st.session_state.processed_df = storage.read_dataframe(config.processed_key)
            st.session_state.data_source = f"s3://{config.s3_bucket}/{config.processed_key}"
            return
    except Exception as exc:  # pragma: no cover - Streamlit UX path
        logger.exception("s3_bootstrap_failed error_type=%s", type(exc).__name__)
        st.warning("No pude leer el dataset procesado desde S3; usaré el dataset de demo local.")

    raw = load_sample_data(str(sample_path))
    processed = process_tweets(raw)
    st.session_state.processed_df = processed
    st.session_state.data_source = str(sample_path)

    if isinstance(storage, S3Storage):
        try:
            storage.write_dataframe(processed, config.processed_key)
            st.session_state.data_source = f"s3://{config.s3_bucket}/{config.processed_key}"
        except Exception as exc:  # pragma: no cover - Streamlit UX path
            logger.exception("s3_sample_write_failed error_type=%s", type(exc).__name__)
            st.warning("Procesé el dataset de demo, pero no pude escribirlo en S3.")


def persist_processed(config: AppConfig, processed: pd.DataFrame, label: str) -> str:
    """Persist processed data to the configured backend."""

    storage = get_storage(config)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if isinstance(storage, S3Storage):
        raw_key = f"{config.raw_prefix}{label}_{timestamp}.parquet"
        latest_key = config.processed_key
        storage.write_dataframe(processed, raw_key)
        storage.write_dataframe(processed, latest_key)
        return f"s3://{config.s3_bucket}/{latest_key}"

    local_path = f"processed/{label}_{timestamp}.parquet"
    storage.write_dataframe(processed, local_path)
    return str(config.local_data_dir / local_path)


def append_to_corpus(new_df: pd.DataFrame) -> None:
    """Append processed rows to the session corpus and deduplicate by doc_id."""

    current = st.session_state.get("processed_df", pd.DataFrame())
    combined = pd.concat([current, new_df], ignore_index=True)
    st.session_state.processed_df = combined.drop_duplicates(subset=["doc_id"]).reset_index(
        drop=True
    )


def show_sidebar(config: AppConfig) -> None:
    """Render ingestion controls in the sidebar."""

    st.sidebar.header("Ingesta de datos")
    st.sidebar.caption("Sube datos o usa Twitter/X recent search si tienes bearer token.")

    uploaded = st.sidebar.file_uploader(
        "Subir CSV o Parquet con columna text", type=["csv", "parquet"]
    )
    if uploaded is not None and st.sidebar.button("Procesar archivo cargado"):
        try:
            with st.spinner("Procesando archivo cargado..."):
                raw = read_uploaded_dataframe(uploaded)
                processed = process_tweets(raw)
                if processed.empty:
                    st.sidebar.warning(
                        "El archivo no contiene textos válidos después de la limpieza."
                    )
                    return
                append_to_corpus(processed)
                location = persist_processed(config, st.session_state.processed_df, "uploaded")
                st.session_state.data_source = location
                st.sidebar.success(f"{len(processed):,} textos procesados")
        except Exception as exc:  # pragma: no cover - Streamlit UX path
            logger.exception("uploaded_file_processing_failed error_type=%s", type(exc).__name__)
            st.sidebar.error(f"No pude procesar el archivo: {exc}")

    st.sidebar.divider()
    live_query = st.sidebar.text_input(
        "Consulta live en X", value="(NVDA OR TSLA OR AAPL) lang:en -is:retweet"
    )
    max_results = st.sidebar.slider("Tweets live", 10, 100, 25, 5)
    if st.sidebar.button("Buscar live"):
        if not config.twitter_bearer:
            st.sidebar.error("TWITTER_BEARER no está configurado.")
        else:
            try:
                with st.spinner("Consultando Twitter/X y procesando resultados..."):
                    rows = fetch_recent_tweets(
                        live_query, config.twitter_bearer, max_results=max_results
                    )
                    if not rows:
                        st.sidebar.warning("Twitter/X no regresó resultados para esa consulta.")
                        return
                    processed = process_tweets(pd.DataFrame(rows))
                    append_to_corpus(processed)
                    location = persist_processed(
                        config, st.session_state.processed_df, "twitter_live"
                    )
                    st.session_state.data_source = location
                    st.sidebar.success(f"{len(processed):,} tweets live procesados")
            except Exception as exc:  # pragma: no cover - Streamlit UX path
                logger.exception("twitter_live_processing_failed error_type=%s", type(exc).__name__)
                st.sidebar.error(f"No pude consultar Twitter/X: {exc}")

    st.sidebar.divider()
    st.sidebar.header("Configuración")
    st.sidebar.write(f"Backend: `{config.data_backend}`")
    st.sidebar.write(f"Región: `{config.aws_region}`")
    st.sidebar.write(f"S3 bucket: `{config.s3_bucket or 'no configurado'}`")
    st.sidebar.write(f"Bedrock: `{'activo' if config.use_bedrock else 'inactivo'}`")


def show_overview(df: pd.DataFrame) -> None:
    """Render summary KPIs and charts."""

    if df.empty:
        st.info("No hay datos procesados. Sube un CSV/Parquet con columna `text` para iniciar.")
        return

    total_mentions = len(df)
    mapped = df["primary_ticker"].ne("UNMAPPED").sum() if not df.empty else 0
    negative_ratio = df["sentiment"].eq("negative").mean() if not df.empty else 0
    positive_ratio = df["sentiment"].eq("positive").mean() if not df.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Textos procesados", f"{total_mentions:,}")
    col2.metric("Menciones mapeadas", f"{mapped:,}")
    col3.metric("Ratio positivo", f"{positive_ratio:.1%}")
    col4.metric("Ratio negativo", f"{negative_ratio:.1%}")

    min_mentions = st.slider("Mínimo de menciones por ticker", 1, 50, 1)
    metric = st.selectbox("Métrica para ranking", ["neg_ratio", "pos_ratio", "signal", "total"])
    ticker_table = sentiment_by_ticker(df, min_mentions=min_mentions)

    left, right = st.columns([2, 1])
    with left:
        chart = build_ticker_bar(ticker_table, metric)
        if chart:
            st.plotly_chart(chart, use_container_width=True)
        else:
            st.info("No hay suficientes menciones por ticker para graficar.")
    with right:
        st.subheader("Ranking de tickers")
        if ticker_table.empty:
            st.info("Sin datos agregados.")
        else:
            st.dataframe(ticker_table.head(15), use_container_width=True)

    trend_chart = build_trend_line(sentiment_trend(df, freq="D"))
    if trend_chart:
        st.plotly_chart(trend_chart, use_container_width=True)


def show_questions(config: AppConfig, df: pd.DataFrame) -> None:
    """Render question-answering tab."""

    st.subheader("Consulta sobre el corpus")
    st.caption(
        "Ejemplos: ¿Qué se dice de NVIDIA?, ¿qué riesgos aparecen para Tesla?, ¿hay tono negativo sobre bancos?"
    )
    query = st.text_input("Pregunta", value="¿Qué se dice de NVIDIA?")
    k = st.slider("Número de textos recuperados", 3, 20, 8)

    if st.button("Responder") and query.strip():
        retriever = TweetRetriever(df)
        results = retriever.search(query, k=k)
        with st.spinner("Generando respuesta..."):
            if config.use_bedrock:
                try:
                    answer = summarize_with_bedrock(
                        query,
                        results,
                        model_id=config.bedrock_model_id,
                        region_name=config.aws_region,
                    )
                except Exception as exc:  # pragma: no cover - Streamlit UX path
                    logger.exception("bedrock_failed error_type=%s", type(exc).__name__)
                    st.warning("Bedrock falló; usaré respuesta extractiva local.")
                    answer = build_extractive_answer(query, results)
            else:
                answer = build_extractive_answer(query, results)

        st.markdown(answer)
        st.subheader("Evidencia recuperada")
        evidence = pd.DataFrame([result.__dict__ for result in results])
        st.dataframe(evidence, use_container_width=True)


def show_topics(df: pd.DataFrame) -> None:
    """Render topic analytics."""

    topic_table = top_risk_topics(df)
    chart = build_topic_bar(topic_table)
    if chart:
        st.plotly_chart(chart, use_container_width=True)
    st.dataframe(topic_table, use_container_width=True)


def show_data_table(df: pd.DataFrame) -> None:
    """Render processed data and download button."""

    st.subheader("Dataset procesado")
    if df.empty:
        st.info("No hay datos procesados para mostrar.")
        return
    selected_ticker = st.selectbox(
        "Filtrar por ticker", ["TODOS"] + sorted(df["primary_ticker"].unique().tolist())
    )
    view = df if selected_ticker == "TODOS" else df[df["primary_ticker"].eq(selected_ticker)]
    st.dataframe(view, use_container_width=True)
    st.download_button(
        "Descargar CSV procesado",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name="financial_sentiment_processed.csv",
        mime="text/csv",
    )


def main() -> None:
    """Run the Streamlit application."""

    config = AppConfig.from_env()
    bootstrap_state(config)
    show_sidebar(config)

    df = st.session_state.processed_df

    st.title("📈 Financial Sentiment Radar")
    st.write(
        "Producto de datos para monitorear sentimiento financiero en social media, "
        "consultar evidencia y priorizar compañías con señales de riesgo reputacional o de mercado."
    )
    st.caption(f"Fuente actual: {st.session_state.get('data_source', 'dataset en memoria')}")

    tab_overview, tab_questions, tab_topics, tab_data = st.tabs(
        ["Resumen", "Consultas", "Temas/Riesgo", "Datos procesados"]
    )

    with tab_overview:
        show_overview(df)
    with tab_questions:
        show_questions(config, df)
    with tab_topics:
        show_topics(df)
    with tab_data:
        show_data_table(df)


if __name__ == "__main__":
    main()
