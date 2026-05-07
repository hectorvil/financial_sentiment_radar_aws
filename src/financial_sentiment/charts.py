"""Plotly chart builders for Streamlit."""

from __future__ import annotations

import pandas as pd
import plotly.express as px


def build_ticker_bar(aggregated: pd.DataFrame, metric: str):
    """Create a ticker bar chart for a selected metric."""

    if aggregated.empty:
        return None
    return px.bar(
        aggregated.sort_values(metric, ascending=False).head(20),
        x="tickers",
        y=metric,
        hover_data=["positive", "neutral", "negative", "total", "signal"],
        title=f"Top tickers por {metric}",
    )


def build_trend_line(trend: pd.DataFrame):
    """Create a sentiment trend line chart."""

    if trend.empty:
        return None
    return px.line(
        trend,
        x="created_at",
        y="mentions",
        color="sentiment",
        markers=True,
        title="Tendencia temporal de sentimiento",
    )


def build_topic_bar(topic_table: pd.DataFrame):
    """Create a topic risk bar chart."""

    if topic_table.empty:
        return None
    return px.bar(
        topic_table.head(12),
        x="topic",
        y="negative_ratio",
        hover_data=["total", "negative"],
        title="Temas con mayor concentración negativa",
    )
