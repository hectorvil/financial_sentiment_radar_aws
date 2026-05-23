from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
import pandas as pd

from financial_sentiment.pipeline import process_tweets

logger = logging.getLogger(__name__)


SPANISH_HINTS = {
    "méxico",
    "mexico",
    "banxico",
    "inflación",
    "inflacion",
    "calificación",
    "calificacion",
    "tasa",
    "tasas",
    "peso",
    "dólar",
    "dolar",
    "deuda",
    "soberana",
    "hacienda",
    "banco de méxico",
    "grado de inversión",
    "grado de inversion",
    "recortó",
    "recorta",
    "rebajó",
    "rebaja",
}

FINANCIAL_HINTS = {
    "moody",
    "fitch",
    "s&p",
    "rating",
    "calificación",
    "calificacion",
    "baa3",
    "banxico",
    "fed",
    "inflación",
    "inflacion",
    "tasa",
    "tasas",
    "peso",
    "deuda",
    "soberana",
    "mercado",
    "acciones",
    "bonos",
    "earnings",
    "revenue",
    "stock",
    "shares",
    "credit",
    "risk",
}


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "y"}


def _looks_non_english_financial(text: str) -> bool:
    normalized = str(text).lower()
    has_spanish_hint = any(term in normalized for term in SPANISH_HINTS)
    has_financial_hint = any(term in normalized for term in FINANCIAL_HINTS)
    has_non_ascii = any(ord(char) > 127 for char in normalized)
    return has_financial_hint and (has_spanish_hint or has_non_ascii)


def _invoke_claude_translation(client: Any, model_id: str, text: str) -> str:
    prompt = f"""
Translate the following social-media financial text into concise English for a financial sentiment classifier.
Keep company names, tickers, rating agencies, countries, numbers and credit ratings.
Do not explain. Return only the translated text.

Text:
{text[:1800]}
""".strip()

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 220,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
    }

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    payload = json.loads(response["body"].read())
    content = payload.get("content", [])
    if content and isinstance(content[0], dict):
        return str(content[0].get("text", "")).strip()
    return text


def _invoke_nova_translation(client: Any, model_id: str, text: str) -> str:
    prompt = f"""
Translate the following social-media financial text into concise English for a financial sentiment classifier.
Keep company names, tickers, rating agencies, countries, numbers and credit ratings.
Do not explain. Return only the translated text.

Text:
{text[:1800]}
""".strip()

    body = {
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        "inferenceConfig": {
            "maxTokens": 220,
            "temperature": 0,
            "topP": 0.9,
        },
    }

    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    payload = json.loads(response["body"].read())
    content = payload.get("output", {}).get("message", {}).get("content", [])
    if content and isinstance(content[0], dict):
        return str(content[0].get("text", "")).strip()
    return text


def _translate_text(client: Any, model_id: str, text: str) -> str:
    if "anthropic.claude" in model_id:
        return _invoke_claude_translation(client, model_id, text)
    if "amazon.nova" in model_id:
        return _invoke_nova_translation(client, model_id, text)

    # Claude/Nova are the supported translation paths. Unknown models fall back.
    return text


def _prepare_finbert_input(df: pd.DataFrame) -> pd.DataFrame:
    """Create finbert_input_text while preserving original text."""
    if df.empty or "text" not in df.columns:
        return df

    # Translation is enabled when Bedrock relevance is enabled, but can be disabled explicitly.
    if _env_true("DISABLE_BEDROCK_TRANSLATION"):
        out = df.copy()
        out["finbert_input_text"] = out["text"].astype(str)
        out["translation_model"] = "none"
        out["translation_reason"] = "disabled"
        return out

    translation_enabled = _env_true("USE_BEDROCK_TRANSLATION") or _env_true("USE_BEDROCK_RELEVANCE")

    out = df.copy()
    out["original_text"] = out["text"].astype(str)
    out["finbert_input_text"] = out["original_text"]
    out["translation_model"] = "none"
    out["translation_reason"] = "not_translated"

    if not translation_enabled:
        return out

    model_id = os.getenv(
        "BEDROCK_TRANSLATION_MODEL_ID",
        os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    )
    region = os.getenv("AWS_REGION", "us-east-1")
    max_rows = int(os.getenv("BEDROCK_TRANSLATION_MAX_ROWS", "25"))

    candidate_idx = [
        idx for idx, text in out["original_text"].items() if _looks_non_english_financial(str(text))
    ][:max_rows]

    if not candidate_idx:
        return out

    client = boto3.client("bedrock-runtime", region_name=region)

    for idx in candidate_idx:
        original = str(out.at[idx, "original_text"])
        try:
            translated = _translate_text(client, model_id, original)
            if translated and translated.strip():
                out.at[idx, "finbert_input_text"] = translated.strip()
                out.at[idx, "translation_model"] = model_id
                out.at[idx, "translation_reason"] = "non_english_financial_text"
        except Exception as exc:
            logger.warning(
                "bedrock_translation_failed error_type=%s",
                type(exc).__name__,
                exc_info=True,
            )
            out.at[idx, "finbert_input_text"] = original
            out.at[idx, "translation_model"] = "failed"
            out.at[idx, "translation_reason"] = type(exc).__name__

    return out


def process_tweets_with_optional_translation(
    raw_df: pd.DataFrame, *args: Any, **kwargs: Any
) -> pd.DataFrame:
    """Process tweets, optionally translating non-English financial texts before FinBERT.

    The original text is preserved. FinBERT sees `finbert_input_text` through a temporary
    replacement of the `text` column.
    """
    if raw_df.empty or "text" not in raw_df.columns:
        return process_tweets(raw_df, *args, **kwargs)

    prepared = _prepare_finbert_input(raw_df)

    model_df = prepared.copy()
    model_df["text"] = model_df["finbert_input_text"].astype(str)

    processed = process_tweets(model_df, *args, **kwargs)

    # Restore original text and keep translation audit columns.
    processed = processed.reset_index(drop=True)
    prepared = prepared.reset_index(drop=True)

    if len(prepared) >= len(processed):
        processed["text"] = prepared["original_text"].astype(str).iloc[: len(processed)].to_list()
        processed["finbert_input_text"] = (
            prepared["finbert_input_text"].astype(str).iloc[: len(processed)].to_list()
        )
        processed["translation_model"] = (
            prepared["translation_model"].astype(str).iloc[: len(processed)].to_list()
        )
        processed["translation_reason"] = (
            prepared["translation_reason"].astype(str).iloc[: len(processed)].to_list()
        )

    try:
        from financial_sentiment.spanish_financial_overrides import (
            apply_spanish_financial_overrides,
        )

        processed = apply_spanish_financial_overrides(processed)
    except Exception:
        logger.warning("spanish_financial_overrides_failed", exc_info=True)

    return processed
