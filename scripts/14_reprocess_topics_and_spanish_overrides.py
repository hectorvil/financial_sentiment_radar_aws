"""Command-line utility for Financial Sentiment Radar.

This script is intended to be executed from the repository root and uses environment variables or CLI arguments to operate on project resources."""

from __future__ import annotations

import argparse
import io
from datetime import UTC, datetime

import boto3
import pandas as pd

from financial_sentiment.spanish_financial_overrides import apply_spanish_financial_overrides
from financial_sentiment.topics import add_topics


def parse_args():
    """Parses command-line arguments or structured model output.

    Returns:
        object: Result produced by the function.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_parquet_s3(s3, bucket: str, key: str) -> pd.DataFrame:
    """Reads data from storage or an API response.

    Args:
        s3: Input value consumed by this function.
        bucket: Input value consumed by this function.
        key: Input value consumed by this function.

    Returns:
        pd.DataFrame: Result produced by the function.
    """
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


def write_parquet_s3(s3, bucket: str, key: str, df: pd.DataFrame) -> None:
    """Writes data to storage in the expected project format.

    Args:
        s3: Input value consumed by this function.
        bucket: Input value consumed by this function.
        key: Input value consumed by this function.
        df: Input value consumed by this function.

    Returns:
        None: Result produced by the function.
    """
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())


def list_parquet_keys(s3, bucket: str, prefix: str) -> list[str]:
    """Implements the `list_parquet_keys` step used by this module.

    Args:
        s3: Input value consumed by this function.
        bucket: Input value consumed by this function.
        prefix: Input value consumed by this function.

    Returns:
        list[str]: Result produced by the function.
    """
    keys = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        keys.extend(
            obj["Key"] for obj in resp.get("Contents", []) if obj["Key"].endswith(".parquet")
        )
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return keys


def reprocess_df(df: pd.DataFrame) -> pd.DataFrame:
    """Transforms input data into a processed representation.

    Args:
        df: Input value consumed by this function.

    Returns:
        pd.DataFrame: Result produced by the function.
    """
    out = df.copy()

    if "clean_text" not in out.columns and "text" in out.columns:
        out["clean_text"] = out["text"].astype(str)

    out = add_topics(out)
    out = apply_spanish_financial_overrides(out)
    out["reprocessed_at"] = datetime.now(UTC).isoformat()
    return out


def main():
    """Coordinates the command-line execution path for this script.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    args = parse_args()
    s3 = boto3.client("s3")

    keys = []

    candidate_keys = [
        "processed/tweets/financial_sentiment_latest.parquet",
        "gold/twitter_live/latest.parquet",
    ]

    for key in candidate_keys:
        try:
            s3.head_object(Bucket=args.bucket, Key=key)
            keys.append(key)
        except Exception:
            pass

    keys.extend(list_parquet_keys(s3, args.bucket, "silver/tweets/source=twitter_live/"))

    seen = set()
    keys = [k for k in keys if not (k in seen or seen.add(k))]

    print(f"Parquets a reprocesar: {len(keys)}")

    for key in keys:
        df = read_parquet_s3(s3, args.bucket, key)
        before = df["topic"].value_counts(dropna=False).head(10).to_dict() if "topic" in df else {}

        out = reprocess_df(df)

        after = out["topic"].value_counts(dropna=False).head(15).to_dict() if "topic" in out else {}

        print("\nKEY:", key)
        print("shape:", df.shape)
        print("topics antes:", before)
        print("topics despues:", after)

        if not args.dry_run:
            write_parquet_s3(s3, args.bucket, key, out)
            print("written:", key)


if __name__ == "__main__":
    main()
