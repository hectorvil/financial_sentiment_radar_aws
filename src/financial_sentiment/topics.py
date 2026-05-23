"""Rule-based topic classification for financial social-media text.

The order matters: specific topics must be evaluated before broad topics.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

TOPIC_KEYWORDS: dict[str, set[str]] = {
    "sovereign_credit_rating": {
        "moody",
        "moody's",
        "moody’s",
        "fitch",
        "s&p",
        "standard & poor",
        "calificacion soberana",
        "calificación soberana",
        "nota soberana",
        "deuda soberana",
        "grado de inversion",
        "grado de inversión",
        "baa3",
        "baa2",
        "bbb",
        "rating soberano",
        "sovereign rating",
        "credit rating",
        "downgrade",
        "upgrade",
    },
    "monetary_policy": {
        "banxico",
        "banco de mexico",
        "banco de méxico",
        "fed",
        "federal reserve",
        "fomc",
        "interest rate",
        "rate cut",
        "rate hike",
        "rates",
        "inflation",
        "cpi",
        "tasa",
        "tasas",
        "tasa de interes",
        "tasa de interés",
        "inflacion",
        "inflación",
        "politica monetaria",
        "política monetaria",
    },
    "fx_rates": {
        "peso",
        "peso mexicano",
        "usd/mxn",
        "usdmxn",
        "tipo de cambio",
        "dolar",
        "dólar",
        "fx",
        "currency",
        "forex",
    },
    "geopolitical_risk": {
        "geopolitics",
        "geopolitical",
        "war",
        "conflict",
        "iran",
        "china",
        "tariff",
        "tariffs",
        "trade war",
        "arancel",
        "aranceles",
        "guerra",
        "conflicto",
        "riesgo geopolitico",
        "riesgo geopolítico",
    },
    "regulation_antitrust": {
        "antitrust",
        "regulation",
        "regulator",
        "regulatory",
        "doj",
        "ftc",
        "sec",
        "lawsuit",
        "court",
        "probe",
        "investigation",
        "regulacion",
        "regulación",
        "regulador",
        "demanda",
        "investigacion",
        "investigación",
        "competencia",
    },
    "commodities_energy": {
        "oil",
        "crude",
        "brent",
        "wti",
        "gas",
        "energy",
        "opec",
        "commodity",
        "commodities",
        "petroleo",
        "petróleo",
        "crudo",
        "energia",
        "energía",
    },
    "credit_risk": {
        "credit risk",
        "default",
        "spread",
        "spreads",
        "debt",
        "bond",
        "bonds",
        "leverage",
        "liquidity",
        "riesgo credito",
        "riesgo de credito",
        "riesgo crediticio",
        "deuda",
        "bonos",
        "liquidez",
    },
    "banking_sector": {
        "bank",
        "banks",
        "banking",
        "loan",
        "loans",
        "deposit",
        "deposits",
        "credit card",
        "mortgage",
        "banco",
        "bancos",
        "banca",
        "credito",
        "crédito",
        "prestamo",
        "préstamo",
        "hipoteca",
    },
    "labor_market": {
        "jobs",
        "payrolls",
        "unemployment",
        "employment",
        "wages",
        "labor market",
        "jobless",
        "empleo",
        "desempleo",
        "salarios",
        "mercado laboral",
    },
    "analyst_rating": {
        "upgrade",
        "downgrade",
        "price target",
        "initiates",
        "reiterates",
        "overweight",
        "underweight",
        "buy rating",
        "sell rating",
        "neutral rating",
        "sube recomendacion",
        "baja recomendacion",
        "precio objetivo",
        "recomendacion",
        "recomendación",
    },
    "earnings": {
        "earnings",
        "results",
        "revenue",
        "profit",
        "guidance",
        "eps",
        "sales",
        "margin",
        "margins",
        "quarter",
        "ventas",
        "ingresos",
        "utilidad",
        "ganancia",
        "resultados",
        "margen",
        "guia",
        "guía",
    },
    "market_action": {
        "buy",
        "sell",
        "short",
        "long",
        "rally",
        "surge",
        "jump",
        "drop",
        "fall",
        "plunge",
        "shares",
        "stock",
        "stocks",
        "market",
        "bullish",
        "bearish",
        "compra",
        "venta",
        "sube",
        "baja",
        "cae",
        "mercado",
        "acciones",
    },
    "ai_chips": {
        "ai",
        "ia",
        "gpu",
        "chips",
        "chip",
        "semiconductor",
        "semiconductors",
        "nvidia",
        "nvda",
        "data center",
        "datacenter",
        "artificial intelligence",
        "inteligencia artificial",
    },
    "product_launch": {
        "iphone",
        "model",
        "launch",
        "app",
        "product",
        "release",
        "unveil",
        "new product",
        "producto",
        "lanzamiento",
        "presenta",
        "presentó",
    },
    "risk_compliance": {
        "fraud",
        "risk",
        "compliance",
        "scandal",
        "fine",
        "penalty",
        "sanction",
        "cyberattack",
        "hack",
        "data breach",
        "fraude",
        "riesgo",
        "cumplimiento",
        "multa",
        "sancion",
        "sanción",
        "ciberataque",
    },
}


TOPIC_ORDER = [
    "sovereign_credit_rating",
    "monetary_policy",
    "fx_rates",
    "geopolitical_risk",
    "regulation_antitrust",
    "commodities_energy",
    "credit_risk",
    "banking_sector",
    "labor_market",
    "analyst_rating",
    "earnings",
    "market_action",
    "ai_chips",
    "product_launch",
    "risk_compliance",
]


def _strip_accents(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )


def _normalize(text: str) -> str:
    return _strip_accents(str(text).lower())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text))


def _matches_keyword(text: str, token_set: set[str], keyword: str) -> bool:
    keyword_norm = _normalize(keyword).strip()
    if not keyword_norm:
        return False

    if " " in keyword_norm or "/" in keyword_norm or "&" in keyword_norm:
        return keyword_norm in text

    return keyword_norm in token_set


def classify_topic(text: str) -> str:
    """Classify one text into a financial topic.

    Specific financial themes are evaluated first. Short tokens like AI or IA
    are matched only as full tokens, not as substrings inside Spanish words.
    """
    normalized = _normalize(text)
    token_set = _tokens(normalized)

    for topic in TOPIC_ORDER:
        keywords = TOPIC_KEYWORDS[topic]
        if any(_matches_keyword(normalized, token_set, keyword) for keyword in keywords):
            return topic

    return "general_market"


def add_topics(df: pd.DataFrame) -> pd.DataFrame:
    """Add a topic column to a dataframe."""
    enriched = df.copy()
    text_col = "clean_text" if "clean_text" in enriched.columns else "text"
    enriched["topic"] = enriched[text_col].fillna("").map(classify_topic)
    return enriched
