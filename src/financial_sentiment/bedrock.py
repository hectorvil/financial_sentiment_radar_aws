"""Optional Amazon Bedrock summarization for retrieved evidence."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

import boto3

from .retrieval import SearchResult

logger = logging.getLogger(__name__)


def build_prompt(query: str, results: Iterable[SearchResult]) -> str:
    """Build a grounded Spanish prompt from retrieved evidence."""

    evidence = "\n".join(
        f"[{idx}] sentiment={item.sentiment} tickers={item.tickers} topic={item.topic} text={item.text}"
        for idx, item in enumerate(results, start=1)
    )
    return f"""
Eres un analista de producto de datos para un equipo financiero.
Responde en español y usa únicamente la evidencia proporcionada.
No des recomendaciones de compra/venta; explica percepción, riesgos y señales.

Pregunta del usuario:
{query}

Evidencia recuperada:
{evidence}

Entrega:
1. Resumen ejecutivo en 3 bullets.
2. Sentimiento predominante y matices.
3. Evidencia citada por número [1], [2], etc.
""".strip()


def summarize_with_bedrock(
    query: str,
    results: list[SearchResult],
    *,
    model_id: str,
    region_name: str,
) -> str:
    """Summarize retrieved evidence with Amazon Bedrock.

    Parameters
    ----------
    query:
        User question.
    results:
        Retrieved evidence.
    model_id:
        Bedrock model id. Supports Amazon Titan Text and Anthropic Claude style
        request bodies.
    region_name:
        AWS region.

    Returns
    -------
    str
        Model-generated grounded summary.
    """

    if not results:
        return "No encontré evidencia suficiente en el corpus cargado para responder esa pregunta."

    prompt = build_prompt(query, results)
    client = boto3.client("bedrock-runtime", region_name=region_name)

    if model_id.startswith("amazon.titan"):
        body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 500,
                "temperature": 0.2,
                "topP": 0.9,
            },
        }
        response = client.invoke_model(modelId=model_id, body=json.dumps(body))
        payload = json.loads(response["body"].read())
        return payload["results"][0]["outputText"].strip()

    if "anthropic.claude" in model_id:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 700,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = client.invoke_model(modelId=model_id, body=json.dumps(body))
        payload = json.loads(response["body"].read())
        return payload["content"][0]["text"].strip()

    logger.warning("Unsupported Bedrock model_id=%s; falling back to Titan body", model_id)
    body = {"inputText": prompt, "textGenerationConfig": {"maxTokenCount": 500, "temperature": 0.2}}
    response = client.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(response["body"].read())
    return json.dumps(payload, ensure_ascii=False)[:1500]
