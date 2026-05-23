"""Medallion S3 writers for Athena-ready datasets.

This module writes:
- bronze/twitter_live/: raw API captures
- silver/tweets/: standardized tweet-level facts
- gold/sentiment_by_ticker_daily/: aggregated daily sentiment by ticker
- gold/twitter_live/latest.parquet: small latest file for the Streamlit live tab
"""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime
from typing import Any

import boto3
import pandas as pd

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(UTC)


def utc_date_string(value: datetime | None = None) -> str:
    """Return YYYY-MM-DD UTC date string."""
    return (value or now_utc()).strftime("%Y-%m-%d")


def make_run_id(prefix: str = "run") -> str:
    """Generate a deterministic-ish run ID from current UTC time."""
    return f"{prefix}_{now_utc().strftime('%Y%m%dT%H%M%SZ')}"


def _write_parquet_to_s3(df: pd.DataFrame, *, bucket: str, key: str, region_name: str) -> str:
    """Write a dataframe to S3 as parquet."""
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    boto3.client("s3", region_name=region_name).put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.read(),
        ContentType="application/octet-stream",
    )
    logger.info("write_parquet_s3 bucket=%s key=%s rows=%s", bucket, key, len(df))
    return f"s3://{bucket}/{key}"


def _write_json_to_s3(payload: dict[str, Any], *, bucket: str, key: str, region_name: str) -> str:
    """Write JSON payload to S3."""
    boto3.client("s3", region_name=region_name).put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info("write_json_s3 bucket=%s key=%s", bucket, key)
    return f"s3://{bucket}/{key}"


def _read_parquet_if_exists(bucket: str, key: str, region_name: str) -> pd.DataFrame:
    """Read parquet from S3 if present, otherwise return an empty dataframe."""
    s3 = boto3.client("s3", region_name=region_name)
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if getattr(exc, "response", {}).get("Error", {}).get("Code") in {
            "NoSuchKey",
            "404",
            "NotFound",
        }:
            return pd.DataFrame()
        raise
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


def silverize_tweets(
    df: pd.DataFrame,
    *,
    source: str,
    run_id: str,
    raw_s3_uri: str | None = None,
) -> pd.DataFrame:
    """Create Athena-friendly silver tweet-level records."""
    silver = df.copy()
    ingestion_time = now_utc()
    ingestion_date = utc_date_string(ingestion_time)

    if "tweet_id" not in silver.columns and "doc_id" in silver.columns:
        silver["tweet_id"] = silver["doc_id"]

    if "created_at" in silver.columns:
        silver["created_at"] = pd.to_datetime(silver["created_at"], errors="coerce", utc=True)
    else:
        silver["created_at"] = pd.NaT

    silver["ingestion_time"] = ingestion_time.isoformat()
    silver["ingestion_date"] = ingestion_date
    silver["run_id"] = run_id
    silver["source"] = source
    silver["raw_s3_uri"] = raw_s3_uri

    expected_defaults = {
        "text": "",
        "clean_text": "",
        "author_id": None,
        "author_username": None,
        "author_name": None,
        "author_verified": None,
        "author_followers": None,
        "lang": None,
        "query_ticker": None,
        "query_name": None,
        "primary_ticker": None,
        "sentiment": None,
        "sentiment_confidence": None,
        "positive_prob": None,
        "neutral_prob": None,
        "negative_prob": None,
        "sentiment_model": None,
        "topic": None,
        "is_noise": False,
        "relevance_score": None,
        "noise_reason": None,
        "live_search_query": None,
        "x_query": None,
        "search_mode": None,
        "like_count": None,
        "retweet_count": None,
        "reply_count": None,
        "quote_count": None,
    }
    for column, default in expected_defaults.items():
        if column not in silver.columns:
            silver[column] = default

    return silver


def gold_sentiment_by_ticker_daily(silver: pd.DataFrame) -> pd.DataFrame:
    """Aggregate silver tweets into daily sentiment by ticker."""
    if silver.empty:
        return pd.DataFrame()

    df = silver.copy()
    df["created_date"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True).dt.date.astype(
        str
    )
    df["ticker"] = df.get("primary_ticker", pd.Series(index=df.index, dtype="object")).fillna(
        "UNMAPPED"
    )

    grouped = (
        df.groupby(["ticker", "created_date", "sentiment"], dropna=False)
        .size()
        .reset_index(name="mentions")
    )

    pivot = (
        grouped.pivot_table(
            index=["ticker", "created_date"],
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
    pivot["neu_ratio"] = pivot["neutral"] / pivot["total"].where(pivot["total"].ne(0), 1)
    pivot["neg_ratio"] = pivot["negative"] / pivot["total"].where(pivot["total"].ne(0), 1)
    pivot["ingestion_time"] = now_utc().isoformat()
    pivot["ingestion_date"] = utc_date_string()
    pivot["source"] = df["source"].iloc[0] if "source" in df.columns and len(df) else "unknown"
    pivot["run_id"] = df["run_id"].iloc[0] if "run_id" in df.columns and len(df) else None

    return pivot


def write_medallion_datasets(
    processed_df: pd.DataFrame,
    *,
    bucket: str,
    region_name: str,
    source: str,
    run_id: str | None = None,
    raw_s3_uri: str | None = None,
) -> dict[str, str | None]:
    """Write silver and gold medallion datasets for any processed dataframe."""
    current_run_id = run_id or make_run_id(source)
    ingestion_date = utc_date_string()

    silver = silverize_tweets(
        processed_df, source=source, run_id=current_run_id, raw_s3_uri=raw_s3_uri
    )
    silver_key = (
        f"silver/tweets/source={source}/ingestion_date={ingestion_date}/{current_run_id}.parquet"
    )
    silver_uri = _write_parquet_to_s3(
        silver, bucket=bucket, key=silver_key, region_name=region_name
    )

    gold = gold_sentiment_by_ticker_daily(silver)
    gold_uri = None
    if not gold.empty:
        gold_key = (
            f"gold/sentiment_by_ticker_daily/source={source}/ingestion_date={ingestion_date}/"
            f"{current_run_id}.parquet"
        )
        gold_uri = _write_parquet_to_s3(gold, bucket=bucket, key=gold_key, region_name=region_name)

    return {"silver_uri": silver_uri, "gold_uri": gold_uri}


def write_twitter_bronze(
    payload: dict[str, Any],
    *,
    bucket: str,
    region_name: str,
    run_id: str,
) -> str:
    """Write raw X API response as bronze JSON."""
    ingestion_date = utc_date_string()
    key = f"bronze/twitter_live/ingestion_date={ingestion_date}/{run_id}.json"
    return _write_json_to_s3(payload, bucket=bucket, key=key, region_name=region_name)


def update_live_latest(
    new_silver_df: pd.DataFrame,
    *,
    bucket: str,
    region_name: str,
    max_rows: int = 1000,
) -> str:
    """Append live tweets to a small latest parquet used by the Streamlit live tab."""
    key = "gold/twitter_live/latest.parquet"
    existing = _read_parquet_if_exists(bucket, key, region_name)

    combined = (
        pd.concat([existing, new_silver_df], ignore_index=True)
        if not existing.empty
        else new_silver_df.copy()
    )
    if "tweet_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["tweet_id"], keep="last")
    elif "text" in combined.columns:
        combined = combined.drop_duplicates(subset=["text"], keep="last")

    if "created_at" in combined.columns:
        combined = combined.sort_values("created_at", ascending=False)

    combined = combined.head(max_rows).reset_index(drop=True)
    return _write_parquet_to_s3(combined, bucket=bucket, key=key, region_name=region_name)
