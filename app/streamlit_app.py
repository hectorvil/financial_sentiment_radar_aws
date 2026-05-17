"""Streamlit UI for Financial Sentiment Radar.

This is the product-consumption layer. It lets a financial analyst upload
or fetch social-media text, persist raw and processed data to S3, explore
sentiment metrics, and ask grounded questions over the active corpus.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from financial_sentiment.analytics import (
    sentiment_by_ticker,
    sentiment_trend,
    top_risk_topics,
)
from financial_sentiment.bedrock import summarize_with_bedrock
from financial_sentiment.charts import (
    build_ticker_bar,
    build_topic_bar,
    build_trend_line,
)
from financial_sentiment.config import AppConfig
from financial_sentiment.io_helpers import read_uploaded_dataframe
from financial_sentiment.logging_utils import configure_logging
from financial_sentiment.pipeline import process_tweets
from financial_sentiment.retrieval import TweetRetriever, build_extractive_answer
from financial_sentiment.schema_inference import infer_schema
from financial_sentiment.storage import LocalStorage, S3Storage
from financial_sentiment.twitter_live import fetch_recent_tweets

configure_logging()
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Financial Sentiment Radar",
    page_icon="",
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


def sanitize_filename(filename: str) -> str:
    """Return a safe filename stem for S3/local keys."""
    stem = Path(filename).stem.lower()
    stem = re.sub(r"[^a-z0-9_-]+", "_", stem).strip("_")
    return stem or "uploaded_file"


def get_content_type(filename: str) -> str:
    """Infer a basic content type from filename."""
    if filename.lower().endswith(".csv"):
        return "text/csv"

    if filename.lower().endswith(".parquet"):
        return "application/octet-stream"

    return "application/octet-stream"


def get_config_value(config: AppConfig, name: str, default):
    """Read optional config attributes without breaking older configs."""
    return getattr(config, name, default)


def get_raw_prefix(config: AppConfig) -> str:
    """Return raw upload prefix.

    User-uploaded raw files are intentionally separated from the default
    preloaded tweet batch. The final upload key is:

        raw/uploads/<timestamp>_<filename>
    """
    return "raw/"


def get_processed_prefix(config: AppConfig) -> str:
    """Return processed upload prefix.

    User-uploaded processed files are intentionally separated from the default
    visualization batch. The final processed key is:

        processed/uploads/<timestamp>_<filename>_processed.parquet
    """
    return "processed/"


def process_with_config(raw_df: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    """Process tweets using either the new configurable pipeline or legacy pipeline."""
    sentiment_model = get_config_value(config, "sentiment_model", "lexicon")
    finbert_model_name = get_config_value(config, "finbert_model_name", "ProsusAI/finbert")
    finbert_batch_size = int(get_config_value(config, "finbert_batch_size", 16))

    try:
        return process_tweets(
            raw_df,
            sentiment_model=sentiment_model,
            finbert_model_name=finbert_model_name,
            finbert_batch_size=finbert_batch_size,
        )
    except TypeError:
        logger.warning("process_tweets_legacy_signature_used")
        return process_tweets(raw_df)


def bootstrap_state(config: AppConfig) -> None:
    """Initialize session state with the default processed dataset."""
    if "default_df" in st.session_state and "active_df" in st.session_state:
        return

    storage = get_storage(config)
    sample_path = Path("data/sample_tweets.csv")

    try:
        if isinstance(storage, S3Storage) and storage.exists(config.processed_key):
            default_df = storage.read_dataframe(config.processed_key)
            st.session_state.default_df = default_df
            st.session_state.active_df = default_df
            st.session_state.data_source = f"s3://{config.s3_bucket}/{config.processed_key}"
            st.session_state.active_mode = "default_batch"
            return
    except Exception as exc:  # pragma: no cover - Streamlit UX path
        logger.exception("s3_bootstrap_failed error_type=%s", type(exc).__name__)
        st.warning("No pude leer el dataset procesado desde S3; usaré el dataset de demo local.")

    raw = load_sample_data(str(sample_path))
    default_df = process_with_config(raw, config)

    st.session_state.default_df = default_df
    st.session_state.active_df = default_df
    st.session_state.data_source = str(sample_path)
    st.session_state.active_mode = "default_batch"

    if isinstance(storage, S3Storage):
        try:
            storage.write_dataframe(default_df, config.processed_key)
            st.session_state.data_source = f"s3://{config.s3_bucket}/{config.processed_key}"
        except Exception as exc:  # pragma: no cover - Streamlit UX path
            logger.exception("s3_sample_write_failed error_type=%s", type(exc).__name__)
            st.warning("Procesé el dataset de demo, pero no pude escribirlo en S3.")


def persist_raw_upload(config: AppConfig, filename: str, content: bytes) -> str:
    """Persist the raw uploaded file to S3/local storage."""
    storage = get_storage(config)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_name = sanitize_filename(filename)
    extension = Path(filename).suffix.lower() or ".bin"

    raw_key = f"{get_raw_prefix(config)}uploads/{timestamp}_{safe_name}{extension}"

    return str(
        storage.write_bytes(
            content,
            raw_key,
            content_type=get_content_type(filename),
        )
    )


def persist_processed_upload(config: AppConfig, processed: pd.DataFrame, filename: str) -> str:
    """Persist the processed uploaded dataset as its own object."""
    storage = get_storage(config)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_name = sanitize_filename(filename)

    processed_key = (
        f"{get_processed_prefix(config)}uploads/{timestamp}_{safe_name}_processed.parquet"
    )

    return str(storage.write_dataframe(processed, processed_key))


def persist_default_batch(config: AppConfig, default_df: pd.DataFrame) -> str:
    """Persist the default batch/latest dataset."""
    storage = get_storage(config)
    return str(storage.write_dataframe(default_df, config.processed_key))


def merge_with_default(default_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """Append processed rows to the default corpus and deduplicate."""
    if default_df.empty:
        combined = new_df.copy()
    else:
        combined = pd.concat([default_df, new_df], ignore_index=True)

    if "doc_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["doc_id"])

    return combined.reset_index(drop=True)


def reset_to_default_batch() -> None:
    """Switch the active view back to the default batch."""
    st.session_state.active_df = st.session_state.default_df
    st.session_state.active_mode = "default_batch"
    st.session_state.data_source = st.session_state.get(
        "default_source",
        st.session_state.get("data_source", "default_batch"),
    )


def render_upload_controls(config: AppConfig) -> None:
    """Render upload controls and process user files."""
    uploaded = st.sidebar.file_uploader(
        "Subir CSV o Parquet",
        type=["csv", "parquet"],
        help="El archivo original se guarda en raw/uploads/ y el procesado en processed/uploads/.",
    )

    if uploaded is None:
        return

    try:
        raw = read_uploaded_dataframe(uploaded)
    except Exception as exc:  # pragma: no cover - Streamlit UX path
        logger.exception("uploaded_file_read_failed error_type=%s", type(exc).__name__)
        st.sidebar.error(f"No pude leer el archivo: {exc}")
        return

    if raw.empty:
        st.sidebar.warning("El archivo no tiene registros.")
        return

    use_bedrock_schema = bool(
        get_config_value(
            config, "use_bedrock_schema", get_config_value(config, "use_bedrock", False)
        )
    )

    mapping = infer_schema(
        raw,
        use_bedrock=use_bedrock_schema,
        model_id=config.bedrock_model_id,
        region_name=config.aws_region,
    )

    st.sidebar.caption("Inferencia de columna")
    st.sidebar.write(f"Método: `{mapping.method}`")
    st.sidebar.write(f"Confianza: `{mapping.confidence:.2f}`")
    st.sidebar.write(f"Razón: {mapping.reason}")

    columns = list(raw.columns)

    if mapping.tweet_text_column in columns:
        default_index = columns.index(mapping.tweet_text_column)
    elif "text" in columns:
        default_index = columns.index("text")
    else:
        default_index = 0

    selected_text_column = st.sidebar.selectbox(
        "Columna de texto a clasificar",
        columns,
        index=default_index,
    )

    add_to_default_batch = st.sidebar.checkbox(
        "Agregar este archivo al batch default de sentimientos",
        value=False,
        help=(
            "Si lo activas, el archivo se concatena con el corpus default y se actualiza "
            "processed/tweets/financial_sentiment_latest.parquet."
        ),
    )

    show_after_processing = st.sidebar.checkbox(
        "Mostrar este archivo después de procesarlo",
        value=True,
        help="Si no lo agregas al batch default, la app mostrará este archivo como vista activa.",
    )

    if not st.sidebar.button("Guardar y procesar archivo cargado"):
        return

    try:
        with st.spinner("Guardando raw, procesando archivo y actualizando vista..."):
            raw_bytes = uploaded.getvalue()
            raw_location = persist_raw_upload(config, uploaded.name, raw_bytes)

            canonical = raw.copy()
            canonical["text"] = canonical[selected_text_column].fillna("").astype(str)

            processed = process_with_config(canonical, config)

            if processed.empty:
                st.sidebar.warning("El archivo no contiene textos válidos después de la limpieza.")
                return

            processed["source_file"] = uploaded.name
            processed["raw_location"] = raw_location
            processed["loaded_at"] = datetime.now(UTC).isoformat()

            processed_location = persist_processed_upload(config, processed, uploaded.name)

            if add_to_default_batch:
                current_default = st.session_state.get("default_df", pd.DataFrame())
                updated_default = merge_with_default(current_default, processed)

                latest_location = persist_default_batch(config, updated_default)

                st.session_state.default_df = updated_default
                st.session_state.active_df = updated_default
                st.session_state.data_source = latest_location
                st.session_state.default_source = latest_location
                st.session_state.active_mode = "default_batch"

                st.sidebar.success(
                    f"{len(processed):,} textos procesados y agregados al batch default."
                )
            else:
                if show_after_processing:
                    st.session_state.active_df = processed
                    st.session_state.data_source = processed_location
                    st.session_state.active_mode = "uploaded_file"

                st.sidebar.success(
                    f"{len(processed):,} textos procesados. El batch default no fue modificado."
                )

            st.session_state.last_raw_upload = raw_location
            st.session_state.last_processed_upload = processed_location
            st.rerun()

    except Exception as exc:  # pragma: no cover - Streamlit UX path
        logger.exception("uploaded_file_processing_failed error_type=%s", type(exc).__name__)
        st.sidebar.error(f"No pude procesar el archivo: {exc}")


def render_live_controls(config: AppConfig) -> None:
    """Render optional Twitter/X live search controls."""
    live_query = st.sidebar.text_input(
        "Consulta live en X",
        value="(NVDA OR TSLA OR AAPL) lang:en -is:retweet",
    )
    max_results = st.sidebar.slider("Tweets live", 10, 100, 25, 5)

    if not st.sidebar.button("Buscar live"):
        return

    if not config.twitter_bearer:
        st.sidebar.error("TWITTER_BEARER no está configurado.")
        return

    try:
        with st.spinner("Consultando Twitter/X y procesando resultados..."):
            rows = fetch_recent_tweets(
                live_query,
                config.twitter_bearer,
                max_results=max_results,
            )

            if not rows:
                st.sidebar.warning("Twitter/X no regresó resultados para esa consulta.")
                return

            processed = process_with_config(pd.DataFrame(rows), config)
            processed["source_file"] = "twitter_live"
            processed["loaded_at"] = datetime.now(UTC).isoformat()

            current_default = st.session_state.get("default_df", pd.DataFrame())
            updated_default = merge_with_default(current_default, processed)
            latest_location = persist_default_batch(config, updated_default)

            st.session_state.default_df = updated_default
            st.session_state.active_df = updated_default
            st.session_state.data_source = latest_location
            st.session_state.default_source = latest_location
            st.session_state.active_mode = "default_batch"

            st.sidebar.success(f"{len(processed):,} tweets live agregados al batch default.")
            st.rerun()

    except Exception as exc:  # pragma: no cover - Streamlit UX path
        logger.exception("twitter_live_processing_failed error_type=%s", type(exc).__name__)
        st.sidebar.error(f"No pude consultar Twitter/X: {exc}")


def show_sidebar(config: AppConfig) -> None:
    """Render ingestion controls in the sidebar."""
    st.sidebar.header("Ingesta de datos")
    st.sidebar.caption("Sube datos o usa Twitter/X recent search si tienes bearer token.")

    render_upload_controls(config)

    st.sidebar.divider()

    if st.session_state.get("active_mode") == "uploaded_file":
        st.sidebar.info("Estás visualizando un archivo cargado en esta sesión.")
        if st.sidebar.button("Volver al batch default"):
            reset_to_default_batch()
            st.rerun()

    render_live_controls(config)

    st.sidebar.divider()
    st.sidebar.header("Configuración")

    sentiment_model = get_config_value(config, "sentiment_model", "lexicon")
    use_bedrock_schema = get_config_value(config, "use_bedrock_schema", False)

    st.sidebar.write(f"Backend: `{config.data_backend}`")
    st.sidebar.write(f"Región: `{config.aws_region}`")
    st.sidebar.write(f"S3 bucket: `{config.s3_bucket or 'no configurado'}`")
    st.sidebar.write(f"Modelo sentimiento: `{sentiment_model}`")
    st.sidebar.write(f"Bedrock chat: `{'activo' if config.use_bedrock else 'inactivo'}`")
    st.sidebar.write(f"Bedrock schema: `{'activo' if use_bedrock_schema else 'inactivo'}`")

    if "last_raw_upload" in st.session_state:
        st.sidebar.caption(f"Último raw: {st.session_state.last_raw_upload}")

    if "last_processed_upload" in st.session_state:
        st.sidebar.caption(f"Último processed: {st.session_state.last_processed_upload}")


def show_overview(df: pd.DataFrame) -> None:
    """Render summary KPIs and charts."""
    if df.empty:
        st.info("No hay datos procesados. Sube un CSV/Parquet con textos para iniciar.")
        return

    total_mentions = len(df)
    mapped = df["primary_ticker"].ne("UNMAPPED").sum() if "primary_ticker" in df.columns else 0
    negative_ratio = df["sentiment"].eq("negative").mean() if "sentiment" in df.columns else 0
    positive_ratio = df["sentiment"].eq("positive").mean() if "sentiment" in df.columns else 0

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
        "Ejemplos: ¿Qué se dice de NVIDIA?, ¿qué riesgos aparecen para Tesla?, "
        "¿hay tono negativo sobre bancos?"
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

    if "primary_ticker" in df.columns:
        selected_ticker = st.selectbox(
            "Filtrar por ticker",
            ["TODOS"] + sorted(df["primary_ticker"].astype(str).unique().tolist()),
        )
        view = df if selected_ticker == "TODOS" else df[df["primary_ticker"].eq(selected_ticker)]
    else:
        view = df

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

    df = st.session_state.active_df

    st.title("Financial Sentiment Radar")
    st.write(
        "Producto de datos para monitorear sentimiento financiero en social media, "
        "consultar evidencia y priorizar compañías con señales de riesgo reputacional "
        "o de mercado."
    )

    st.caption(f"Fuente actual: {st.session_state.get('data_source', 'dataset en memoria')}")
    st.caption(f"Modo activo: {st.session_state.get('active_mode', 'default_batch')}")

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
