"""Application configuration utilities.

The app reads configuration from environment variables so the same code can run
locally, in Docker, and in AWS ECS/Fargate without changing source code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    """Convert common environment string values to bool."""

    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: str | None, default: int) -> int:
    """Parse an integer environment variable with fallback."""

    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _normalize_prefix(value: str) -> str:
    """Ensure S3 prefixes end with one slash and do not start with one."""

    stripped = value.strip().strip("/")
    return f"{stripped}/" if stripped else ""


@dataclass(frozen=True)
class AppConfig:
    """Typed configuration for the financial sentiment data product."""

    project_name: str = "financial-sentiment-radar"
    aws_region: str = "us-east-1"
    data_backend: str = "local"
    s3_bucket: str | None = None
    local_data_dir: Path = Path("data")
    use_bedrock: bool = False
    use_bedrock_schema: bool = False
    bedrock_model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    twitter_bearer: str | None = None
    sentiment_model: str = "lexicon"
    finbert_model_name: str = "ProsusAI/finbert"
    finbert_batch_size: int = 16
    s3_raw_prefix: str = "raw/"
    s3_processed_prefix: str = "processed/"
    s3_schema_prefix: str = "schema-mappings/"
    s3_outputs_prefix: str = "outputs/"

    @classmethod
    def from_env(cls) -> AppConfig:
        """Build configuration from environment variables."""

        use_bedrock = _as_bool(os.getenv("USE_BEDROCK"), default=False)
        sentiment_model = os.getenv("SENTIMENT_MODEL", "lexicon").strip().lower()
        if sentiment_model not in {"lexicon", "finbert"}:
            sentiment_model = "lexicon"

        return cls(
            project_name=os.getenv("PROJECT_NAME", "financial-sentiment-radar"),
            aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
            data_backend=os.getenv("DATA_BACKEND", "local").strip().lower(),
            s3_bucket=os.getenv("S3_BUCKET") or os.getenv("DATA_BUCKET"),
            local_data_dir=Path(os.getenv("LOCAL_DATA_DIR", "data")),
            use_bedrock=use_bedrock,
            use_bedrock_schema=_as_bool(os.getenv("USE_BEDROCK_SCHEMA"), default=use_bedrock),
            bedrock_model_id=os.getenv(
                "BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-haiku-20241022-v1:0"
            ),
            twitter_bearer=os.getenv("TWITTER_BEARER"),
            sentiment_model=sentiment_model,
            finbert_model_name=os.getenv("FINBERT_MODEL_NAME", "ProsusAI/finbert"),
            finbert_batch_size=_as_int(os.getenv("FINBERT_BATCH_SIZE"), default=16),
            s3_raw_prefix=_normalize_prefix(os.getenv("S3_RAW_PREFIX", "raw/")),
            s3_processed_prefix=_normalize_prefix(os.getenv("S3_PROCESSED_PREFIX", "processed/")),
            s3_schema_prefix=_normalize_prefix(os.getenv("S3_SCHEMA_PREFIX", "schema-mappings/")),
            s3_outputs_prefix=_normalize_prefix(os.getenv("S3_OUTPUTS_PREFIX", "outputs/")),
        )

    @property
    def processed_key(self) -> str:
        """Default S3 key for the processed dataset."""

        return f"{self.s3_processed_prefix}tweets/financial_sentiment_latest.parquet"

    @property
    def raw_prefix(self) -> str:
        """S3 prefix used for raw uploads."""

        return f"{self.s3_raw_prefix}tweets/"

    @property
    def schema_prefix(self) -> str:
        """S3 prefix used for schema mappings."""

        return self.s3_schema_prefix

    @property
    def outputs_prefix(self) -> str:
        """S3 prefix used for app-generated outputs."""

        return f"{self.s3_outputs_prefix}app/"
