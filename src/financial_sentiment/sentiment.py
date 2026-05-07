"""Lightweight financial sentiment scoring.

This module provides an interpretable baseline that does not need GPU, Colab or
large transformer downloads. It is appropriate for a proof of concept and can be
replaced later by FinBERT, Amazon Comprehend, or a Bedrock classification prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

TOKEN_PATTERN = re.compile(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]+")

POSITIVE_TERMS = {
    "beat",
    "beats",
    "bullish",
    "buy",
    "gain",
    "gains",
    "growth",
    "high",
    "higher",
    "long",
    "outperform",
    "profit",
    "profits",
    "rally",
    "record",
    "recovery",
    "upgrade",
    "upside",
    "strong",
    "positivo",
    "sube",
    "alza",
    "crecimiento",
    "ganancia",
    "ganancias",
    "mejora",
    "récord",
}

NEGATIVE_TERMS = {
    "bearish",
    "bubble",
    "crash",
    "cut",
    "cuts",
    "debt",
    "decline",
    "downgrade",
    "drop",
    "falls",
    "fear",
    "fraud",
    "loss",
    "losses",
    "miss",
    "risk",
    "sell",
    "short",
    "slowdown",
    "volatility",
    "warning",
    "negativo",
    "baja",
    "cae",
    "caída",
    "deuda",
    "pérdida",
    "pérdidas",
    "riesgo",
    "vende",
    "volatilidad",
}

NEGATIONS = {"not", "no", "never", "nunca", "sin"}


@dataclass(frozen=True)
class SentimentResult:
    """Result from the sentiment scorer."""

    sentiment: str
    sentiment_score: float
    positive_hits: int
    negative_hits: int


def _tokens(text: str) -> list[str]:
    """Tokenize text into lowercase words."""

    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def score_sentiment(text: str) -> SentimentResult:
    """Score the sentiment of a financial text.

    Parameters
    ----------
    text:
        Cleaned tweet text.

    Returns
    -------
    SentimentResult
        Sentiment label, score and interpretable hit counts.
    """

    tokens = _tokens(text)
    if not tokens:
        return SentimentResult("neutral", 0.0, 0, 0)

    positive_hits = 0
    negative_hits = 0
    negate_next = False

    for token in tokens:
        if token in NEGATIONS:
            negate_next = True
            continue

        is_positive = token in POSITIVE_TERMS
        is_negative = token in NEGATIVE_TERMS

        if negate_next:
            is_positive, is_negative = is_negative, is_positive
            negate_next = False

        positive_hits += int(is_positive)
        negative_hits += int(is_negative)

    score = (positive_hits - negative_hits) / max(len(tokens) ** 0.5, 1.0)
    if score >= 0.25:
        label = "positive"
    elif score <= -0.25:
        label = "negative"
    else:
        label = "neutral"

    return SentimentResult(label, round(float(score), 4), positive_hits, negative_hits)


def add_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    """Add sentiment columns to a prepared tweet dataframe.

    Parameters
    ----------
    df:
        Dataframe with ``clean_text`` column.

    Returns
    -------
    pandas.DataFrame
        Dataframe enriched with sentiment columns.
    """

    if "clean_text" not in df.columns:
        raise ValueError("Dataframe must include a 'clean_text' column.")

    scored = df.copy()
    results = scored["clean_text"].map(score_sentiment)
    scored["sentiment"] = results.map(lambda item: item.sentiment)
    scored["sentiment_score"] = results.map(lambda item: item.sentiment_score)
    scored["positive_hits"] = results.map(lambda item: item.positive_hits)
    scored["negative_hits"] = results.map(lambda item: item.negative_hits)
    return scored
