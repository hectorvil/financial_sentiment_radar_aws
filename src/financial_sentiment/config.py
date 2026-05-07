"""Application configuration utilities.

The app reads configuration from environment variables so the same code can run
locally, in Docker, and in AWS ECS/Fargate without changing source code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    """Convert common environment string values to bool.

    Parameters
    ----------
    value:
        Raw environment variable value.
    default:
        Value used when the variable is missing.

    Returns
    -------
    bool
        Parsed boolean value.
    """

    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AppConfig:
    """Typed configuration for the financial sentiment data product.

    Attributes
    ----------
    project_name:
        Human-readable project name.
    aws_region:
        AWS region used by boto3 clients.
    data_backend:
        Either ``local`` or ``s3``. In Fargate this should be ``s3``.
    s3_bucket:
        Data lake bucket for raw, processed and output files.
    local_data_dir:
        Local directory with sample data and local outputs.
    use_bedrock:
        Whether user question summaries should call Amazon Bedrock.
    bedrock_model_id:
        Bedrock model id. The default is Amazon Titan Text Lite to minimize cost.
    twitter_bearer:
        Optional Twitter/X API bearer token for recent-search ingestion.
    """

    project_name: str = "financial-sentiment-radar"
    aws_region: str = "us-east-1"
    data_backend: str = "local"
    s3_bucket: str | None = None
    local_data_dir: Path = Path("data")
    use_bedrock: bool = False
    bedrock_model_id: str = "amazon.titan-text-lite-v1"
    twitter_bearer: str | None = None

    @classmethod
    def from_env(cls) -> AppConfig:
        """Build configuration from environment variables.

        Returns
        -------
        AppConfig
            Configuration object used by Streamlit and scripts.
        """

        return cls(
            project_name=os.getenv("PROJECT_NAME", "financial-sentiment-radar"),
            aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
            data_backend=os.getenv("DATA_BACKEND", "local").strip().lower(),
            s3_bucket=os.getenv("S3_BUCKET") or os.getenv("DATA_BUCKET"),
            local_data_dir=Path(os.getenv("LOCAL_DATA_DIR", "data")),
            use_bedrock=_as_bool(os.getenv("USE_BEDROCK"), default=False),
            bedrock_model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.titan-text-lite-v1"),
            twitter_bearer=os.getenv("TWITTER_BEARER"),
        )

    @property
    def processed_key(self) -> str:
        """Default S3 key for the processed dataset."""

        return "processed/tweets/financial_sentiment_latest.parquet"

    @property
    def raw_prefix(self) -> str:
        """S3 prefix used for raw uploads."""

        return "raw/tweets/"

    @property
    def outputs_prefix(self) -> str:
        """S3 prefix used for app-generated outputs."""

        return "outputs/app/"
