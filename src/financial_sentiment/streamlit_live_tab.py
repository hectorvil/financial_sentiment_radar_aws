"""Streamlit tab for live Twitter/X sentiment datasets."""

from __future__ import annotations

import io
import logging
from typing import Any

import boto3
import pandas as pd
import plotly.express as px
import streamlit as st

logger = logging.getLogger(__name__)


def _get_bucket(config: Any) -> str | None:
    """Get bucket from config object or environment-backed fields."""
    return getattr(config, "s3_bucket", None) or getattr(config, "app_bucket", None)


def _read_s3_parquet(bucket: str, key: str, region_name: str) -> pd.DataFrame:
    """Read parquet from S3."""
    client = boto3.client("s3", region_name=region_name)
    response = client.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(response["Body"].read()))


@st.cache_data(ttl=300, show_spinner=False)
def load_live_latest(bucket: str, region_name: str) -> pd.DataFrame:
    """Load live latest dataset cached for five minutes."""
    return _read_s3_parquet(bucket, "gold/twitter_live/latest.parquet", region_name)


def _sentiment_by_ticker(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate live sentiment by ticker."""
    if df.empty:
        return pd.DataFrame()

    ticker_col = "primary_ticker" if "primary_ticker" in df.columns else "query_ticker"
    view = df.copy()
    view["ticker"] = view[ticker_col].fillna("UNMAPPED").astype(str)

    grouped = (
        view.groupby(["ticker", "sentiment"], dropna=False).size().reset_index(name="mentions")
    )
    pivot = (
        grouped.pivot_table(
            index="ticker",
            columns="sentiment",
            values="mentions",
            fill_value=0,
            aggfunc="sum",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )

    for column in ["positive", "neutral", "negative"]:
        if column not in pivot.columns:
            pivot[column] = 0

    pivot["total"] = pivot[["positive", "neutral", "negative"]].sum(axis=1)
    pivot["pos_ratio"] = pivot["positive"] / pivot["total"].where(pivot["total"].ne(0), 1)
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


def show_live_tweets(config: Any) -> None:
    """Render live Twitter/X tab."""
    st.subheader("Tweets live")
    st.caption(
        "Muestra los tweets capturados por la ingesta programada cada 2 horas. "
        "La ingesta usa consultas controladas por empresa/cuenta para reducir ruido y costo."
    )

    bucket = _get_bucket(config)
    region = getattr(config, "aws_region", "us-east-1")

    if not bucket:
        st.warning("No hay bucket S3 configurado para cargar gold/twitter_live/latest.parquet.")
        return

    try:
        df = load_live_latest(bucket, region)
    except Exception as exc:  # pragma: no cover - Streamlit UX path
        logger.exception("load_live_latest_failed error_type=%s", type(exc).__name__)
        st.info(
            "Aún no hay datos live en gold/twitter_live/latest.parquet. "
            "Ejecuta la tarea programada o corre el job live_twitter_ingest manualmente."
        )
        st.code("python -m financial_sentiment.jobs.live_twitter_ingest --max-results 10")
        return

    if df.empty:
        st.info("El dataset live existe, pero no tiene filas.")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tweets live", f"{len(df):,}")
    col2.metric("Tickers", f"{df.get('primary_ticker', df.get('query_ticker')).nunique():,}")
    col3.metric("Ratio positivo", f"{df['sentiment'].eq('positive').mean():.1%}")
    col4.metric("Ratio negativo", f"{df['sentiment'].eq('negative').mean():.1%}")

    ticker_table = _sentiment_by_ticker(df)
    left, right = st.columns([2, 1])
    with left:
        if ticker_table.empty:
            st.info("No hay suficientes tickers para graficar.")
        else:
            fig = px.bar(
                ticker_table,
                x="ticker",
                y="neg_ratio",
                title="Top tickers por neg_ratio en tweets live",
            )
            st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Ranking live de tickers")
        st.dataframe(ticker_table, use_container_width=True)

    trend = _trend(df)
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
            "sentiment_model",
            "topic",
            "like_count",
            "retweet_count",
        ]
        if column in df.columns
    ]
    st.dataframe(df[display_cols].head(200), use_container_width=True)

    st.download_button(
        "Descargar tweets live CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="twitter_live_latest.csv",
        mime="text/csv",
    )
