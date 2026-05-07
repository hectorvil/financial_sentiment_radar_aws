"""Local and S3 storage abstractions for the app."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Literal

import boto3
import pandas as pd
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

DataFormat = Literal["csv", "parquet"]


class LocalStorage:
    """Read and write data under a local directory."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def read_dataframe(self, relative_path: str) -> pd.DataFrame:
        """Read a local CSV or Parquet file."""

        path = self.root / relative_path
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        return pd.read_csv(path)

    def write_dataframe(self, df: pd.DataFrame, relative_path: str) -> Path:
        """Write a local CSV or Parquet file."""

        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".parquet":
            df.to_parquet(path, index=False)
        else:
            df.to_csv(path, index=False)
        logger.info("write_local path=%s rows=%s", path, len(df))
        return path


class S3Storage:
    """Read and write dataframes in S3."""

    def __init__(self, bucket: str, region_name: str):
        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region_name)

    def read_dataframe(self, key: str) -> pd.DataFrame:
        """Read a CSV or Parquet dataframe from S3."""

        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"].read()
        if key.endswith(".parquet"):
            return pd.read_parquet(io.BytesIO(body))
        return pd.read_csv(io.BytesIO(body))

    def write_dataframe(self, df: pd.DataFrame, key: str) -> str:
        """Write a CSV or Parquet dataframe to S3."""

        buffer = io.BytesIO()
        if key.endswith(".parquet"):
            df.to_parquet(buffer, index=False)
            content_type = "application/octet-stream"
        else:
            df.to_csv(buffer, index=False)
            content_type = "text/csv"
        buffer.seek(0)
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=buffer.read(), ContentType=content_type
        )
        logger.info("write_s3 bucket=%s key=%s rows=%s", self.bucket, key, len(df))
        return f"s3://{self.bucket}/{key}"

    def exists(self, key: str) -> bool:
        """Return whether an S3 object exists."""

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
