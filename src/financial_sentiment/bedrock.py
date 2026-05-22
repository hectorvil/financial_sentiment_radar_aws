"""Optional Amazon Bedrock summarization for retrieved evidence.

This module is intentionally small and defensive. If the configured Bedrock
model is unavailable or disabled, the Streamlit app still falls back to the
local extractive answer. The functions here only build a grounded prompt and
send the correct request shape for Titan or Claude-style models.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

import boto3

from .retrieval import SearchResult

logger = logging.getLogger(__name__)


def build_prompt(query: str, results: Iterable[SearchResult]) -> str:
    """Build a grounded Spanish prompt from retrieved evidence."""
    evidence_items = []
    for idx, item in enumerate(results, start=1):
        evidence_items.append(
            f"[{idx}] sentiment={item.sentiment} tickers={item.tickers} "
            f"topic={item.topic} text={item.text[:700]}"
        )
    evidence = "\n".join(evidence_items)
    return f"""
Eres un analista financiero dentro de un producto de datos.
Responde en español y usa únicamente la evidencia proporcionada.
No des recomendaciones de compra o venta. No inventes información externa.

Pregunta del usuario:
{query}

Evidencia recuperada:
{evidence}

Entrega:
1. Resumen ejecutivo en 3 bullets.
2. Sentimiento predominante y matices.
3. Evidencia citada por número [1], [2], etc.
""".strip()


def _invoke_titan(client, model_id: str, prompt: str) -> str:
    """Invoke Amazon Titan Text-style models."""
    body = {
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 700,
            "temperature": 0.2,
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
    return payload.get("results", [{}])[0].get("outputText", "").strip()


def _invoke_claude(client, model_id: str, prompt: str) -> str:
    """Invoke Anthropic Claude-style models through Bedrock."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 900,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
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
    return json.dumps(payload, ensure_ascii=False)[:1500]


def summarize_with_bedrock(
    query: str,
    results: list[SearchResult],
    *,
    model_id: str,
    region_name: str,
) -> str:
    """Summarize retrieved evidence with Amazon Bedrock."""
    if not results:
        return "No encontré evidencia suficiente en el corpus cargado para responder esa pregunta."

    prompt = build_prompt(query, results)
    client = boto3.client("bedrock-runtime", region_name=region_name)

    try:
        if model_id.startswith("amazon.titan"):
            return _invoke_titan(client, model_id, prompt)
        if "anthropic.claude" in model_id:
            return _invoke_claude(client, model_id, prompt)
        logger.warning("Unsupported Bedrock model_id=%s; trying Claude-style request", model_id)
        return _invoke_claude(client, model_id, prompt)
    except Exception as exc:
        logger.exception(
            "bedrock_summary_failed model_id=%s error_type=%s", model_id, type(exc).__name__
        )
        raise
