from __future__ import annotations

import pandas as pd

SOVEREIGN_RATING_TERMS = [
    "moody",
    "moody's",
    "moody’s",
    "fitch",
    "s&p",
    "standard & poor",
    "calificación",
    "calificacion",
    "calificación crediticia",
    "calificacion crediticia",
    "nota soberana",
    "deuda soberana",
    "grado de inversión",
    "grado de inversion",
    "baa3",
    "baa2",
    "bbb",
    "perspectiva negativa",
    "riesgo país",
    "riesgo pais",
]

NEGATIVE_RATING_TERMS = [
    "recorta",
    "recortó",
    "rebaja",
    "rebajó",
    "baja",
    "bajó",
    "downgrade",
    "degrada",
    "degradó",
    "negativa",
    "deterioro",
    "menor calificación",
    "menor calificacion",
    "nivel más bajo",
    "nivel mas bajo",
    "pierde",
    "riesgo",
]

POSITIVE_RATING_TERMS = [
    "mejora",
    "mejoró",
    "sube",
    "subió",
    "upgrade",
    "eleva",
    "elevó",
    "perspectiva estable",
    "estable",
]

MACRO_MEXICO_TERMS = [
    "banxico",
    "banco de méxico",
    "banco de mexico",
    "tasa de interés",
    "tasa de interes",
    "tasas",
    "inflación",
    "inflacion",
    "peso mexicano",
    "tipo de cambio",
    "política monetaria",
    "politica monetaria",
]


def _contains_any(text: str, terms: list[str]) -> bool:
    normalized = str(text).lower()
    return any(term in normalized for term in terms)


def _safe_text(row: pd.Series) -> str:
    pieces = []
    for col in ["text", "clean_text", "title", "summary"]:
        if col in row and pd.notna(row[col]):
            pieces.append(str(row[col]))
    return " ".join(pieces)


def _confidence_value(value: object, floor: float) -> float:
    try:
        current = float(value or 0)
    except (TypeError, ValueError):
        current = 0.0
    return max(current, floor)


def apply_spanish_financial_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """Correct obvious Spanish financial/rating cases after FinBERT/topic rules.

    FinBERT sigue siendo el clasificador principal. Esta función solo corrige casos
    muy claros en español, por ejemplo:
    - Moody's recorta calificación de México -> sovereign_credit_rating / negative
    - Banxico/tasas/inflación -> monetary_policy
    """
    if df.empty:
        return df

    out = df.copy()

    for idx, row in out.iterrows():
        text = _safe_text(row)

        is_rating = _contains_any(text, SOVEREIGN_RATING_TERMS)
        is_macro_mx = _contains_any(text, MACRO_MEXICO_TERMS)

        if is_rating:
            out.at[idx, "topic"] = "sovereign_credit_rating"

            if _contains_any(text, NEGATIVE_RATING_TERMS):
                out.at[idx, "sentiment"] = "negative"
                out.at[idx, "sentiment_confidence"] = _confidence_value(
                    row.get("sentiment_confidence", 0),
                    0.88,
                )
            elif _contains_any(text, POSITIVE_RATING_TERMS):
                out.at[idx, "sentiment"] = "positive"
                out.at[idx, "sentiment_confidence"] = _confidence_value(
                    row.get("sentiment_confidence", 0),
                    0.75,
                )
            else:
                out.at[idx, "sentiment"] = "neutral"
                out.at[idx, "sentiment_confidence"] = _confidence_value(
                    row.get("sentiment_confidence", 0),
                    0.70,
                )

        elif is_macro_mx:
            current_topic = str(row.get("topic", "") or "").strip()
            if current_topic in {"", "general_market", "ai_chips"}:
                out.at[idx, "topic"] = "monetary_policy"

    return out
