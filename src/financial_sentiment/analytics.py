"""Aggregation functions consumed by the Streamlit app."""

from __future__ import annotations

import pandas as pd


def sentiment_by_ticker(df: pd.DataFrame, min_mentions: int = 1) -> pd.DataFrame:
    """Aggregate sentiment counts and ratios by ticker.

    Parameters
    ----------
    df:
        Processed tweet dataframe.
    min_mentions:
        Minimum number of mentions required for a ticker to appear.

    Returns
    -------
    pandas.DataFrame
        Aggregated sentiment dataframe sorted by negative ratio.
    """

    if df.empty or "tickers" not in df.columns:
        return pd.DataFrame()

    exploded = df.explode("tickers").dropna(subset=["tickers"]).copy()
    exploded = exploded[exploded["tickers"].astype(str).str.len() > 0]
    if exploded.empty:
        return pd.DataFrame()

    pivot = (
        exploded.groupby(["tickers", "sentiment"], observed=True)
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    for column in ["positive", "neutral", "negative"]:
        if column not in pivot.columns:
            pivot[column] = 0

    pivot["total"] = pivot[["positive", "neutral", "negative"]].sum(axis=1)
    pivot = pivot[pivot["total"] >= min_mentions].copy()
    pivot["pos_ratio"] = pivot["positive"] / pivot["total"]
    pivot["neg_ratio"] = pivot["negative"] / pivot["total"]
    pivot["signal"] = pivot["pos_ratio"] - pivot["neg_ratio"]
    return pivot.sort_values(["neg_ratio", "total"], ascending=[False, False])


def sentiment_trend(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Build a time trend by sentiment.

    Parameters
    ----------
    df:
        Processed tweet dataframe.
    freq:
        Pandas resample frequency, for example ``D`` or ``H``.

    Returns
    -------
    pandas.DataFrame
        Time-indexed counts in long format.
    """

    if df.empty or "created_at" not in df.columns:
        return pd.DataFrame()

    trend = df.copy()
    trend["created_at"] = pd.to_datetime(trend["created_at"], errors="coerce")
    trend = trend.dropna(subset=["created_at"])
    if trend.empty:
        return pd.DataFrame()

    grouped = (
        trend.set_index("created_at")
        .groupby("sentiment")
        .resample(freq)
        .size()
        .rename("mentions")
        .reset_index()
    )
    return grouped


def top_risk_topics(df: pd.DataFrame) -> pd.DataFrame:
    """Identify topics with negative concentration.

    Parameters
    ----------
    df:
        Processed tweet dataframe.

    Returns
    -------
    pandas.DataFrame
        Topic-level risk table.
    """

    if df.empty:
        return pd.DataFrame()

    table = (
        df.assign(is_negative=df["sentiment"].eq("negative").astype(int))
        .groupby("topic", observed=True)
        .agg(total=("doc_id", "count"), negative=("is_negative", "sum"))
        .reset_index()
    )
    table["negative_ratio"] = table["negative"] / table["total"].clip(lower=1)
    return table.sort_values(["negative_ratio", "total"], ascending=[False, False])
