"""X/Twitter query catalog for broad but high-signal financial live search.

This module builds compact X API recent-search queries from natural-language
questions. The search lives in the **Consultas** tab, while the **Tweets live**
tab only visualizes tweets already ingested into S3.

Design goals:
- Search broadly enough to capture current market conversation.
- Avoid over-restrictive exact-sentence queries that return zero tweets.
- Use curated media, institutional, research, trader and influencer accounts as
  reliability signals, not as the only data source.
- Keep recent-search queries below X's 512-character query length limit.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

AuthorTier = Literal[
    "institution",
    "financial_media",
    "market_research",
    "trader_influencer",
    "mexico_latam",
    "high_noise_watchlist",
    "unknown",
]

INSTITUTIONAL_ACCOUNTS: tuple[str, ...] = (
    "federalreserve",
    "NewYorkFed",
    "ChicagoFed",
    "USTreasury",
    "Banxico",
    "Hacienda_Mexico",
    "ecb",
    "bankofengland",
    "BIS_org",
    "IMFNews",
    "FMInoticias",
    "WorldBank",
    "INEGI_INFORMA",
)

GLOBAL_FINANCIAL_MEDIA_ACCOUNTS: tuple[str, ...] = (
    "Reuters",
    "ReutersBiz",
    "ReutersMarkets",
    "business",
    "markets",
    "CNBC",
    "CNBCi",
    "SquawkCNBC",
    "FT",
    "FTMarkets",
    "FTAlphaville",
    "ftfinancenews",
    "WSJ",
    "WSJmarkets",
    "WSJbusiness",
    "MarketWatch",
    "YahooFinance",
    "Investingcom",
    "Benzinga",
    "Stocktwits",
    "IBDinvestors",
    "nytimesbusiness",
)

MEXICO_LATAM_FINANCIAL_ACCOUNTS: tuple[str, ...] = (
    "ElFinanciero_Mx",
    "ExpansionMx",
    "ExpEconomia",
    "BloombergLinea_",
    "eleconomista",
    "ElEconomistaMx",
    "Reforma",
    "BMVMercados",
    "GBMplus",
)

MARKET_RESEARCH_ACCOUNTS: tuple[str, ...] = (
    "bespokeinvest",
    "BreakoutStocks",
    "KoyfinCharts",
    "SoberLook",
    "KobeissiLetter",
    "DataArbor",
    "MacroMicroMe",
)

TRADER_INFLUENCER_ACCOUNTS: tuple[str, ...] = (
    # Macro strategists / economists / professional market commentators
    "LizAnnSonders",
    "elerianm",
    "TheStalwart",
    "callieabost",
    "Stephanie_Link",
    "TimmerFidelity",
    "NickTimiraos",
    "KathyJones",
    "biancoresearch",
    "fundstrat",
    "lynaldencapital",
    # Market research / high-signal commentary
    "bespokeinvest",
    "KobeissiLetter",
    "DeItaone",
    "MktOutPerform",
    "charliebilello",
    "hmeisler",
    "RyanDetrick",
    "ReformedBroker",
    "ritholtz",
    "awealthofcs",
    "morganhousel",
    # Trading, technical analysis and flow-oriented accounts
    "PeterLBrandt",
    "markminervini",
    "LindaRaschke",
    "CarterBWorth",
    "basso_tom",
    "howardlindzon",
    "Chartfest1",
    "steenbab",
    "OptionsHawk",
    "NorthmanTrader",
    "GuyAdami",
    "RampCapitalLLC",
    "unusual_whales",
    "Stocktwits",
    "IBDinvestors",
    "BreakoutStocks",
)

CURATED_MARKET_ACCOUNT_UNIVERSE: tuple[str, ...] = tuple(
    dict.fromkeys(
        GLOBAL_FINANCIAL_MEDIA_ACCOUNTS
        + MARKET_RESEARCH_ACCOUNTS
        + TRADER_INFLUENCER_ACCOUNTS
        + INSTITUTIONAL_ACCOUNTS
        + MEXICO_LATAM_FINANCIAL_ACCOUNTS
    )
)

RELIABLE_BROAD_ACCOUNTS: tuple[str, ...] = CURATED_MARKET_ACCOUNT_UNIVERSE

GLOBAL_MARKET_TERMS_EN: tuple[str, ...] = (
    "earnings",
    "revenue",
    "guidance",
    "profit",
    "loss",
    "margin",
    "stock",
    "stocks",
    "shares",
    "market",
    "markets",
    "downgrade",
    "upgrade",
    "analyst",
    "valuation",
    "rates",
    "inflation",
    "CPI",
    "central bank",
    "Fed",
    "FOMC",
    "Treasury yields",
    "geopolitical risk",
    "tariffs",
    "oil",
    "FX",
    "dollar",
    "AI",
    "chips",
    "cloud",
    "risk",
    "regulation",
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
    "bolsa",
    "mercado",
    "mercados",
    "riesgo",
    "tasas",
    "tasa de interés",
    "inflación",
    "Banxico",
    "banco central",
    "política monetaria",
    "analistas",
    "valuación",
    "regulación",
    "México",
    "Mexico",
    "peso mexicano",
    "dólar",
    "aranceles",
    "geopolítica",
)

MACRO_TERMS_EN: tuple[str, ...] = (
    "rates",
    "interest rates",
    "inflation",
    "CPI",
    "central bank",
    "monetary policy",
    "Fed",
    "FOMC",
    "Banxico",
    "Treasury yields",
    "dollar",
    "peso",
    "recession",
    "GDP",
    "geopolitical risk",
    "tariffs",
    "oil",
)

MACRO_TERMS_ES: tuple[str, ...] = (
    "tasas",
    "tasa de interés",
    "inflación",
    "Banxico",
    "política monetaria",
    "banco central",
    "peso",
    "dólar",
    "recesión",
    "PIB",
    "riesgo geopolítico",
    "aranceles",
    "petróleo",
    "México",
    "Mexico",
)

NOISE_EXCLUSION_TERMS: tuple[str, ...] = (
    "giveaway",
    "airdrop",
    "free crypto",
    "promo code",
    "onlyfans",
    "casino",
    "betting",
    "parlay",
    "coupon",
)

HIGH_NOISE_WATCHLIST_ACCOUNTS: tuple[str, ...] = (
    "WatcherGuru",
    "WhaleChart",
    "zerohedge",
)

SPANISH_STOPWORDS = {
    "que",
    "qué",
    "se",
    "dice",
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "un",
    "una",
    "como",
    "cómo",
    "va",
    "mal",
    "bien",
    "sobre",
    "preve",
    "prevé",
    "suba",
    "baje",
    "tasa",
    "tasas",
}

ENGLISH_STOPWORDS = {
    "what",
    "is",
    "are",
    "said",
    "about",
    "the",
    "a",
    "an",
    "of",
    "on",
    "for",
    "with",
    "how",
    "bad",
    "good",
    "going",
}


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
    "META": CompanyLiveQuery(
        ticker="META",
        name="Meta Platforms",
        aliases=("META", "$META", "Meta", "Facebook", "Instagram"),
        terms_en=(
            "earnings",
            "revenue",
            "advertising",
            "AI",
            "metaverse",
            "margins",
            "stock",
            "shares",
        ),
    ),
    "AMD": CompanyLiveQuery(
        ticker="AMD",
        name="Advanced Micro Devices",
        aliases=("AMD", "$AMD", "Advanced Micro Devices"),
        terms_en=("earnings", "revenue", "AI", "chips", "GPU", "data center", "stock", "shares"),
    ),
    "AVGO": CompanyLiveQuery(
        ticker="AVGO",
        name="Broadcom",
        aliases=("AVGO", "$AVGO", "Broadcom"),
        terms_en=(
            "earnings",
            "revenue",
            "AI",
            "chips",
            "semiconductor",
            "VMware",
            "stock",
            "shares",
        ),
    ),
    "INTC": CompanyLiveQuery(
        ticker="INTC",
        name="Intel",
        aliases=("INTC", "$INTC", "Intel"),
        terms_en=(
            "earnings",
            "revenue",
            "chips",
            "semiconductor",
            "foundry",
            "guidance",
            "stock",
            "shares",
        ),
    ),
    "NFLX": CompanyLiveQuery(
        ticker="NFLX",
        name="Netflix",
        aliases=("NFLX", "$NFLX", "Netflix"),
        terms_en=(
            "earnings",
            "revenue",
            "subscribers",
            "streaming",
            "advertising",
            "guidance",
            "stock",
            "shares",
        ),
    ),
    "ORCL": CompanyLiveQuery(
        ticker="ORCL",
        name="Oracle",
        aliases=("ORCL", "$ORCL", "Oracle"),
        terms_en=("earnings", "revenue", "cloud", "AI", "database", "guidance", "stock", "shares"),
    ),
    "BAC": CompanyLiveQuery(
        ticker="BAC",
        name="Bank of America",
        aliases=("BAC", "$BAC", "Bank of America", "BofA"),
        terms_en=(
            "earnings",
            "rates",
            "credit risk",
            "loan losses",
            "deposits",
            "net interest income",
            "stock",
            "shares",
        ),
    ),
    "GS": CompanyLiveQuery(
        ticker="GS",
        name="Goldman Sachs",
        aliases=("GS", "$GS", "Goldman Sachs"),
        terms_en=(
            "earnings",
            "trading revenue",
            "investment banking",
            "deals",
            "rates",
            "stock",
            "shares",
        ),
    ),
    "WMT": CompanyLiveQuery(
        ticker="WMT",
        name="Walmart",
        aliases=("WMT", "$WMT", "Walmart"),
        terms_en=(
            "earnings",
            "revenue",
            "consumer",
            "retail",
            "margins",
            "inflation",
            "stock",
            "shares",
        ),
    ),
    "DIS": CompanyLiveQuery(
        ticker="DIS",
        name="Disney",
        aliases=("DIS", "$DIS", "Disney"),
        terms_en=(
            "earnings",
            "revenue",
            "streaming",
            "parks",
            "ESPN",
            "margins",
            "stock",
            "shares",
        ),
    ),
}


def strip_accents(text: str) -> str:
    """Return lowercase text without accents for matching."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _quote_if_needed(term: str) -> str:
    """Quote terms containing spaces so X search treats them as phrases."""
    cleaned = term.strip()
    return f'"{cleaned}"' if " " in cleaned and not cleaned.startswith('"') else cleaned


def _or_group(values: tuple[str, ...] | list[str]) -> str:
    """Build a parenthesized OR group."""
    cleaned = [_quote_if_needed(str(value)) for value in values if str(value).strip()]
    return "(" + " OR ".join(cleaned) + ")"


def _truncate_accounts(accounts: tuple[str, ...], max_accounts: int) -> tuple[str, ...]:
    """Limit accounts to keep X query length below recent-search caps."""
    return accounts[:max_accounts]


def build_account_filter(
    accounts: tuple[str, ...] = RELIABLE_BROAD_ACCOUNTS,
    *,
    max_accounts: int = 8,
) -> str:
    """Build an X query filter restricted to curated accounts."""
    selected = _truncate_accounts(accounts, max_accounts)
    return "(" + " OR ".join(f"from:{account}" for account in selected) + ")"


def classify_author_reliability(author_username: str | None) -> AuthorTier:
    """Classify an X author into a reliability/context tier."""
    if not author_username:
        return "unknown"

    normalized = author_username.lower().lstrip("@")
    tiers: list[tuple[AuthorTier, tuple[str, ...]]] = [
        ("institution", INSTITUTIONAL_ACCOUNTS),
        ("financial_media", GLOBAL_FINANCIAL_MEDIA_ACCOUNTS),
        ("mexico_latam", MEXICO_LATAM_FINANCIAL_ACCOUNTS),
        ("market_research", MARKET_RESEARCH_ACCOUNTS),
        ("trader_influencer", TRADER_INFLUENCER_ACCOUNTS),
        ("high_noise_watchlist", HIGH_NOISE_WATCHLIST_ACCOUNTS),
    ]
    for tier, accounts in tiers:
        if normalized in {account.lower().lstrip("@") for account in accounts}:
            return tier
    return "unknown"


def is_curated_market_author(author_username: str | None) -> bool:
    """Return whether an author belongs to the curated market universe."""
    return classify_author_reliability(author_username) not in {"unknown", "high_noise_watchlist"}


def detect_language_hint(text: str) -> str:
    """Infer Spanish vs English from user query terms."""
    lowered = strip_accents(text)
    spanish_markers = [
        "mexico",
        "banxico",
        "tasa",
        "tasas",
        "interes",
        "inflacion",
        "suba",
        "baje",
        "que",
        "dice",
        "preve",
    ]
    return "es" if any(marker in lowered for marker in spanish_markers) else "en"


def _company_aliases(company) -> list[str]:
    """Return aliases from dataclass-style or dict-style company config."""
    if hasattr(company, "aliases"):
        return list(company.aliases)
    if isinstance(company, dict):
        return list(company.get("aliases", []))
    return []


def _company_terms(company, language: str = "en") -> list[str]:
    """Return financial terms from dataclass-style or dict-style company config."""
    if hasattr(company, "terms_en"):
        if language == "es" and hasattr(company, "terms_es"):
            return list(company.terms_es or company.terms_en)
        return list(company.terms_en)

    if isinstance(company, dict):
        if language == "es" and company.get("terms_es"):
            return list(company.get("terms_es", []))
        return list(company.get("terms_en", []))

    return []


def _company_name(company, fallback: str) -> str:
    """Return company display name from dataclass-style or dict-style config."""
    if hasattr(company, "name"):
        return str(company.name)
    if isinstance(company, dict):
        return str(company.get("name", fallback))
    return fallback


def infer_ticker_from_text(text: str) -> str | None:
    """Infer a configured ticker from user-entered text.

    Avoids false positives for one-letter tickers such as V.
    Supports dataclass-style and dict-style company configs.
    """
    normalized = text.upper().replace("$", " ")
    words = set(re.findall(r"[A-Z0-9]+", normalized))

    for ticker, company in COMPANY_QUERIES.items():
        ticker_norm = ticker.upper().strip()

        if ticker_norm in words:
            return ticker

        for alias in _company_aliases(company):
            alias_norm = str(alias).upper().replace("$", " ").strip()
            if not alias_norm:
                continue

            # One-letter symbols/aliases must match a full token only.
            if len(alias_norm) <= 2:
                if alias_norm in words:
                    return ticker
                continue

            if alias_norm in normalized:
                return ticker

    return None


def is_macro_query(text: str) -> bool:
    """Return whether the query is more macro/geopolitical than single-company."""
    lowered = strip_accents(text)
    macro_markers = tuple(strip_accents(term) for term in MACRO_TERMS_EN + MACRO_TERMS_ES)
    geopolitical_markers = (
        "war",
        "oil shock",
        "geopolitical",
        "geopolitico",
        "arancel",
        "tariff",
        "china",
        "mexico",
        "rate",
        "rates",
        "tasa",
        "tasas",
        "banxico",
        "fed",
        "fomc",
    )
    return any(marker in lowered for marker in macro_markers + geopolitical_markers)


def _exclusion_query(max_terms: int = 4) -> str:
    """Return compact negative filters for obvious non-financial spam."""
    return " ".join(
        f'-"{term}"' if " " in term else f"-{term}" for term in NOISE_EXCLUSION_TERMS[:max_terms]
    )


def _account_exclusion_query() -> str:
    """Return compact account exclusions for known high-noise watchlist accounts."""
    return " ".join(f"-from:{account}" for account in HIGH_NOISE_WATCHLIST_ACCOUNTS)


def compact_query(query: str, max_chars: int = 500) -> str:
    """Compact query to stay below X recent-search's 512-character limit."""
    query = re.sub(r"\s+", " ", query).strip()
    if len(query) <= max_chars:
        return query

    query = re.sub(r"(?:\s+-[^ ]+)+$", "", query).strip()
    if len(query) <= max_chars:
        return query

    return query[:max_chars].rsplit(" ", 1)[0]


def extract_search_terms(user_query: str, *, language: str) -> list[str]:
    """Extract useful terms from a natural-language query.

    The previous implementation used the full user sentence as an exact phrase,
    which often returned zero tweets. This function keeps entities and market
    keywords while removing generic words.
    """
    tokens = re.findall(r"[$A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+", user_query)
    stopwords = SPANISH_STOPWORDS if language == "es" else ENGLISH_STOPWORDS
    terms: list[str] = []
    for token in tokens:
        cleaned = token.strip()
        if not cleaned:
            continue
        normalized = strip_accents(cleaned).lstrip("$")
        if len(normalized) <= 2 or normalized in stopwords:
            continue
        terms.append(cleaned)

    lowered = strip_accents(user_query)
    if "mexico" in lowered or "banxico" in lowered:
        terms.extend(["México", "Mexico", "Banxico", "peso", "tasas", "inflación"])
    if "trump" in lowered:
        terms.extend(["Trump", "tariffs", "markets", "rates", "geopolitics"])

    return list(dict.fromkeys(terms))[:10]


def build_company_query(
    ticker: str,
    *,
    language: str = "en",
    reliable_accounts_only: bool = True,
    trusted_accounts_only: bool | None = None,
) -> str:
    """Build a controlled recent-search query for scheduled company ingestion."""
    normalized = ticker.upper().strip()
    if normalized not in COMPANY_QUERIES:
        raise KeyError(f"Ticker not configured for live ingestion: {ticker}")

    if trusted_accounts_only is not None:
        reliable_accounts_only = trusted_accounts_only

    company = COMPANY_QUERIES[normalized]
    aliases = _or_group(_company_aliases(company))

    if language == "es" and company.terms_es:
        terms = company.terms_es + GLOBAL_MARKET_TERMS_ES
        lang_filter = "lang:es"
    else:
        terms = company.terms_en + GLOBAL_MARKET_TERMS_EN
        lang_filter = "lang:en"

    unique_terms = tuple(dict.fromkeys(terms))[:10]
    base_query = (
        f"{aliases} {_or_group(unique_terms)} {lang_filter} -is:retweet {_exclusion_query(3)}"
    )

    if reliable_accounts_only:
        return compact_query(f"{build_account_filter()} {base_query}")

    return compact_query(f"{base_query} {_account_exclusion_query()}".strip())


def build_loose_fallback_query(user_query: str, *, language: str = "auto") -> str:
    """Build a less restrictive query for cases where the primary query returns 0."""
    detected_language = detect_language_hint(user_query) if language == "auto" else language
    ticker = infer_ticker_from_text(user_query)
    if ticker:
        company = COMPANY_QUERIES[ticker]
        values = list(company.aliases) + list(
            company.terms_es if detected_language == "es" else company.terms_en
        )
    else:
        values = extract_search_terms(user_query, language=detected_language)
        if is_macro_query(user_query):
            values.extend(
                list(MACRO_TERMS_ES[:5] if detected_language == "es" else MACRO_TERMS_EN[:5])
            )
        else:
            values.extend(
                list(
                    GLOBAL_MARKET_TERMS_ES[:5]
                    if detected_language == "es"
                    else GLOBAL_MARKET_TERMS_EN[:5]
                )
            )

    values = list(dict.fromkeys(values))[:12]
    lang_filter = "lang:es" if detected_language == "es" else "lang:en"
    return compact_query(f"{_or_group(values)} {lang_filter} -is:retweet {_exclusion_query(2)}")


def build_reliable_broad_query(
    user_query: str,
    *,
    language: str = "auto",
    max_accounts: int = 8,
    search_scope: Literal["broad_all_x", "curated_accounts"] = "broad_all_x",
) -> tuple[str, str | None, str]:
    """Build a broad but finance-constrained X query from natural language."""
    cleaned = user_query.strip()
    if not cleaned:
        raise ValueError("user_query is required")

    detected_language = detect_language_hint(cleaned) if language == "auto" else language
    ticker = infer_ticker_from_text(cleaned)

    if ticker:
        company = COMPANY_QUERIES[ticker]
        if search_scope == "curated_accounts":
            query = build_company_query(
                ticker, language=detected_language, reliable_accounts_only=True
            )
        else:
            query = build_company_query(
                ticker, language=detected_language, reliable_accounts_only=False
            )
        return query, ticker, _company_name(company, ticker)

    query_terms = extract_search_terms(cleaned, language=detected_language)
    if is_macro_query(cleaned):
        query_terms.extend(
            list(MACRO_TERMS_ES[:6] if detected_language == "es" else MACRO_TERMS_EN[:6])
        )
    else:
        query_terms.extend(
            list(
                GLOBAL_MARKET_TERMS_ES[:6]
                if detected_language == "es"
                else GLOBAL_MARKET_TERMS_EN[:6]
            )
        )
    query_terms = list(dict.fromkeys(query_terms))[:12]

    lang_filter = "lang:es" if detected_language == "es" else "lang:en"
    core_query = f"{_or_group(query_terms)} {lang_filter} -is:retweet {_exclusion_query(3)}"

    if search_scope == "curated_accounts":
        return (
            compact_query(f"{build_account_filter(max_accounts=max_accounts)} {core_query}"),
            None,
            cleaned,
        )

    return compact_query(f"{core_query} {_account_exclusion_query()}".strip()), None, cleaned


# Backward-compatible name used by older modules.
def build_broad_financial_query(
    user_query: str,
    *,
    language: str = "en",
    trusted_accounts_only: bool = True,
) -> tuple[str, str | None, str]:
    """Build a broad financial query."""
    scope = "curated_accounts" if trusted_accounts_only else "broad_all_x"
    return build_reliable_broad_query(user_query, language=language, search_scope=scope)


def rotate_ticker(tickers: list[str], now: datetime | None = None) -> str:
    """Select one ticker for the current two-hour window."""
    if not tickers:
        raise ValueError("At least one ticker is required for rotation.")

    current = now or datetime.now(UTC)
    window_index = int(current.timestamp() // (2 * 60 * 60))
    return tickers[window_index % len(tickers)].upper().strip()


# --- additive final refinements hook ---
try:
    from financial_sentiment.additive_refinements import extend_catalog_globals

    extend_catalog_globals(globals())
except Exception:
    # Catalog extension should never break the working application.
    pass
# --- end additive final refinements hook ---
