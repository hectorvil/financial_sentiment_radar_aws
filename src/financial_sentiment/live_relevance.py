"""Bedrock-assisted relevance filtering and Spanish summaries for live tweets.

The goal is to let the app search the broader X conversation while still
protecting the product from noisy or non-financial posts. Bedrock is used only
on the small batch returned by the user query, capped at 25 tweets.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import boto3
import pandas as pd

logger = logging.getLogger(__name__)

FINANCIAL_TERMS = {
    "stock",
    "shares",
    "earnings",
    "revenue",
    "guidance",
    "profit",
    "loss",
    "margin",
    "margins",
    "market",
    "upgrade",
    "downgrade",
    "rates",
    "inflation",
    "ai",
    "cloud",
    "chips",
    "risk",
    "analyst",
    "price target",
    "central bank",
    "geopolitics",
    "tariffs",
    "banxico",
    "fed",
    "mexico",
    "acción",
    "acciones",
    "mercado",
    "ingresos",
    "utilidad",
    "riesgo",
    "tasas",
    "tasa de interés",
    "banco central",
    "méxico",
    "geopolítica",
    "aranceles",
}

STRONG_MARKET_TERMS = {
    "banxico",
    "fed",
    "fomc",
    "inflation",
    "inflación",
    "interest rates",
    "tasa de interés",
    "tasas",
    "peso",
    "yield",
    "treasury",
    "earnings",
    "guidance",
    "revenue",
    "shares",
    "stock",
    "acciones",
    "bolsa",
    "mercado",
    "bonds",
    "bonos",
    "fx",
    "dollar",
    "dólar",
    "oil",
    "crude",
    "commodities",
}

POLITICAL_SOCIAL_NOISE_TERMS = {
    "peso pluma",
    "infiel",
    "basura criminal",
    "morena narc",
    "novia",
    "farándula",
    "crime",
    "murder",
    "shooting",
    "election campaign",
    "party politics",
    "celebrity",
    "sports",
    "football",
    "music",
    "movie",
    "viral",
    "meme",
    "narco",
    "violencia",
    "asesinato",
    "partido político",
    "campaña",
    "fútbol",
    "deporte",
    "famoso",
}

NOISE_TERMS = {
    "peso pluma",
    "infiel",
    "basura criminal",
    "morena narc",
    "novia",
    "farándula",
    "giveaway",
    "airdrop",
    "casino",
    "betting",
    "onlyfans",
    "promo code",
    "free crypto",
    "dm me",
    "follow back",
}


@dataclass(frozen=True)
class RelevanceLabel:
    """Relevance/noise label for a single tweet."""

    tweet_id: str
    is_noise: bool
    relevance_score: float
    reason: str


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    """Extract a JSON array from an LLM response."""
    stripped = text.strip()
    if stripped.startswith("["):
        return json.loads(stripped)

    match = re.search(r"\[[\s\S]*\]", stripped)
    if not match:
        raise ValueError("Bedrock response did not contain a JSON array")
    return json.loads(match.group(0))


def _invoke_bedrock_text(client: Any, model_id: str, prompt: str, *, max_tokens: int = 1200) -> str:
    """Invoke Bedrock and return text for Claude or Titan style models."""
    if "anthropic.claude" in model_id:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        raw = json.loads(response["body"].read())
        content = raw.get("content", [])
        if content and isinstance(content[0], dict):
            return str(content[0].get("text", "")).strip()
        return json.dumps(raw, ensure_ascii=False)

    body = {
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": max_tokens,
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
    raw = json.loads(response["body"].read())
    return raw.get("results", [{}])[0].get("outputText", "").strip()


def fallback_relevance_labels(
    rows: list[dict[str, Any]], *, user_query: str
) -> list[RelevanceLabel]:
    """Heuristic fallback if Bedrock is disabled or unavailable."""
    query_terms = {token.lower() for token in re.findall(r"[A-Za-z0-9$]+", user_query)}
    labels: list[RelevanceLabel] = []

    for row in rows:
        tweet_id = str(row.get("tweet_id") or row.get("id") or "")
        text = str(row.get("text") or "")
        lowered = text.lower()

        has_finance = any(term in lowered for term in FINANCIAL_TERMS)
        has_strong_market_context = any(term in lowered for term in STRONG_MARKET_TERMS)
        has_query = any(term and term.lower().replace("$", "") in lowered for term in query_terms)
        has_noise = any(term in lowered for term in NOISE_TERMS)
        has_social_political_noise = any(term in lowered for term in POLITICAL_SOCIAL_NOISE_TERMS)
        too_short = len(lowered.split()) < 5
        is_curated_author = bool(row.get("is_curated_market_author"))
        author_tier = str(row.get("author_reliability_tier") or "unknown")

        # A curated author helps, but content still needs market/macro context.
        market_context = has_strong_market_context or (has_finance and has_query)
        is_noise = has_noise or too_short or not market_context
        if has_social_political_noise and not has_strong_market_context:
            is_noise = True

        if is_noise:
            relevance_score = 0.10 if has_social_political_noise else 0.20
            reason = "heuristic_noise_no_market_context"
        elif is_curated_author:
            relevance_score = 0.92
            reason = f"heuristic_curated_author_{author_tier}_market_context"
        else:
            relevance_score = 0.85 if has_finance and has_query else 0.70
            reason = "heuristic_financial_or_macro_relevance"
        labels.append(
            RelevanceLabel(
                tweet_id=tweet_id,
                is_noise=is_noise,
                relevance_score=relevance_score,
                reason=reason,
            )
        )

    return labels


def label_tweets_with_bedrock(
    rows: list[dict[str, Any]],
    *,
    user_query: str,
    model_id: str,
    region_name: str,
) -> list[RelevanceLabel]:
    """Use Bedrock to identify noise in a small live tweet batch."""
    compact_rows = []
    for row in rows[:25]:
        compact_rows.append(
            {
                "tweet_id": str(row.get("tweet_id") or row.get("id") or ""),
                "author": row.get("author_username") or row.get("author_name"),
                "text": str(row.get("text") or "")[:500],
                "author_reliability_tier": row.get("author_reliability_tier"),
                "is_curated_market_author": row.get("is_curated_market_author"),
                "metrics": {
                    "likes": row.get("like_count"),
                    "retweets": row.get("retweet_count"),
                    "replies": row.get("reply_count"),
                },
            }
        )

    prompt = f"""
Eres un analista financiero. Debes clasificar si cada tweet es ruido o si es relevante para entender el mercado, la acción, resultados, riesgos, tasas de interés, inflación, política monetaria, geopolítica o sentimiento financiero de la empresa/tema consultado.

Consulta del usuario: {user_query}

Reglas:
- Marca is_noise=true si el tweet es spam, meme, promoción, giveaway, conversación personal, social/político sin canal de mercado, no financiero o no relacionado.
- Marca is_noise=false solo si hay canal financiero explícito: acción, mercado, resultados, ingresos, guidance, analistas, riesgo, regulación, producto relevante para ingresos, tasas, inflación, bancos centrales, México/Banxico, peso, bonos, FX, petróleo, geopolítica con impacto de mercado, márgenes o sentimiento de inversionistas.
- Si el autor pertenece a una fuente financiera, institucional, research o trader/influencer curado, úsalo como señal positiva, pero NO como garantía: si el contenido no tiene canal financiero, marca ruido.
- No inventes tweet_id.
- Responde SOLO un JSON array válido.
- Cada objeto debe tener: tweet_id, is_noise, relevance_score entre 0 y 1, reason breve en español.

Tweets:
{json.dumps(compact_rows, ensure_ascii=False)}
""".strip()

    client = boto3.client("bedrock-runtime", region_name=region_name)
    output_text = _invoke_bedrock_text(client, model_id, prompt, max_tokens=1200)
    parsed = _extract_json_array(output_text)

    labels: list[RelevanceLabel] = []
    for item in parsed:
        labels.append(
            RelevanceLabel(
                tweet_id=str(item.get("tweet_id", "")),
                is_noise=bool(item.get("is_noise", True)),
                relevance_score=float(item.get("relevance_score", 0.0)),
                reason=str(item.get("reason", "bedrock"))[:300],
            )
        )
    return labels


def get_relevance_labels(
    rows: list[dict[str, Any]],
    *,
    user_query: str,
    use_bedrock: bool,
    model_id: str,
    region_name: str,
) -> list[RelevanceLabel]:
    """Get Bedrock labels with a safe heuristic fallback."""
    if not rows:
        return []

    if use_bedrock:
        try:
            return label_tweets_with_bedrock(
                rows,
                user_query=user_query,
                model_id=model_id,
                region_name=region_name,
            )
        except Exception as exc:  # pragma: no cover - network/Bedrock fallback
            logger.exception("bedrock_relevance_failed error_type=%s", type(exc).__name__)

    return fallback_relevance_labels(rows, user_query=user_query)


def apply_relevance_labels(df: pd.DataFrame, labels: list[RelevanceLabel]) -> pd.DataFrame:
    """Attach relevance labels to a dataframe of live tweets."""
    output = df.copy()
    label_map = {label.tweet_id: label for label in labels}

    def _get_label(row: pd.Series) -> RelevanceLabel:
        tweet_id = str(row.get("tweet_id") or "")
        return label_map.get(
            tweet_id,
            RelevanceLabel(
                tweet_id=tweet_id, is_noise=True, relevance_score=0.0, reason="unlabeled"
            ),
        )

    assigned = output.apply(_get_label, axis=1)
    output["is_noise"] = [label.is_noise for label in assigned]
    output["relevance_score"] = [label.relevance_score for label in assigned]
    output["noise_reason"] = [label.reason for label in assigned]
    return output


def summarize_live_tweets_fallback(df: pd.DataFrame, *, user_query: str) -> str:
    """Build a Spanish summary without Bedrock."""
    if df.empty:
        return "No encontré tweets relevantes suficientes para resumir la consulta."

    counts = df["sentiment"].value_counts().to_dict() if "sentiment" in df.columns else {}
    dominant = max(counts, key=counts.get) if counts else "neutral"
    ticker = df.get("primary_ticker", pd.Series([None])).dropna().astype(str).head(1).tolist()
    ticker_text = ticker[0] if ticker else user_query

    examples = df.get("text", pd.Series(dtype="object")).dropna().astype(str).head(3).tolist()
    bullets = "\n".join(f"- {example[:220]}" for example in examples)

    return (
        f"Para **{ticker_text}**, los tweets relevantes recuperados muestran un tono dominante "
        f"**{dominant}**. Conteo por sentimiento: {counts}.\n\n"
        f"Evidencia principal:\n{bullets}"
    )


def summarize_live_tweets_with_bedrock(
    df: pd.DataFrame,
    *,
    user_query: str,
    model_id: str,
    region_name: str,
) -> str:
    """Summarize non-noise live tweets in Spanish with Bedrock."""
    if df.empty:
        return "No encontré tweets relevantes suficientes para resumir la consulta."

    evidence = []
    for _, row in df.head(20).iterrows():
        evidence.append(
            {
                "ticker": row.get("primary_ticker") or row.get("query_ticker"),
                "sentiment": row.get("sentiment"),
                "confidence": row.get("sentiment_confidence"),
                "topic": row.get("topic"),
                "text": str(row.get("text") or "")[:400],
            }
        )

    sentiment_counts = df["sentiment"].value_counts(dropna=False).to_dict()
    prompt = f"""
Eres un analista financiero. Resume en español qué dicen los tweets relevantes sobre la consulta del usuario.

Consulta: {user_query}

Conteo por sentimiento basado en FinBERT/reglas del pipeline:
{json.dumps(sentiment_counts, ensure_ascii=False)}

Evidencia de tweets no marcados como ruido:
{json.dumps(evidence, ensure_ascii=False)}

Instrucciones:
- Responde en español.
- No des recomendaciones de compra o venta.
- No inventes datos que no estén en la evidencia.
- Explica si predominan menciones positivas, negativas o neutras.
- Menciona 2-4 razones o temas observados; si la consulta es macro/geopolítica, explica el canal de mercado observado en la evidencia.
""".strip()

    client = boto3.client("bedrock-runtime", region_name=region_name)
    return _invoke_bedrock_text(client, model_id, prompt, max_tokens=900)


def summarize_live_tweets(
    df: pd.DataFrame,
    *,
    user_query: str,
    use_bedrock: bool,
    model_id: str,
    region_name: str,
) -> str:
    """Summarize live tweets using Bedrock with local fallback."""
    if use_bedrock:
        try:
            return summarize_live_tweets_with_bedrock(
                df,
                user_query=user_query,
                model_id=model_id,
                region_name=region_name,
            )
        except Exception as exc:  # pragma: no cover - network/Bedrock fallback
            logger.exception("bedrock_live_summary_failed error_type=%s", type(exc).__name__)
    return summarize_live_tweets_fallback(df, user_query=user_query)
