"""Rule-based topic classification for a compact MVP."""

from __future__ import annotations

import pandas as pd

TOPIC_KEYWORDS: dict[str, set[str]] = {
    "earnings": {"earnings", "results", "revenue", "profit", "guidance", "ventas", "ingresos"},
    "macro_rates": {"fed", "rates", "inflation", "cpi", "banxico", "tasas", "inflación"},
    "ai_chips": {"ai", "gpu", "chips", "semiconductor", "nvidia", "ia"},
    "product_launch": {"iphone", "model", "launch", "app", "producto", "lanzamiento"},
    "risk_compliance": {"fraud", "lawsuit", "regulator", "risk", "fraude", "demanda", "riesgo"},
    "market_action": {"buy", "sell", "short", "long", "rally", "upgrade", "downgrade"},
}


def classify_topic(text: str) -> str:
    """Classify one text into a coarse business topic.

    Parameters
    ----------
    text:
        Cleaned text.

    Returns
    -------
    str
        Topic name.
    """

    lower_text = text.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            return topic
    return "general_market"


def add_topics(df: pd.DataFrame) -> pd.DataFrame:
    """Add a topic column to a dataframe."""

    enriched = df.copy()
    enriched["topic"] = enriched["clean_text"].map(classify_topic)
    return enriched
