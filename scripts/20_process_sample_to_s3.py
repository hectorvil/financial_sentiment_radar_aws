"""Process sample data and publish it to S3.

Usage:
    PYTHONPATH=src uv run python scripts/20_process_sample_to_s3.py \
        --bucket my-bucket --region us-east-1
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from financial_sentiment.logging_utils import configure_logging
from financial_sentiment.pipeline import process_tweets
from financial_sentiment.storage import S3Storage

configure_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    """Process the sample CSV and write outputs to S3."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True, help="Destination S3 bucket")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--input", default="data/sample_tweets.csv", help="Local sample CSV")
    parser.add_argument(
        "--key",
        default="processed/tweets/financial_sentiment_latest.parquet",
        help="Destination S3 key",
    )
    args = parser.parse_args()

    raw = pd.read_csv(Path(args.input))
    processed = process_tweets(raw)
    storage = S3Storage(args.bucket, args.region)
    destination = storage.write_dataframe(processed, args.key)
    logger.info("sample_processed destination=%s rows=%s", destination, len(processed))


if __name__ == "__main__":
    main()
