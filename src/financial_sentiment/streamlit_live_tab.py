"""Streamlit components for Consultas live search, live tweets and batch tabs."""

from __future__ import annotations

import io
import logging
from typing import Any

import boto3
import pandas as pd
import plotly.express as px
import streamlit as st

from financial_sentiment.additive_refinements import refine_live_question_for_x
from financial_sentiment.live_query_catalog import CURATED_MARKET_ACCOUNT_UNIVERSE
from financial_sentiment.live_search_service import (
    LiveSearchPreview,
    ingest_live_search_preview,
    preview_direct_live_search,
)

logger = logging.getLogger(__name__)


def _get_bucket(config: Any) -> str | None:
    """Get bucket from config object."""
    return getattr(config, "s3_bucket", None) or getattr(config, "app_bucket", None)


def _read_s3_parquet(bucket: str, key: str, region_name: str) -> pd.DataFrame:
    """Read parquet from S3."""
    client = boto3.client("s3", region_name=region_name)
    response = client.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(response["Body"].read()))


@st.cache_data(ttl=120, show_spinner=False)
def load_live_latest(bucket: str, region_name: str) -> pd.DataFrame:
    """Load live latest dataset cached briefly."""
    return _read_s3_parquet(bucket, "gold/twitter_live/latest.parquet", region_name)


def load_live_latest_safe(config: Any) -> pd.DataFrame:
    """Return live latest dataframe or empty dataframe."""
    bucket = _get_bucket(config)
    region = getattr(config, "aws_region", "us-east-1")
    if not bucket:
        return pd.DataFrame()
    try:
        return load_live_latest(bucket, region)
    except Exception as exc:  # pragma: no cover - Streamlit UX path
        logger.info("load_live_latest_safe_empty error_type=%s", type(exc).__name__)
        return pd.DataFrame()


def build_combined_query_corpus(config: Any, batch_df: pd.DataFrame) -> pd.DataFrame:
    """Combine batch corpus and live tweets for the Consultas retriever."""
    live = load_live_latest_safe(config)
    if live.empty:
        return batch_df
    if batch_df.empty:
        return live

    combined = pd.concat([batch_df, live], ignore_index=True, sort=False)
    if "tweet_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["tweet_id"], keep="last")
    elif "doc_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["doc_id"], keep="last")
    elif "text" in combined.columns:
        combined = combined.drop_duplicates(subset=["text"], keep="last")
    return combined.reset_index(drop=True)


def _sentiment_by_ticker(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate sentiment counts by ticker."""
    if df.empty:
        return pd.DataFrame()

    ticker_col = "primary_ticker" if "primary_ticker" in df.columns else "query_ticker"
    view = df.copy()
    view["ticker"] = view[ticker_col].fillna("UNMAPPED").astype(str)
    view = view[view["ticker"].ne("UNMAPPED")]

    grouped = (
        view.groupby(["ticker", "sentiment"], dropna=False).size().reset_index(name="mentions")
    )
    pivot = (
        grouped.pivot_table(
            index="ticker", columns="sentiment", values="mentions", fill_value=0, aggfunc="sum"
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for column in ["positive", "neutral", "negative"]:
        if column not in pivot.columns:
            pivot[column] = 0
    pivot["total"] = pivot[["positive", "neutral", "negative"]].sum(axis=1)
    pivot["pos_ratio"] = pivot["positive"] / pivot["total"].where(pivot["total"].ne(0), 1)
    pivot["neu_ratio"] = pivot["neutral"] / pivot["total"].where(pivot["total"].ne(0), 1)
    pivot["neg_ratio"] = pivot["negative"] / pivot["total"].where(pivot["total"].ne(0), 1)
    return pivot.sort_values("neg_ratio", ascending=False)


def _trend(df: pd.DataFrame) -> pd.DataFrame:
    """Build daily trend dataset."""
    if df.empty or "created_at" not in df.columns:
        return pd.DataFrame()
    view = df.copy()
    view["created_at"] = pd.to_datetime(view["created_at"], errors="coerce", utc=True).dt.date
    return (
        view.dropna(subset=["created_at"])
        .groupby(["created_at", "sentiment"], dropna=False)
        .size()
        .reset_index(name="mentions")
    )


def _filter_live_df(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Filter live dataframe by simple keyword search."""
    cleaned = query.strip().lower()
    if not cleaned:
        return df
    terms = [term for term in cleaned.split() if term]
    if not terms:
        return df

    searchable = (
        df.get("text", pd.Series(index=df.index, dtype="object")).fillna("").astype(str)
        + " "
        + df.get("primary_ticker", pd.Series(index=df.index, dtype="object")).fillna("").astype(str)
        + " "
        + df.get("topic", pd.Series(index=df.index, dtype="object")).fillna("").astype(str)
    ).str.lower()
    mask = searchable.apply(lambda text: all(term in text for term in terms))
    return df[mask].copy()


def _render_raw_preview(preview: LiveSearchPreview) -> None:
    """Render raw/noise-labelled preview table."""
    if preview.raw_df.empty:
        st.info("No se recibieron tweets para mostrar.")
        return

    st.markdown("#### Tweets encontrados antes de ingestar")
    cols = [
        col
        for col in [
            "tweet_id",
            "author_username",
            "text",
            "is_noise",
            "relevance_score",
            "noise_reason",
            "author_reliability_tier",
            "like_count",
            "retweet_count",
        ]
        if col in preview.raw_df.columns
    ]
    st.dataframe(preview.raw_df[cols], use_container_width=True)


def _render_relevant_preview(preview: LiveSearchPreview) -> None:
    """Render relevant processed preview table."""
    if preview.relevant_df.empty:
        st.warning("No hay tweets relevantes/no ruido para ingestar.")
        return

    st.markdown("#### Tweets relevantes listos para ingesta")
    cols = [
        col
        for col in [
            "created_at",
            "primary_ticker",
            "sentiment",
            "sentiment_confidence",
            "topic",
            "author_username",
            "text",
        ]
        if col in preview.relevant_df.columns
    ]
    st.dataframe(preview.relevant_df[cols], use_container_width=True)


def render_live_search_consultas(config: Any) -> None:
    """Render direct X/Twitter search inside the Consultas tab.

    Step 1 previews and labels tweets. Step 2 asks the user whether to ingest
    only relevant/no-noise tweets into S3 medallion.
    """
    st.markdown("### Búsqueda live en X/Twitter con Bedrock")
    st.caption(
        "Busca tweets recientes en X con un horizonte amplio y filtros financieros. "
        "Primero se muestran tweets ruido/relevantes; después decides si ingestar los relevantes. "
        "Bedrock etiqueta ruido/no ruido y FinBERT clasifica sentimiento."
    )

    bucket = _get_bucket(config)
    region = getattr(config, "aws_region", "us-east-1")
    if not bucket:
        st.warning(
            "No hay bucket S3 configurado. La búsqueda live necesita guardar bronze/silver/gold."
        )
        return

    col_query, col_n, col_lang = st.columns([3, 1, 1])
    user_query = col_query.text_input(
        "Pregunta live",
        value="Qué se dice de México?",
        help=(
            "Ejemplos: ¿qué se dice de Google?, ¿Tesla va mal?, "
            "¿se prevé que suba la tasa de interés en México?, ¿qué dicen traders de NVDA?"
        ),
    )
    max_results = col_n.slider("Tweets", min_value=3, max_value=25, value=10, step=1)
    language = col_lang.selectbox("Idioma", ["auto", "en", "es"], index=0)

    search_scope = st.selectbox(
        "Horizonte de búsqueda",
        ["broad_all_x", "curated_accounts"],
        index=0,
        format_func=lambda value: (
            "Todo X con filtros financieros + señal de cuentas curadas"
            if value == "broad_all_x"
            else "Solo cuentas curadas de finanzas/trading"
        ),
        help=(
            "Recomendado: Todo X con filtros financieros. Las cuentas curadas se usan como señal de confiabilidad, "
            "pero Bedrock decide ruido/no ruido tweet por tweet."
        ),
    )

    with st.expander(
        "Ver universo de cuentas curadas usado como señal de confiabilidad", expanded=False
    ):
        st.caption(
            "Incluye medios financieros, instituciones, research de mercado, cuentas mexicanas/LatAm "
            "y traders/influencers relevantes como Peter Brandt, Mark Minervini, Linda Raschke, "
            "Carter Worth, Howard Lindzon, Charlie Bilello y Kobeissi Letter."
        )
        st.write(", ".join(f"@{account}" for account in CURATED_MARKET_ACCOUNT_UNIVERSE))

    st.caption(
        "Mínimo 3 y máximo 25 tweets por consulta. La API de X puede pedir páginas mínimas mayores, "
        "pero la app recorta el resultado al número solicitado."
    )

    use_bedrock_noise = st.checkbox(
        "Usar Bedrock para filtrar ruido y resumir en español",
        value=bool(getattr(config, "use_bedrock", False)),
    )
    sort_order = st.radio(
        "Prioridad",
        ["relevancy", "recency"],
        index=0,
        horizontal=True,
        help="relevancy busca mayor relevancia; si tu acceso de X no lo soporta, el código reintenta con recency.",
    )

    if st.button("1) Buscar y etiquetar tweets"):
        bearer = getattr(config, "twitter_bearer", None)
        if not bearer:
            st.error(
                "TWITTER_BEARER no está disponible. Revisa Secrets Manager y la task definition de ECS."
            )
            return

        with st.spinner(
            "Buscando en X, etiquetando ruido y clasificando sentimiento de tweets relevantes..."
        ):
            try:
                refined_live_question = refine_live_question_for_x(user_query)
                effective_live_question = refined_live_question.refined

                if effective_live_question != user_query:
                    st.caption(f"Consulta refinada para X: {effective_live_question}")

                preview = preview_direct_live_search(
                    user_query=effective_live_question,
                    bearer_token=bearer,
                    region_name=region,
                    max_results=max_results,
                    sentiment_model=getattr(config, "sentiment_model", "finbert"),
                    finbert_model_name=getattr(config, "finbert_model_name", "ProsusAI/finbert"),
                    finbert_batch_size=int(getattr(config, "finbert_batch_size", 16)),
                    use_bedrock=use_bedrock_noise,
                    bedrock_model_id=getattr(
                        config, "bedrock_model_id", "us.anthropic.claude-3-5-haiku-20241022-v1:0"
                    ),
                    language=language,
                    sort_order=sort_order,
                    search_scope=search_scope,
                )
            except Exception as exc:  # pragma: no cover - Streamlit UX path
                logger.exception("consultas_live_preview_failed error_type=%s", type(exc).__name__)
                st.error(f"No pude ejecutar la búsqueda live: {type(exc).__name__}: {exc}")
                return

        st.session_state["live_search_preview"] = preview
        st.session_state["live_search_preview_bucket"] = bucket
        st.session_state["live_search_preview_region"] = region

    preview = st.session_state.get("live_search_preview")
    if not isinstance(preview, LiveSearchPreview):
        return

    if preview.warning:
        st.warning(preview.warning)
    st.success(
        f"Tweets solicitados: {preview.rows_requested}. "
        f"Recibidos: {preview.rows_raw}. Relevantes/no ruido: {preview.rows_relevant}."
    )
    st.markdown("#### Resumen en español preliminar")
    st.markdown(preview.summary)

    with st.container(border=True):
        st.caption("Query enviada a X")
        st.code(preview.query)

    _render_raw_preview(preview)
    _render_relevant_preview(preview)

    col_ingest, col_clear = st.columns([1, 1])
    if col_ingest.button(
        "2) Ingestar solo tweets relevantes a S3", disabled=preview.relevant_df.empty
    ):
        with st.spinner("Escribiendo bronze/silver/gold y actualizando Tweets live..."):
            try:
                result = ingest_live_search_preview(
                    preview,
                    bucket=st.session_state.get("live_search_preview_bucket", bucket),
                    region_name=st.session_state.get("live_search_preview_region", region),
                )
                load_live_latest.clear()
            except Exception as exc:  # pragma: no cover - Streamlit UX path
                logger.exception("consultas_live_ingest_failed error_type=%s", type(exc).__name__)
                st.error(f"No pude ingestar los tweets relevantes: {type(exc).__name__}: {exc}")
                return

        st.success(f"Ingesta completada. Tweets relevantes ingestados: {result.rows_relevant}.")
        if result.bronze_uri:
            st.caption(f"Bronze: {result.bronze_uri}")
        if result.silver_uri:
            st.caption(f"Silver: {result.silver_uri}")
        if result.gold_uri:
            st.caption(f"Gold: {result.gold_uri}")
        if result.latest_uri:
            st.caption(f"Latest live: {result.latest_uri}")

    if col_clear.button("Limpiar previsualización"):
        st.session_state.pop("live_search_preview", None)
        st.session_state.pop("live_search_preview_bucket", None)
        st.session_state.pop("live_search_preview_region", None)
        st.rerun()


def show_live_tweets(config: Any) -> None:
    """Render live Twitter/X dashboard tab."""
    st.subheader("Tweets live")
    st.caption(
        "Muestra tweets capturados por la ingesta programada o por búsquedas confirmadas desde Consultas. "
        "Los datos se leen desde gold/twitter_live/latest.parquet."
    )

    df = load_live_latest_safe(config)
    if df.empty:
        st.info("Aún no hay datos live en gold/twitter_live/latest.parquet.")
        return

    search_query = st.text_input("Filtrar tweets live ya ingeridos", value="")
    view = _filter_live_df(df, search_query)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Tweets live", f"{len(view):,}")
    ticker_col = "primary_ticker" if "primary_ticker" in view.columns else "query_ticker"
    col2.metric("Tickers", f"{view.get(ticker_col, pd.Series(dtype='object')).nunique():,}")
    col3.metric("Ratio positivo", f"{view['sentiment'].eq('positive').mean():.1%}")
    col4.metric("Ratio neutral", f"{view['sentiment'].eq('neutral').mean():.1%}")
    col5.metric("Ratio negativo", f"{view['sentiment'].eq('negative').mean():.1%}")

    ticker_table = _sentiment_by_ticker(view)
    left, right = st.columns([2, 1])
    with left:
        if ticker_table.empty:
            st.info("No hay suficientes tickers para graficar.")
        else:
            ratio_df = ticker_table.melt(
                id_vars="ticker",
                value_vars=["neg_ratio", "neu_ratio", "pos_ratio"],
                var_name="ratio",
                value_name="value",
            )
            fig = px.bar(
                ratio_df,
                x="ticker",
                y="value",
                color="ratio",
                barmode="group",
                title="Ratios de sentimiento por ticker en tweets live",
            )
            st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Ranking live de tickers")
        st.dataframe(ticker_table, use_container_width=True)

    trend = _trend(view)
    if not trend.empty:
        fig = px.line(
            trend,
            x="created_at",
            y="mentions",
            color="sentiment",
            markers=True,
            title="Tendencia temporal de sentimiento live",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tweets capturados")
    display_cols = [
        column
        for column in [
            "created_at",
            "query_ticker",
            "primary_ticker",
            "author_username",
            "text",
            "sentiment",
            "sentiment_confidence",
            "topic",
            "is_noise",
            "relevance_score",
            "noise_reason",
            "like_count",
            "retweet_count",
        ]
        if column in view.columns
    ]
    st.dataframe(view[display_cols].head(300), use_container_width=True)
    st.download_button(
        "Descargar tweets live CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name="twitter_live_latest.csv",
        mime="text/csv",
    )


def _positive_topic_table(df: pd.DataFrame) -> pd.DataFrame:
    """Return topics with best positive perspective."""
    if df.empty or "topic" not in df.columns or "sentiment" not in df.columns:
        return pd.DataFrame()
    grouped = df.groupby(["topic", "sentiment"], dropna=False).size().reset_index(name="mentions")
    pivot = grouped.pivot_table(
        index="topic", columns="sentiment", values="mentions", fill_value=0
    ).reset_index()
    for column in ["positive", "neutral", "negative"]:
        if column not in pivot.columns:
            pivot[column] = 0
    pivot["total"] = pivot[["positive", "neutral", "negative"]].sum(axis=1)
    pivot["positive_ratio"] = pivot["positive"] / pivot["total"].where(pivot["total"].ne(0), 1)
    return pivot.sort_values(["positive_ratio", "total"], ascending=[False, False])


def show_live_topic_insights(config: Any, batch_df: pd.DataFrame | None = None) -> None:
    """Render live and general positive topic perspectives for Temas/Riesgo."""
    if batch_df is not None and not batch_df.empty:
        st.divider()
        st.subheader("Temas con mejor perspectiva general en batch")
        positive_topics = _positive_topic_table(batch_df).head(10)
        if positive_topics.empty:
            st.info("No hay datos suficientes para temas positivos en batch.")
        else:
            st.plotly_chart(
                px.bar(
                    positive_topics,
                    x="topic",
                    y="positive_ratio",
                    title="Temas con mayor concentración positiva en batch",
                ),
                use_container_width=True,
            )
            st.dataframe(positive_topics, use_container_width=True)

    live = load_live_latest_safe(config)
    if live.empty or "topic" not in live.columns:
        st.info("Aún no hay tweets live suficientes para graficar temas live.")
        return

    st.divider()
    st.subheader("Temas live por sentimiento y tiempo")
    view = live.copy()
    view["created_at"] = pd.to_datetime(view.get("created_at"), errors="coerce", utc=True).dt.date
    view = view.dropna(subset=["created_at"])
    if view.empty:
        st.info("Los tweets live no tienen fechas válidas.")
        return

    risk = (
        view[view["sentiment"].eq("negative")]
        .groupby(["created_at", "topic"], dropna=False)
        .size()
        .reset_index(name="mentions")
    )
    positive = (
        view[view["sentiment"].eq("positive")]
        .groupby(["created_at", "topic"], dropna=False)
        .size()
        .reset_index(name="mentions")
    )

    left, right = st.columns(2)
    with left:
        if risk.empty:
            st.info("Sin temas negativos live.")
        else:
            st.plotly_chart(
                px.line(
                    risk,
                    x="created_at",
                    y="mentions",
                    color="topic",
                    markers=True,
                    title="Temas de riesgo live por línea temporal",
                ),
                use_container_width=True,
            )
    with right:
        if positive.empty:
            st.info("Sin temas positivos live.")
        else:
            st.plotly_chart(
                px.line(
                    positive,
                    x="created_at",
                    y="mentions",
                    color="topic",
                    markers=True,
                    title="Temas positivos live por línea temporal",
                ),
                use_container_width=True,
            )

    st.subheader("Temas live con mejor perspectiva")
    live_positive = _positive_topic_table(view).head(10)
    if live_positive.empty:
        st.info("Sin temas positivos live para resumir.")
    else:
        st.dataframe(live_positive, use_container_width=True)


def show_batch_dataset_tab(df: pd.DataFrame) -> None:
    """Render batch data tab with batch-specific charts and table."""
    st.subheader("Datos batch")
    st.caption(
        "Dataset batch/default cargado desde processed/tweets/financial_sentiment_latest.parquet."
    )
    if df.empty:
        st.info("No hay datos batch para mostrar.")
        return

    sentiment_counts = df.get("sentiment", pd.Series(dtype="object")).value_counts().reset_index()
    sentiment_counts.columns = ["sentiment", "mentions"]

    col1, col2 = st.columns(2)
    with col1:
        if not sentiment_counts.empty:
            st.plotly_chart(
                px.bar(
                    sentiment_counts,
                    x="sentiment",
                    y="mentions",
                    title="Distribución batch por sentimiento",
                ),
                use_container_width=True,
            )
    with col2:
        if "primary_ticker" in df.columns:
            ticker_counts = (
                df[df["primary_ticker"].ne("UNMAPPED")]
                .groupby("primary_ticker", dropna=False)
                .size()
                .reset_index(name="mentions")
                .sort_values("mentions", ascending=False)
                .head(15)
            )
            st.plotly_chart(
                px.bar(
                    ticker_counts,
                    x="primary_ticker",
                    y="mentions",
                    title="Tickers más sonados en batch",
                ),
                use_container_width=True,
            )

    if "primary_ticker" in df.columns:
        tickers = ["TODOS"] + sorted(df["primary_ticker"].dropna().astype(str).unique().tolist())
        selected_ticker = st.selectbox("Filtrar por ticker", tickers)
        view = (
            df
            if selected_ticker == "TODOS"
            else df[df["primary_ticker"].astype(str).eq(selected_ticker)]
        )
    else:
        view = df

    st.dataframe(view, use_container_width=True)
    st.download_button(
        "Descargar CSV batch",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name="financial_sentiment_batch.csv",
        mime="text/csv",
    )


def show_live_search_panel(config: Any) -> None:
    """Compatibility wrapper used by app patch script."""
    render_live_search_consultas(config)
