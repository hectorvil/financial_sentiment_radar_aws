"""Controlled X/Twitter query catalog for financial live ingestion.

The goal of this module is to reduce noise and control API cost. We do not let
scheduled ingestion search arbitrary user text. Instead, we build queries from a
small catalog of public companies, market terms, and trusted financial accounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

TRUSTED_FINANCIAL_ACCOUNTS: tuple[str, ...] = (
    "Reuters",
    "CNBC",
    "FT",
    "WSJmarkets",
    "MarketWatch",
    "YahooFinance",
    "Investingcom",
    "Benzinga",
)

GLOBAL_MARKET_TERMS_EN: tuple[str, ...] = (
    "earnings",
    "revenue",
    "guidance",
    "profit",
    "loss",
    "margin",
    "margins",
    "stock",
    "shares",
    "market",
    "downgrade",
    "upgrade",
    "rates",
    "inflation",
    "AI",
    "cloud",
)

GLOBAL_MARKET_TERMS_ES: tuple[str, ...] = (
    "resultados",
    "utilidad",
    "ingresos",
    "ganancia",
    "pérdida",
    "margen",
    "acción",
    "acciones",
    "mercado",
    "riesgo",
    "tasas",
    "inflación",
)


@dataclass(frozen=True)
class CompanyLiveQuery:
    """Live query metadata for one tracked company."""

    ticker: str
    name: str
    aliases: tuple[str, ...]
    terms_en: tuple[str, ...]
    terms_es: tuple[str, ...] = ()


COMPANY_QUERIES: dict[str, CompanyLiveQuery] = {
    "NVDA": CompanyLiveQuery(
        ticker="NVDA",
        name="Nvidia",
        aliases=("NVDA", "$NVDA", "Nvidia"),
        terms_en=("earnings", "guidance", "AI", "chips", "GPU", "data center", "stock", "shares"),
    ),
    "TSLA": CompanyLiveQuery(
        ticker="TSLA",
        name="Tesla",
        aliases=("TSLA", "$TSLA", "Tesla"),
        terms_en=("earnings", "deliveries", "EV demand", "margins", "guidance", "stock", "shares"),
    ),
    "GOOGL": CompanyLiveQuery(
        ticker="GOOGL",
        name="Alphabet / Google",
        aliases=("GOOGL", "$GOOGL", "Google", "Alphabet"),
        terms_en=(
            "earnings",
            "revenue",
            "cloud",
            "advertising",
            "AI",
            "antitrust",
            "stock",
            "shares",
        ),
    ),
    "AAPL": CompanyLiveQuery(
        ticker="AAPL",
        name="Apple",
        aliases=("AAPL", "$AAPL", "Apple"),
        terms_en=(
            "earnings",
            "revenue",
            "iPhone",
            "services",
            "China",
            "margins",
            "stock",
            "shares",
        ),
    ),
    "MSFT": CompanyLiveQuery(
        ticker="MSFT",
        name="Microsoft",
        aliases=("MSFT", "$MSFT", "Microsoft"),
        terms_en=("earnings", "revenue", "Azure", "AI", "Copilot", "cloud", "stock", "shares"),
    ),
    "AMZN": CompanyLiveQuery(
        ticker="AMZN",
        name="Amazon",
        aliases=("AMZN", "$AMZN", "Amazon", "AWS"),
        terms_en=("earnings", "revenue", "AWS", "cloud", "retail", "margins", "stock", "shares"),
    ),
    "JPM": CompanyLiveQuery(
        ticker="JPM",
        name="JPMorgan",
        aliases=("JPM", "$JPM", "JPMorgan", "JP Morgan"),
        terms_en=(
            "earnings",
            "rates",
            "credit risk",
            "loan losses",
            "trading revenue",
            "stock",
            "shares",
        ),
    ),
    "BBVA": CompanyLiveQuery(
        ticker="BBVA",
        name="BBVA",
        aliases=("BBVA", "$BBVA", "Banco Bilbao Vizcaya"),
        terms_en=(
            "earnings",
            "revenue",
            "profit",
            "credit",
            "risk",
            "Mexico",
            "rates",
            "stock",
            "shares",
        ),
        terms_es=(
            "resultados",
            "utilidad",
            "ingresos",
            "crédito",
            "riesgo",
            "tasas",
            "acción",
            "acciones",
            "México",
        ),
    ),
}


def _quote_if_needed(term: str) -> str:
    """Quote terms that contain spaces so X search treats them as phrases."""
    return f'"{term}"' if " " in term else term


def build_account_filter(accounts: tuple[str, ...] = TRUSTED_FINANCIAL_ACCOUNTS) -> str:
    """Build an X query filter restricted to trusted financial accounts."""
    return "(" + " OR ".join(f"from:{account}" for account in accounts) + ")"


def build_company_query(
    ticker: str,
    *,
    language: str = "en",
    trusted_accounts_only: bool = True,
) -> str:
    """Build a controlled recent-search query for a tracked company.

    Args:
        ticker: Company ticker from COMPANY_QUERIES.
        language: ``en`` or ``es``. Spanish is mainly supported for BBVA.
        trusted_accounts_only: If true, restricts results to selected financial accounts.

    Returns:
        X API recent-search query string.
    """
    normalized = ticker.upper().strip()
    if normalized not in COMPANY_QUERIES:
        raise KeyError(f"Ticker not configured for live ingestion: {ticker}")

    company = COMPANY_QUERIES[normalized]
    aliases = "(" + " OR ".join(_quote_if_needed(alias) for alias in company.aliases) + ")"

    if language == "es" and company.terms_es:
        terms = company.terms_es + GLOBAL_MARKET_TERMS_ES
        lang_filter = "lang:es"
    else:
        terms = company.terms_en + GLOBAL_MARKET_TERMS_EN
        lang_filter = "lang:en"

    unique_terms = tuple(dict.fromkeys(terms))
    term_filter = "(" + " OR ".join(_quote_if_needed(term) for term in unique_terms) + ")"
    base_query = f"{aliases} {term_filter} {lang_filter} -is:retweet"

    if trusted_accounts_only:
        return f"{build_account_filter()} {base_query}"

    return base_query


def rotate_ticker(tickers: list[str], now: datetime | None = None) -> str:
    """Select one ticker for the current two-hour window.

    This keeps the scheduled job at exactly one query per run and 10 posts max.
    With the default 8 tickers and a two-hour schedule, every ticker is covered
    over a rolling 16-hour window.
    """
    if not tickers:
        raise ValueError("At least one ticker is required for rotation.")

    current = now or datetime.now(UTC)
    window_index = int(current.timestamp() // (2 * 60 * 60))
    return tickers[window_index % len(tickers)].upper().strip()
