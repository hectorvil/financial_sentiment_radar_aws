"""Schema inference for batch files with variable column names.

The product receives Parquet/CSV files that do not always use the same
schema. This module identifies which column contains the tweet/social-media
text to classify. It uses deterministic rules first and calls Amazon Bedrock
only when the local signal is ambiguous.

Bedrock receives metadata and small samples only. It never receives the full
file, which keeps cost and privacy risk low.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import asdict, dataclass
from typing import Any

import boto3
import pandas as pd

logger = logging.getLogger(__name__)

TEXT_COLUMN_NAMES = {
    "text",
    "tweet",
    "tweets",
    "full_text",
    "content",
    "body",
    "message",
    "post",
    "sentence",
    "review",
    "comentario",
    "texto",
    "publicacion",
    "publicación",
}

LABEL_COLUMN_NAMES = {
    "label",
    "labels",
    "target",
    "sentiment",
    "polarity",
    "class",
    "y",
}

TIMESTAMP_COLUMN_NAMES = {
    "date",
    "created_at",
    "timestamp",
    "time",
    "fecha",
}

TICKER_COLUMN_NAMES = {
    "ticker",
    "tickers",
    "symbol",
    "symbols",
    "company",
    "empresa",
}

FINANCE_TERMS = {
    "stock",
    "stocks",
    "shares",
    "market",
    "earnings",
    "revenue",
    "guidance",
    "profit",
    "loss",
    "downgrade",
    "upgrade",
    "bullish",
    "bearish",
    "inflation",
    "rates",
    "acciones",
    "mercado",
    "resultados",
    "utilidad",
    "ingresos",
    "tasas",
    "riesgo",
    "ganancia",
    "pérdida",
}

CASHTAG_PATTERN = re.compile(r"\$[A-Za-z]{1,6}\b")
URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
MENTION_PATTERN = re.compile(r"@\w+")
HASHTAG_PATTERN = re.compile(r"#\w+")
WORD_PATTERN = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}")


@dataclass(frozen=True)
class SchemaMapping:
    """Column mapping inferred for a raw dataset.

    Attributes
    ----------
    tweet_text_column:
        Column containing the main tweet/social-media text. ``None`` means the
        system could not identify a safe candidate.
    confidence:
        Confidence score from 0 to 1.
    method:
        ``rules``, ``needs_bedrock``, ``bedrock`` or ``bedrock_failed``.
    reason:
        Human-readable explanation for the decision.
    label_column:
        Optional existing sentiment/label column in the uploaded data.
    timestamp_column:
        Optional timestamp column.
    ticker_column:
        Optional ticker/symbol column.
    """

    tweet_text_column: str | None
    confidence: float
    method: str
    reason: str
    label_column: str | None = None
    timestamp_column: str | None = None
    ticker_column: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True)
class ColumnCandidate:
    """Internal scoring result for a column."""

    column: str
    dtype: str
    score: float
    name_score: float
    content_score: float
    sample_values: list[str]


def _normalize_name(column_name: object) -> str:
    """Normalize a column name for scoring."""

    return str(column_name).strip().lower().replace(" ", "_").replace("-", "_")


def _safe_sample(series: pd.Series, n: int = 5, max_chars: int = 300) -> list[str]:
    """Return short non-empty sample values from a column."""

    if series.empty:
        return []

    values = series.dropna().astype(str).map(lambda value: re.sub(r"\s+", " ", value).strip())
    values = values[values.str.len() > 0].head(n).tolist()
    return [value[:max_chars] for value in values]


def _guess_column_by_names(df: pd.DataFrame, names: set[str]) -> str | None:
    """Guess a column by exact or normalized name."""

    for column in df.columns:
        normalized = _normalize_name(column)
        if normalized in names:
            return str(column)
    return None


def _score_column_name(column_name: str) -> float:
    """Score a column based on its name."""

    normalized = _normalize_name(column_name)
    score = 0.0

    if normalized in TEXT_COLUMN_NAMES:
        score += 8.0
    elif any(token in normalized for token in TEXT_COLUMN_NAMES):
        score += 4.0

    if normalized in LABEL_COLUMN_NAMES or any(token in normalized for token in LABEL_COLUMN_NAMES):
        score -= 8.0

    if normalized in TIMESTAMP_COLUMN_NAMES or any(
        token in normalized for token in TIMESTAMP_COLUMN_NAMES
    ):
        score -= 6.0

    if normalized in TICKER_COLUMN_NAMES:
        score -= 2.0

    noisy_tokens = {"id", "uuid", "url", "user", "username", "author", "score", "index"}
    if any(token == normalized or normalized.endswith(f"_{token}") for token in noisy_tokens):
        score -= 5.0

    return score


def _numeric_like_ratio(sample: pd.Series) -> float:
    """Return the share of values that look numeric."""

    if sample.empty:
        return 0.0
    return float(sample.str.fullmatch(r"[-+]?\d+(\.\d+)?").mean())


def _score_text_content(series: pd.Series) -> float:
    """Score a column based on its values."""

    sample = series.dropna().astype(str).head(200)
    if sample.empty:
        return -6.0

    lengths = sample.str.len()
    avg_len = float(lengths.mean())
    unique_ratio = float(sample.nunique() / max(len(sample), 1))
    joined = " ".join(sample.head(50).tolist()).lower()

    score = 0.0

    if avg_len >= 25:
        score += 3.0
    if avg_len >= 60:
        score += 2.0
    if avg_len >= 180:
        score += 1.0
    if avg_len < 8:
        score -= 5.0

    if unique_ratio >= 0.5:
        score += 2.0
    else:
        score -= 2.0

    if CASHTAG_PATTERN.search(joined):
        score += 2.0
    if URL_PATTERN.search(joined):
        score += 1.0
    if MENTION_PATTERN.search(joined):
        score += 1.0
    if HASHTAG_PATTERN.search(joined):
        score += 1.0

    word_count = len(WORD_PATTERN.findall(joined))
    if word_count >= 20:
        score += 2.0
    elif word_count <= 3:
        score -= 2.0

    if any(term in joined for term in FINANCE_TERMS):
        score += 2.0

    if _numeric_like_ratio(sample) > 0.5:
        score -= 8.0

    return score


def get_column_candidates(df: pd.DataFrame) -> list[ColumnCandidate]:
    """Score every column and return sorted candidates."""

    candidates: list[ColumnCandidate] = []
    for column in df.columns:
        column_name = str(column)
        name_score = _score_column_name(column_name)
        content_score = _score_text_content(df[column])
        candidates.append(
            ColumnCandidate(
                column=column_name,
                dtype=str(df[column].dtype),
                score=round(name_score + content_score, 4),
                name_score=round(name_score, 4),
                content_score=round(content_score, 4),
                sample_values=_safe_sample(df[column], n=5),
            )
        )

    return sorted(candidates, key=lambda item: item.score, reverse=True)


def infer_schema_with_rules(df: pd.DataFrame) -> SchemaMapping:
    """Infer the tweet-text column using deterministic rules.

    This is the default and cheapest path. Bedrock is reserved for ambiguous
    cases.
    """

    if df.empty or len(df.columns) == 0:
        return SchemaMapping(
            tweet_text_column=None,
            confidence=0.0,
            method="rules",
            reason="El archivo no tiene columnas o está vacío.",
        )

    candidates = get_column_candidates(df)
    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    gap = best.score - second.score if second else math.inf

    label_column = _guess_column_by_names(df, LABEL_COLUMN_NAMES)
    timestamp_column = _guess_column_by_names(df, TIMESTAMP_COLUMN_NAMES)
    ticker_column = _guess_column_by_names(df, TICKER_COLUMN_NAMES)

    logger.info(
        "schema_rules best_column=%s best_score=%s gap=%s",
        best.column,
        best.score,
        gap,
    )

    if best.score >= 8.0 and gap >= 2.5:
        confidence = 0.95 if gap >= 4 else 0.85
        return SchemaMapping(
            tweet_text_column=best.column,
            confidence=confidence,
            method="rules",
            reason=(
                f"La columna '{best.column}' tiene nombre/contenido compatible "
                "con texto de tweet y supera claramente a las demás candidatas."
            ),
            label_column=label_column,
            timestamp_column=timestamp_column,
            ticker_column=ticker_column,
        )

    return SchemaMapping(
        tweet_text_column=None,
        confidence=0.0,
        method="needs_bedrock",
        reason=(
            "Hay ambigüedad entre columnas candidatas. "
            f"Mejor candidata local: '{best.column}' con score {best.score}."
        ),
        label_column=label_column,
        timestamp_column=timestamp_column,
        ticker_column=ticker_column,
    )


def build_schema_payload(
    df: pd.DataFrame, max_columns: int = 20, sample_rows: int = 5
) -> dict[str, Any]:
    """Build a small schema payload for Bedrock."""

    candidates = get_column_candidates(df)
    candidate_lookup = {candidate.column: candidate for candidate in candidates}

    columns: list[dict[str, Any]] = []
    for column in list(df.columns)[:max_columns]:
        column_name = str(column)
        candidate = candidate_lookup.get(column_name)
        columns.append(
            {
                "name": column_name,
                "dtype": str(df[column].dtype),
                "rule_score": candidate.score if candidate else None,
                "sample_values": _safe_sample(df[column], n=sample_rows),
            }
        )

    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": columns,
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from a model response."""

    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return json.loads(stripped)

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        raise ValueError("Bedrock response did not contain a JSON object.")
    return json.loads(match.group(0))


def _invoke_bedrock_text(prompt: str, model_id: str, region_name: str) -> str:
    """Invoke Bedrock and return text output for Titan or Claude-style models."""

    client = boto3.client("bedrock-runtime", region_name=region_name)

    if model_id.startswith("anthropic."):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 700,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}],
        }
    else:
        body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 700,
                "temperature": 0.0,
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

    if "results" in payload:
        return str(payload["results"][0].get("outputText", ""))

    if "content" in payload and payload["content"]:
        first = payload["content"][0]
        if isinstance(first, dict):
            return str(first.get("text", ""))

    return json.dumps(payload, ensure_ascii=False)


def infer_schema_with_bedrock(
    df: pd.DataFrame,
    *,
    model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    region_name: str = "us-east-1",
) -> SchemaMapping:
    """Ask Bedrock to identify the tweet-text column.

    The prompt requires JSON-only output and forbids inventing columns.
    """

    payload = build_schema_payload(df)
    valid_columns = {str(column) for column in df.columns}

    prompt = f"""
Eres un asistente de ingeniería de datos. Tu tarea es identificar cuál columna
contiene el texto principal de tweets o publicaciones financieras que deben
clasificarse por sentimiento.

Recibirás nombres de columnas, tipos de datos, puntajes de reglas locales y
muestras pequeñas por columna.

Responde SOLO JSON válido con este formato:
{{
  "tweet_text_column": "... or null",
  "confidence": 0.0,
  "reason": "...",
  "label_column": "... or null",
  "timestamp_column": "... or null",
  "ticker_column": "... or null"
}}

Reglas:
- Elige la columna con el texto completo a clasificar.
- No elijas columnas de etiqueta, id, fecha, usuario, ticker aislado o score.
- Si no hay evidencia suficiente, usa null y confidence menor a 0.5.
- No inventes columnas que no existan.
- No incluyas markdown, explicaciones fuera del JSON ni texto adicional.

Esquema y muestras:
{json.dumps(payload, ensure_ascii=False)}
""".strip()

    raw_text = _invoke_bedrock_text(prompt, model_id=model_id, region_name=region_name)
    parsed = _extract_json_object(raw_text)

    tweet_text_column = parsed.get("tweet_text_column")
    if tweet_text_column in {"", "null", "None"}:
        tweet_text_column = None
    if tweet_text_column is not None and tweet_text_column not in valid_columns:
        raise ValueError(f"Bedrock returned an unknown column: {tweet_text_column}")

    def optional_column(name: str) -> str | None:
        value = parsed.get(name)
        if value in {"", "null", "None", None}:
            return None
        return str(value) if str(value) in valid_columns else None

    return SchemaMapping(
        tweet_text_column=str(tweet_text_column) if tweet_text_column else None,
        confidence=float(parsed.get("confidence", 0.0)),
        method="bedrock",
        reason=str(parsed.get("reason", "Bedrock identificó el esquema.")),
        label_column=optional_column("label_column"),
        timestamp_column=optional_column("timestamp_column"),
        ticker_column=optional_column("ticker_column"),
    )


def infer_schema(
    df: pd.DataFrame,
    *,
    use_bedrock: bool,
    model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    region_name: str = "us-east-1",
) -> SchemaMapping:
    """Infer schema with rules first and optional Bedrock fallback."""

    rule_result = infer_schema_with_rules(df)
    if rule_result.tweet_text_column is not None:
        return rule_result

    if not use_bedrock:
        return rule_result

    try:
        bedrock_result = infer_schema_with_bedrock(
            df,
            model_id=model_id,
            region_name=region_name,
        )
        return SchemaMapping(
            tweet_text_column=bedrock_result.tweet_text_column,
            confidence=bedrock_result.confidence,
            method=bedrock_result.method,
            reason=bedrock_result.reason,
            label_column=bedrock_result.label_column or rule_result.label_column,
            timestamp_column=bedrock_result.timestamp_column or rule_result.timestamp_column,
            ticker_column=bedrock_result.ticker_column or rule_result.ticker_column,
        )
    except Exception as exc:
        logger.exception("bedrock_schema_inference_failed error_type=%s", type(exc).__name__)
        return SchemaMapping(
            tweet_text_column=None,
            confidence=0.0,
            method="bedrock_failed",
            reason=f"Bedrock falló durante inferencia de esquema: {type(exc).__name__}: {exc}",
            label_column=rule_result.label_column,
            timestamp_column=rule_result.timestamp_column,
            ticker_column=rule_result.ticker_column,
        )
