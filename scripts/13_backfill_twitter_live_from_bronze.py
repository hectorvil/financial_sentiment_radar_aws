from __future__ import annotations

import argparse
import io
import json
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath

import boto3
import pandas as pd

from financial_sentiment.pipeline import process_tweets
from financial_sentiment.x_api_client import flatten_recent_search_response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sentiment-model", default="finbert")
    parser.add_argument("--finbert-model-name", default="ProsusAI/finbert")
    parser.add_argument("--finbert-batch-size", type=int, default=16)
    parser.add_argument("--latest-limit", type=int, default=500)
    return parser.parse_args()


def list_keys(s3, bucket: str, prefix: str) -> list[str]:
    keys = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        keys.extend(obj["Key"] for obj in resp.get("Contents", []))
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return keys


def key_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def read_json_s3(s3, bucket: str, key: str) -> dict:
    obj = s3.get_object(Bucket=bucket, Key=key)
    raw = obj["Body"].read()
    if not raw or raw.strip() in {b"", b"{}"}:
        return {}
    return json.loads(raw)


def write_parquet_s3(s3, bucket: str, key: str, df: pd.DataFrame) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())


def read_parquet_s3(s3, bucket: str, key: str) -> pd.DataFrame:
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


def extract_ingestion_date(key: str) -> str:
    m = re.search(r"ingestion_date=(\d{4}-\d{2}-\d{2})", key)
    if not m:
        raise ValueError(f"No pude extraer ingestion_date de {key}")
    return m.group(1)


def extract_run_id(key: str) -> str:
    return PurePosixPath(key).stem


def extract_ticker(run_id: str) -> str:
    m = re.match(r"twitter_live_([a-z0-9]+)_", run_id)
    if m:
        return m.group(1).upper()
    m = re.match(r"twitter_consultas_live_", run_id)
    if m:
        return "UNMAPPED"
    return "UNMAPPED"


def normalize_raw_response(payload: dict, run_id: str, query_ticker: str) -> pd.DataFrame:
    try:
        df = flatten_recent_search_response(payload)
    except Exception:
        data = payload.get("data", [])
        df = pd.DataFrame(data)

    if df.empty:
        return df

    if "tweet_id" not in df.columns:
        if "id" in df.columns:
            df["tweet_id"] = df["id"].astype(str)
        elif "doc_id" in df.columns:
            df["tweet_id"] = df["doc_id"].astype(str)
        else:
            df = df.reset_index(drop=True)
            df["tweet_id"] = [f"{run_id}_{i}" for i in range(len(df))]

    if "text" not in df.columns:
        for candidate in ["full_text", "content", "body", "message"]:
            if candidate in df.columns:
                df["text"] = df[candidate].astype(str)
                break

    if "text" not in df.columns:
        return pd.DataFrame()

    df["source"] = "twitter_live"
    df["query_ticker"] = query_ticker
    df["run_id"] = run_id
    df["is_noise"] = False
    df["relevance_score"] = 0.75
    df["noise_reason"] = "bronze_backfill_no_relevance_recheck"
    df["is_curated_market_author"] = None
    df["author_reliability_tier"] = "unknown"
    return df


def process_raw(df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    try:
        processed = process_tweets(
            df,
            sentiment_model=args.sentiment_model,
            finbert_model_name=args.finbert_model_name,
            finbert_batch_size=args.finbert_batch_size,
        )
    except TypeError:
        processed = process_tweets(df)

    if "tweet_id" not in processed.columns:
        if "tweet_id" in df.columns and len(df) >= len(processed):
            processed = processed.reset_index(drop=True)
            processed["tweet_id"] = (
                df.reset_index(drop=True)["tweet_id"].astype(str).iloc[: len(processed)]
            )
        elif "doc_id" in processed.columns:
            processed["tweet_id"] = processed["doc_id"].astype(str)

    for col in [
        "source",
        "query_ticker",
        "run_id",
        "is_noise",
        "relevance_score",
        "noise_reason",
        "is_curated_market_author",
        "author_reliability_tier",
    ]:
        if col not in processed.columns and col in df.columns:
            processed[col] = df[col].iloc[0] if len(df[col]) else None

    return processed


def make_gold(processed: pd.DataFrame, ingestion_date: str) -> pd.DataFrame:
    df = processed.copy()

    if "created_at" in df.columns:
        df["created_date"] = pd.to_datetime(df["created_at"], errors="coerce").dt.date.astype(str)
    else:
        df["created_date"] = ingestion_date

    ticker_col = "primary_ticker" if "primary_ticker" in df.columns else "query_ticker"
    df["ticker"] = df.get(ticker_col, "UNMAPPED").fillna("UNMAPPED")

    grouped = (
        df.groupby(["source", "ticker", "created_date", "sentiment"], dropna=False)
        .size()
        .reset_index(name="count")
    )

    pivot = grouped.pivot_table(
        index=["source", "ticker", "created_date"],
        columns="sentiment",
        values="count",
        fill_value=0,
        aggfunc="sum",
    ).reset_index()

    for col in ["positive", "neutral", "negative"]:
        if col not in pivot.columns:
            pivot[col] = 0

    pivot["total"] = pivot[["positive", "neutral", "negative"]].sum(axis=1)
    pivot["pos_ratio"] = pivot["positive"] / pivot["total"].where(pivot["total"] != 0, 1)
    pivot["neu_ratio"] = pivot["neutral"] / pivot["total"].where(pivot["total"] != 0, 1)
    pivot["neg_ratio"] = pivot["negative"] / pivot["total"].where(pivot["total"] != 0, 1)
    pivot["ingestion_date"] = ingestion_date
    pivot["processed_at"] = datetime.now(UTC).isoformat()

    return pivot


def update_latest(s3, bucket: str, processed: pd.DataFrame, latest_limit: int) -> None:
    latest_key = "gold/twitter_live/latest.parquet"

    if key_exists(s3, bucket, latest_key):
        current = read_parquet_s3(s3, bucket, latest_key)
        combined = pd.concat([current, processed], ignore_index=True)
    else:
        combined = processed.copy()

    if "tweet_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["tweet_id"], keep="last")

    if "created_at" in combined.columns:
        combined["_created_sort"] = pd.to_datetime(combined["created_at"], errors="coerce")
        combined = combined.sort_values("_created_sort").drop(columns=["_created_sort"])

    combined = combined.tail(latest_limit).reset_index(drop=True)
    write_parquet_s3(s3, bucket, latest_key, combined)


def main() -> None:
    args = parse_args()
    s3 = boto3.client("s3")

    keys = list_keys(s3, args.bucket, "bronze/twitter_live/")
    keys = [k for k in keys if k.endswith(".json")]

    if args.start_date:
        keys = [k for k in keys if extract_ingestion_date(k) >= args.start_date]
    if args.end_date:
        keys = [k for k in keys if extract_ingestion_date(k) <= args.end_date]

    print(f"bronze json candidates: {len(keys)}")

    processed_count = 0
    skipped_count = 0

    for key in sorted(keys):
        ingestion_date = extract_ingestion_date(key)
        run_id = extract_run_id(key)
        query_ticker = extract_ticker(run_id)

        silver_key = (
            f"silver/tweets/source=twitter_live/ingestion_date={ingestion_date}/{run_id}.parquet"
        )
        gold_key = (
            f"gold/sentiment_by_ticker_daily/source=twitter_live/"
            f"ingestion_date={ingestion_date}/{run_id}.parquet"
        )

        if not args.force and key_exists(s3, args.bucket, silver_key):
            skipped_count += 1
            continue

        payload = read_json_s3(s3, args.bucket, key)
        raw_df = normalize_raw_response(payload, run_id, query_ticker)

        if raw_df.empty:
            print(f"skip empty/no text: {key}")
            skipped_count += 1
            continue

        print(f"backfill {run_id}: raw_rows={len(raw_df)} -> {silver_key}")

        if args.dry_run:
            processed_count += 1
            continue

        processed = process_raw(raw_df, args)
        processed["source"] = "twitter_live"
        processed["ingestion_date"] = ingestion_date
        processed["processed_at"] = datetime.now(UTC).isoformat()

        gold = make_gold(processed, ingestion_date)

        write_parquet_s3(s3, args.bucket, silver_key, processed)
        write_parquet_s3(s3, args.bucket, gold_key, gold)
        update_latest(s3, args.bucket, processed, args.latest_limit)

        processed_count += 1

    print(f"done processed={processed_count} skipped={skipped_count}")


if __name__ == "__main__":
    main()
