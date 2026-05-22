"""Scheduled X/Twitter live ingestion job.

This job is designed to run as an ECS Fargate scheduled task every two hours.
It performs exactly one controlled query and retrieves at most 10 posts by default.
It writes bronze, silver, gold, and latest datasets to S3.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import UTC, datetime

import pandas as pd

from financial_sentiment.live_query_catalog import (
    COMPANY_QUERIES,
    build_company_query,
    rotate_ticker,
)
from financial_sentiment.live_relevance import apply_relevance_labels, get_relevance_labels
from financial_sentiment.medallion import (
    make_run_id,
    silverize_tweets,
    update_live_latest,
    write_medallion_datasets,
    write_twitter_bronze,
)
from financial_sentiment.pipeline import process_tweets
from financial_sentiment.x_api_client import flatten_recent_search_response, search_recent_posts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    """Parse boolean-ish environment values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bucket",
        default=os.getenv("APP_BUCKET") or os.getenv("S3_BUCKET") or os.getenv("DATA_BUCKET"),
    )
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--bearer-token", default=os.getenv("TWITTER_BEARER"))
    parser.add_argument(
        "--tickers",
        default=os.getenv(
            "LIVE_TICKERS",
            "NVDA,TSLA,AAPL,GOOGL,MSFT,AMZN,JPM,BBVA,META,AMD,AVGO,INTC,NFLX,ORCL,BAC,GS,WMT,DIS",
        ),
    )
    parser.add_argument("--ticker", default=os.getenv("LIVE_TICKER"))
    parser.add_argument("--language", default=os.getenv("LIVE_LANGUAGE", "en"))
    parser.add_argument(
        "--trusted-accounts-only", default=os.getenv("LIVE_TRUSTED_ACCOUNTS_ONLY", "true")
    )
    parser.add_argument("--max-results", type=int, default=int(os.getenv("LIVE_MAX_RESULTS", "10")))
    parser.add_argument("--sentiment-model", default=os.getenv("SENTIMENT_MODEL", "lexicon"))
    parser.add_argument(
        "--use-bedrock-relevance",
        default=os.getenv("USE_BEDROCK_RELEVANCE", os.getenv("USE_BEDROCK", "false")),
    )
    parser.add_argument(
        "--bedrock-model-id",
        default=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-haiku-20241022-v1:0"),
    )
    parser.add_argument(
        "--finbert-model-name", default=os.getenv("FINBERT_MODEL_NAME", "ProsusAI/finbert")
    )
    parser.add_argument(
        "--finbert-batch-size", type=int, default=int(os.getenv("FINBERT_BATCH_SIZE", "16"))
    )
    return parser.parse_args()


def run_live_ingestion(args: argparse.Namespace) -> dict[str, str | int | None]:
    """Run one live ingestion cycle."""
    if not args.bucket:
        raise ValueError("S3 bucket is required. Set APP_BUCKET, S3_BUCKET, or DATA_BUCKET.")
    if not args.bearer_token:
        raise ValueError(
            "Twitter/X bearer token is required. Set TWITTER_BEARER via Secrets Manager."
        )

    configured_tickers = [
        ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()
    ]
    ticker = args.ticker.upper().strip() if args.ticker else rotate_ticker(configured_tickers)
    company = COMPANY_QUERIES[ticker]

    query = build_company_query(
        ticker,
        language=args.language,
        trusted_accounts_only=parse_bool(args.trusted_accounts_only, default=True),
    )
    run_id = make_run_id(f"twitter_live_{ticker.lower()}")

    logger.info(
        "twitter_live_ingest_start run_id=%s ticker=%s max_results=%s sentiment_model=%s query=%s",
        run_id,
        ticker,
        args.max_results,
        args.sentiment_model,
        query,
    )

    payload = search_recent_posts(
        bearer_token=args.bearer_token,
        query=query,
        max_results=args.max_results,
    )
    bronze_uri = write_twitter_bronze(
        payload, bucket=args.bucket, region_name=args.region, run_id=run_id
    )

    rows = flatten_recent_search_response(
        payload,
        query=query,
        query_ticker=ticker,
        query_name=company.name,
    )

    if not rows:
        logger.info("twitter_live_ingest_no_results run_id=%s ticker=%s", run_id, ticker)
        return {
            "rows": 0,
            "ticker": ticker,
            "bronze_uri": bronze_uri,
            "silver_uri": None,
            "gold_uri": None,
            "latest_uri": None,
        }

    raw_df = pd.DataFrame(rows)
    labels = get_relevance_labels(
        rows,
        user_query=ticker,
        use_bedrock=parse_bool(args.use_bedrock_relevance, default=False),
        model_id=args.bedrock_model_id,
        region_name=args.region,
    )
    labeled_df = apply_relevance_labels(raw_df, labels)
    relevant_df = labeled_df[~labeled_df["is_noise"].fillna(True)].copy()

    if relevant_df.empty:
        logger.info(
            "twitter_live_ingest_all_noise run_id=%s ticker=%s rows=%s", run_id, ticker, len(raw_df)
        )
        return {
            "rows": 0,
            "ticker": ticker,
            "bronze_uri": bronze_uri,
            "silver_uri": None,
            "gold_uri": None,
            "latest_uri": None,
        }

    processed = process_tweets(
        relevant_df,
        sentiment_model=args.sentiment_model,
        finbert_model_name=args.finbert_model_name,
        finbert_batch_size=args.finbert_batch_size,
    )
    relevance_cols = ["tweet_id", "is_noise", "relevance_score", "noise_reason"]
    processed = processed.drop(
        columns=[col for col in relevance_cols if col in processed.columns], errors="ignore"
    )
    if "tweet_id" not in relevant_df.columns:
        if "id" in relevant_df.columns:
            relevant_df["tweet_id"] = relevant_df["id"].astype(str)
        elif "doc_id" in relevant_df.columns:
            relevant_df["tweet_id"] = relevant_df["doc_id"].astype(str)
        else:
            relevant_df = relevant_df.reset_index(drop=True)
            relevant_df["tweet_id"] = [f"{run_id}_{idx}" for idx in range(len(relevant_df))]

    if "tweet_id" not in processed.columns:
        if "id" in processed.columns:
            processed["tweet_id"] = processed["id"].astype(str)
        elif "doc_id" in processed.columns:
            processed["tweet_id"] = processed["doc_id"].astype(str)
        else:
            processed = processed.reset_index(drop=True)
            relevant_df = relevant_df.reset_index(drop=True)
            ids = relevant_df["tweet_id"].astype(str).tolist()
            if len(ids) < len(processed):
                ids.extend(f"{run_id}_{idx}" for idx in range(len(ids), len(processed)))
            processed["tweet_id"] = ids[: len(processed)]

    available_relevance_cols = [col for col in relevance_cols if col in relevant_df.columns]

    if "tweet_id" not in available_relevance_cols:
        available_relevance_cols = ["tweet_id", *available_relevance_cols]

    processed = processed.drop(
        columns=[
            col
            for col in available_relevance_cols
            if col in processed.columns and col != "tweet_id"
        ],
        errors="ignore",
    )

    processed = processed.merge(
        relevant_df[available_relevance_cols].drop_duplicates(subset=["tweet_id"]),
        on="tweet_id",
        how="left",
    )
    processed["query_ticker"] = ticker
    processed["query_name"] = company.name
    processed["live_query"] = query
    processed["search_mode"] = "scheduled_catalog"
    processed["ingested_at"] = datetime.now(UTC).isoformat()

    locations = write_medallion_datasets(
        processed,
        bucket=args.bucket,
        region_name=args.region,
        source="twitter_live",
        run_id=run_id,
        raw_s3_uri=bronze_uri,
    )

    silver_df = silverize_tweets(
        processed,
        source="twitter_live",
        run_id=run_id,
        raw_s3_uri=bronze_uri,
    )
    latest_uri = update_live_latest(
        silver_df,
        bucket=args.bucket,
        region_name=args.region,
        max_rows=1000,
    )

    logger.info(
        "twitter_live_ingest_success run_id=%s ticker=%s rows=%s bronze=%s silver=%s gold=%s latest=%s",
        run_id,
        ticker,
        len(processed),
        bronze_uri,
        locations.get("silver_uri"),
        locations.get("gold_uri"),
        latest_uri,
    )

    return {
        "rows": len(processed),
        "ticker": ticker,
        "bronze_uri": bronze_uri,
        "silver_uri": locations.get("silver_uri"),
        "gold_uri": locations.get("gold_uri"),
        "latest_uri": latest_uri,
    }


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    result = run_live_ingestion(args)
    logger.info("twitter_live_ingest_result=%s", result)


if __name__ == "__main__":
    main()
