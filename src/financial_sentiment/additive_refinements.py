"""Additive query refinements for the final Financial Sentiment Radar phase.

This module is intentionally additive: it does not replace the working ingestion
pipeline. It only adds richer account coverage, extra companies, topic keywords,
and deterministic query refinements that reduce noise before X/Twitter search or
batch-corpus retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from financial_sentiment.query_anchor_filter import build_precise_anchor_query

# Spanish / Mexican finance, economics and market sources.
# Keep handles without @ because X search uses from:<handle>.
EXTRA_SPANISH_MX_ACCOUNTS = [
    "ElFinanciero_Mx",
    "ElFinancieroTv",
    "eleconomista",
    "ExpansionMx",
    "Forbes_Mexico",
    "BloombergLineaM",
    "BloombergLinea_",
    "BMVMercados",
    "Banxico",
    "Hacienda_Mexico",
    "INEGI_INFORMA",
    "ReutersLatam",
]

# High-activity English market, business and investing accounts. These should be
# treated as quality signals, not as the only possible source.
EXTRA_EN_MARKET_ACCOUNTS = [
    "Reuters",
    "ReutersBiz",
    "ReutersMarkets",
    "CNBC",
    "CNBCi",
    "SquawkCNBC",
    "YahooFinance",
    "MarketWatch",
    "WSJmarkets",
    "FTMarkets",
    "Benzinga",
    "Stocktwits",
    "IBDinvestors",
    "bespokeinvest",
    "markets",
    "business",
    "Investingcom",
    "SeekingAlpha",
    "TheStalwart",
    "KobeissiLetter",
    "charliebilello",
    "RyanDetrick",
    "Stephanie_Link",
    "elerianm",
]

EXTRA_CURATED_ACCOUNTS = list(dict.fromkeys(EXTRA_SPANISH_MX_ACCOUNTS + EXTRA_EN_MARKET_ACCOUNTS))

# 15 additional tickers that usually have active investor/media discussion.
ADDITIONAL_COMPANY_QUERIES: dict[str, dict[str, Any]] = {
    "PLTR": {
        "name": "Palantir",
        "aliases": ["PLTR", "$PLTR", "Palantir"],
        "terms_en": [
            "earnings",
            "AI",
            "government contracts",
            "revenue",
            "guidance",
            "stock",
            "shares",
        ],
    },
    "COIN": {
        "name": "Coinbase",
        "aliases": ["COIN", "$COIN", "Coinbase"],
        "terms_en": ["bitcoin", "crypto", "SEC", "trading volume", "earnings", "stock", "shares"],
    },
    "MU": {
        "name": "Micron",
        "aliases": ["MU", "$MU", "Micron"],
        "terms_en": ["memory", "DRAM", "HBM", "AI", "chips", "earnings", "guidance", "stock"],
    },
    "QCOM": {
        "name": "Qualcomm",
        "aliases": ["QCOM", "$QCOM", "Qualcomm"],
        "terms_en": ["chips", "AI", "smartphone", "licensing", "earnings", "stock", "guidance"],
    },
    "CRM": {
        "name": "Salesforce",
        "aliases": ["CRM", "$CRM", "Salesforce"],
        "terms_en": ["cloud", "AI", "software", "earnings", "guidance", "margin", "stock"],
    },
    "UBER": {
        "name": "Uber",
        "aliases": ["UBER", "$UBER", "Uber"],
        "terms_en": ["rideshare", "delivery", "margins", "earnings", "guidance", "stock", "shares"],
    },
    "SHOP": {
        "name": "Shopify",
        "aliases": ["SHOP", "$SHOP", "Shopify"],
        "terms_en": ["ecommerce", "merchant", "earnings", "revenue", "guidance", "stock", "shares"],
    },
    "V": {
        "name": "Visa",
        "aliases": ["V", "$V", "Visa"],
        "terms_en": ["payments", "consumer spending", "earnings", "revenue", "stock", "shares"],
    },
    "MA": {
        "name": "Mastercard",
        "aliases": ["MA", "$MA", "Mastercard"],
        "terms_en": ["payments", "consumer spending", "earnings", "revenue", "stock", "shares"],
    },
    "XOM": {
        "name": "Exxon Mobil",
        "aliases": ["XOM", "$XOM", "Exxon", "Exxon Mobil"],
        "terms_en": ["oil", "energy", "crude", "earnings", "dividend", "stock", "shares"],
    },
    "CVX": {
        "name": "Chevron",
        "aliases": ["CVX", "$CVX", "Chevron"],
        "terms_en": ["oil", "energy", "crude", "earnings", "dividend", "stock", "shares"],
    },
    "LLY": {
        "name": "Eli Lilly",
        "aliases": ["LLY", "$LLY", "Eli Lilly", "Lilly"],
        "terms_en": ["obesity drug", "diabetes", "FDA", "earnings", "guidance", "stock", "shares"],
    },
    "NVO": {
        "name": "Novo Nordisk",
        "aliases": ["NVO", "$NVO", "Novo Nordisk"],
        "terms_en": ["Ozempic", "Wegovy", "obesity drug", "earnings", "stock", "shares"],
    },
    "TSM": {
        "name": "TSMC",
        "aliases": ["TSM", "$TSM", "TSMC", "Taiwan Semiconductor"],
        "terms_en": ["chips", "semiconductor", "AI", "foundry", "earnings", "stock", "shares"],
    },
    "COST": {
        "name": "Costco",
        "aliases": ["COST", "$COST", "Costco"],
        "terms_en": [
            "retail",
            "consumer",
            "same-store sales",
            "earnings",
            "membership",
            "stock",
            "shares",
        ],
    },
}

# Extra topic keyword families. Existing topics remain untouched.
ADDITIONAL_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "monetary_policy": [
        "banxico",
        "fed",
        "rate cut",
        "rate hike",
        "tasa",
        "tasas",
        "política monetaria",
        "interest rate",
        "central bank",
    ],
    "fx_rates": [
        "peso",
        "mxn",
        "usd/mxn",
        "dólar",
        "dollar",
        "exchange rate",
        "tipo de cambio",
        "currency",
    ],
    "geopolitical_risk": [
        "geopolitical",
        "geopolítica",
        "tariffs",
        "arancel",
        "war",
        "conflict",
        "trade tensions",
        "nearshoring",
    ],
    "analyst_rating": [
        "upgrade",
        "downgrade",
        "price target",
        "analyst",
        "rating",
        "overweight",
        "buy rating",
        "sell rating",
    ],
    "regulation_antitrust": [
        "antitrust",
        "regulation",
        "regulatory",
        "probe",
        "lawsuit",
        "fine",
        "SEC",
        "DOJ",
        "Cofece",
    ],
    "commodities_energy": [
        "oil",
        "crude",
        "gas",
        "energy",
        "commodity",
        "commodities",
        "gold",
        "copper",
        "brent",
        "wti",
    ],
}

FINANCIAL_CONTEXT_TERMS_ES = [
    "acciones",
    "bolsa",
    "bmv",
    "mercado",
    "mercados",
    "inversión",
    "inversionistas",
    "tasas",
    "tasa de interés",
    "banxico",
    "inflación",
    "peso",
    "dólar",
    "tipo de cambio",
    "bonos",
    "deuda",
    "riesgo país",
    "nearshoring",
    "utilidad",
    "ingresos",
    "crédito",
    "cartera vencida",
    "margen",
    "resultados",
    "trimestre",
    "banco",
    "financiero",
]

FINANCIAL_CONTEXT_TERMS_EN = [
    "stock",
    "stocks",
    "shares",
    "market",
    "markets",
    "earnings",
    "revenue",
    "guidance",
    "margin",
    "margins",
    "profit",
    "loss",
    "inflation",
    "rates",
    "fed",
    "bonds",
    "yield",
    "fx",
    "currency",
    "commodities",
    "upgrade",
    "downgrade",
    "price target",
    "analyst",
]

QUERY_ENTITY_EXPANSIONS: dict[str, str] = {
    "google": "(GOOGL OR $GOOGL OR Google OR Alphabet) (earnings OR revenue OR cloud OR advertising OR AI OR antitrust OR stock OR shares OR guidance OR profit)",
    "alphabet": "(GOOGL OR $GOOGL OR Google OR Alphabet) (earnings OR revenue OR cloud OR advertising OR AI OR antitrust OR stock OR shares OR guidance OR profit)",
    "bbva": '(BBVA OR $BBVA OR "Banco Bilbao Vizcaya" OR "BBVA México") (resultados OR utilidad OR ingresos OR crédito OR riesgo OR tasas OR acción OR acciones OR México)',
    "mexico": '(México OR Mexico OR Banxico OR peso OR MXN OR "tipo de cambio" OR inflación OR "tasa de interés" OR "política monetaria" OR BMV OR nearshoring) (mercado OR mercados OR finanzas OR inversión OR tasas OR bonos OR acciones OR riesgo)',
    "méxico": '(México OR Mexico OR Banxico OR peso OR MXN OR "tipo de cambio" OR inflación OR "tasa de interés" OR "política monetaria" OR BMV OR nearshoring) (mercado OR mercados OR finanzas OR inversión OR tasas OR bonos OR acciones OR riesgo)',
    "nvidia": '(NVDA OR $NVDA OR Nvidia) (earnings OR guidance OR AI OR chips OR GPU OR "data center" OR stock OR shares OR revenue OR profit OR margin)',
    "tesla": "(TSLA OR $TSLA OR Tesla) (earnings OR deliveries OR EV OR margins OR revenue OR guidance OR stock OR shares)",
}


@dataclass(frozen=True)
class RefinedQuery:
    original: str
    refined: str
    reason: str


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def refine_live_question_for_x(question: str) -> RefinedQuery:
    """Convert broad user questions into finance-aware X search text.

    This is deliberately deterministic and cheap. Bedrock can still be used
    later for relevance/noise labels, but this first pass reduces noise before
    hitting the X API.
    """
    raw = (question or "").strip()
    lowered = raw.lower()
    if not raw:
        return RefinedQuery(raw, raw, "empty query")

    # Si la consulta tiene anclas fuertes, no la conviertas a una macro-query genérica.
    # Ejemplos: Mexico Moody, Google antitrust DOJ, Nvidia earnings, Banxico tasa.
    # La construcción precisa de query se encargará de usar esas anclas sin borrarlas.
    if build_precise_anchor_query(raw, language="auto"):
        return RefinedQuery(raw, raw, "strong_anchors_preserved")

    for key, expansion in QUERY_ENTITY_EXPANSIONS.items():
        if key in lowered:
            return RefinedQuery(raw, expansion, f"expanded entity '{key}' with finance terms")

    if _contains_any(lowered, FINANCIAL_CONTEXT_TERMS_ES + FINANCIAL_CONTEXT_TERMS_EN):
        return RefinedQuery(raw, raw, "already has financial context")

    finance_terms = "(mercado OR mercados OR finanzas OR inversión OR acciones OR tasas OR inflación OR stock OR shares OR earnings OR revenue)"
    return RefinedQuery(raw, f"({raw}) {finance_terms}", "added generic financial context")


def refine_batch_question_for_corpus(question: str) -> RefinedQuery:
    """Refine batch-corpus questions without changing the UI flow."""
    refined = refine_live_question_for_x(question)
    if refined.refined == refined.original:
        return refined
    # For corpus retrieval, boolean syntax is less important than terms, so strip operators.
    corpus_text = re.sub(r'[()"]', " ", refined.refined)
    corpus_text = re.sub(r"\bOR\b", " ", corpus_text, flags=re.IGNORECASE)
    corpus_text = re.sub(r"\s+", " ", corpus_text).strip()
    return RefinedQuery(refined.original, corpus_text, refined.reason)


def extend_catalog_globals(module_globals: dict[str, Any]) -> None:
    """Extend whichever catalog globals exist in the current repository.

    Different patches used slightly different variable names. This function is
    defensive and only extends names that are present, avoiding breaking working
    code.
    """
    account_names = [
        "TRUSTED_FINANCIAL_ACCOUNTS",
        "CURATED_MARKET_ACCOUNTS",
        "CURATED_FINANCIAL_ACCOUNTS",
        "TRUSTED_ACCOUNTS",
    ]
    for name in account_names:
        existing = module_globals.get(name)
        if isinstance(existing, list):
            module_globals[name] = list(dict.fromkeys(existing + EXTRA_CURATED_ACCOUNTS))

    company_names = ["COMPANY_QUERIES", "TICKER_CATALOG", "COMPANIES", "TICKERS"]
    for name in company_names:
        existing = module_globals.get(name)
        if isinstance(existing, dict):
            for ticker, spec in ADDITIONAL_COMPANY_QUERIES.items():
                existing.setdefault(ticker, spec)

    alias_names = ["TICKER_ALIASES", "COMPANY_ALIASES"]
    for name in alias_names:
        existing = module_globals.get(name)
        if isinstance(existing, dict):
            for ticker, spec in ADDITIONAL_COMPANY_QUERIES.items():
                existing.setdefault(ticker, spec.get("aliases", [ticker]))

    topic_names = ["TOPIC_KEYWORDS", "TOPIC_RULES", "TOPIC_PATTERNS"]
    for name in topic_names:
        existing = module_globals.get(name)
        if isinstance(existing, dict):
            for topic, terms in ADDITIONAL_TOPIC_KEYWORDS.items():
                if topic in existing and isinstance(existing[topic], list):
                    existing[topic] = list(dict.fromkeys(existing[topic] + terms))
                else:
                    existing.setdefault(topic, terms)
