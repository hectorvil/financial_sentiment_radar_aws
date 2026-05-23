"""Batch processor for variable-schema CSV/Parquet files.

Example
-------
python -m financial_sentiment.jobs.batch_process \
    --input-path s3://my-bucket/raw/file.parquet \
    --output-path s3://my-bucket/processed/file.parquet \
    --use-bedrock-schema \
    --sentiment-model finbert
"""

from __future__ import annotations

import argparse
import io
import logging
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import boto3
import pandas as pd

from financial_sentiment.pipeline import process_tweets
from financial_sentiment.schema_inference import SchemaMapping, infer_schema

logger = logging.getLogger(__name__)


def _is_s3_path(path: str) -> bool:
    """Return whether a path is an S3 URI."""

    return path.startswith("s3://")


def _split_s3_uri(path: str) -> tuple[str, str]:
    """Split an S3 URI into bucket and key."""

    parsed = urlparse(path)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError(f"Invalid S3 URI: {path}")
    return parsed.netloc, parsed.path.lstrip("/")


def read_table(path: str, *, region_name: str) -> pd.DataFrame:
    """Read CSV or Parquet from local filesystem or S3."""

    lower = path.lower()
    if _is_s3_path(path):
        bucket, key = _split_s3_uri(path)
        response = boto3.client("s3", region_name=region_name).get_object(Bucket=bucket, Key=key)
        data = response["Body"].read()
        if lower.endswith(".parquet"):
            return pd.read_parquet(io.BytesIO(data))
        if lower.endswith(".csv"):
            return pd.read_csv(io.BytesIO(data))
        raise ValueError(f"Unsupported file format: {path}")

    if lower.endswith(".parquet"):
        return pd.read_parquet(path)
    if lower.endswith(".csv"):
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file format: {path}")


def write_table(df: pd.DataFrame, path: str, *, region_name: str) -> str:
    """Write CSV or Parquet to local filesystem or S3."""

    lower = path.lower()
    if _is_s3_path(path):
        bucket, key = _split_s3_uri(path)
        buffer = io.BytesIO()
        if lower.endswith(".parquet"):
            df.to_parquet(buffer, index=False)
            content_type = "application/octet-stream"
        elif lower.endswith(".csv"):
            df.to_csv(buffer, index=False)
            content_type = "text/csv"
        else:
            raise ValueError(f"Unsupported file format: {path}")
        buffer.seek(0)
        boto3.client("s3", region_name=region_name).put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.read(),
            ContentType=content_type,
        )
        return path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if lower.endswith(".parquet"):
        df.to_parquet(path, index=False)
    elif lower.endswith(".csv"):
        df.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported file format: {path}")
    return path


def standardize_dataframe(
    df: pd.DataFrame,
    mapping: SchemaMapping,
    *,
    input_path: str,
) -> pd.DataFrame:
    """Convert an arbitrary raw dataframe into the canonical input schema."""

    if mapping.tweet_text_column is None:
        raise ValueError(f"No tweet text column found: {mapping.reason}")

    canonical = pd.DataFrame()
    canonical["text"] = df[mapping.tweet_text_column].fillna("").astype(str)
    canonical["source_file"] = Path(urlparse(input_path).path).name or Path(input_path).name
    canonical["processed_at"] = datetime.now(UTC).isoformat()
    canonical["schema_method"] = mapping.method
    canonical["schema_confidence"] = mapping.confidence
    canonical["schema_reason"] = mapping.reason

    if mapping.label_column and mapping.label_column in df.columns:
        canonical["original_label"] = df[mapping.label_column]
    if mapping.timestamp_column and mapping.timestamp_column in df.columns:
        canonical["created_at"] = df[mapping.timestamp_column]
    if mapping.ticker_column and mapping.ticker_column in df.columns:
        canonical["raw_ticker"] = df[mapping.ticker_column]

    return canonical


def run_batch(
    *,
    input_path: str,
    output_path: str,
    use_bedrock_schema: bool,
    bedrock_model_id: str,
    aws_region: str,
    sentiment_model: str,
    finbert_model_name: str,
    finbert_batch_size: int,
) -> str:
    """Execute the batch pipeline and return output location."""

    logger.info("batch_start input_path=%s output_path=%s", input_path, output_path)
    raw = read_table(input_path, region_name=aws_region)
    logger.info("batch_read rows=%s columns=%s", len(raw), list(raw.columns))

    mapping = infer_schema(
        raw,
        use_bedrock=use_bedrock_schema,
        model_id=bedrock_model_id,
        region_name=aws_region,
    )
    logger.info("schema_mapping=%s", mapping.to_dict())

    canonical = standardize_dataframe(raw, mapping, input_path=input_path)
    processed = process_tweets(
        canonical,
        sentiment_model=sentiment_model,
        finbert_model_name=finbert_model_name,
        finbert_batch_size=finbert_batch_size,
    )
    logger.info("batch_processed rows=%s", len(processed))

    location = write_table(processed, output_path, region_name=aws_region)
    logger.info("batch_success output=%s", location)
    return location


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--use-bedrock-schema", action="store_true")
    parser.add_argument("--bedrock-model-id", default="us.anthropic.claude-3-5-haiku-20241022-v1:0")
    parser.add_argument("--aws-region", default="us-east-1")
    parser.add_argument("--sentiment-model", choices=["lexicon", "finbert"], default="lexicon")
    parser.add_argument("--finbert-model-name", default="ProsusAI/finbert")
    parser.add_argument("--finbert-batch-size", type=int, default=16)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()
    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    run_batch(
        input_path=args.input_path,
        output_path=args.output_path,
        use_bedrock_schema=args.use_bedrock_schema,
        bedrock_model_id=args.bedrock_model_id,
        aws_region=args.aws_region,
        sentiment_model=args.sentiment_model,
        finbert_model_name=args.finbert_model_name,
        finbert_batch_size=args.finbert_batch_size,
    )


if __name__ == "__main__":
    main()
