"""Automated tests for Financial Sentiment Radar.

The tests in this module protect important product behavior so that future refactors can be made safely."""

from financial_sentiment.live_query_catalog import (
    CURATED_MARKET_ACCOUNT_UNIVERSE,
    TRADER_INFLUENCER_ACCOUNTS,
    build_account_filter,
    build_reliable_broad_query,
    classify_author_reliability,
    infer_ticker_from_text,
)
from financial_sentiment.x_api_client import normalize_max_results


def test_google_query_searches_broad_x_with_financial_filters():
    """Filters records according to business or data-quality rules.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    query, ticker, name = build_reliable_broad_query(
        "¿Qué se dice de Google? ¿Va mal?", language="auto"
    )
    assert ticker == "GOOGL"
    assert name == "Alphabet / Google"
    assert "Google" in query or "GOOGL" in query
    assert "(from:" not in query
    assert "-is:retweet" in query
    assert "earnings" in query or "revenue" in query
    assert len(query) <= 512


def test_curated_accounts_scope_is_available_for_conservative_searches():
    """Retrieves matching records from an external service or local corpus.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    query, ticker, _name = build_reliable_broad_query(
        "Nvidia traders AI chips",
        language="en",
        search_scope="curated_accounts",
    )
    assert ticker == "NVDA"
    assert "from:Reuters" in query
    assert "from:CNBC" in query or "from:WSJmarkets" in query
    assert "Nvidia" in query or "NVDA" in query
    assert len(query) <= 512


def test_mexico_rates_query_uses_spanish_macro_terms_without_forcing_accounts():
    """Implements the `test_mexico_rates_query_uses_spanish_macro_terms_without_forcing_accounts` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    query, ticker, name = build_reliable_broad_query(
        "¿se prevé que suba la tasa de interés en México?", language="auto"
    )
    assert ticker is None
    assert name == "¿se prevé que suba la tasa de interés en México?"
    assert "tasa" in query or "tasas" in query
    assert "lang:es" in query
    assert "-is:retweet" in query
    assert len(query) <= 512


def test_account_filter_and_tiers_include_traders_and_influencers():
    """Filters records according to business or data-quality rules.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    assert "PeterLBrandt" in TRADER_INFLUENCER_ACCOUNTS
    assert "markminervini" in TRADER_INFLUENCER_ACCOUNTS
    assert "LindaRaschke" in TRADER_INFLUENCER_ACCOUNTS
    assert "CarterBWorth" in TRADER_INFLUENCER_ACCOUNTS
    assert "elerianm" in TRADER_INFLUENCER_ACCOUNTS
    assert "Stocktwits" in CURATED_MARKET_ACCOUNT_UNIVERSE
    assert classify_author_reliability("PeterLBrandt") == "trader_influencer"
    assert classify_author_reliability("Banxico") == "institution"
    assert classify_author_reliability("Reuters") == "financial_media"
    assert classify_author_reliability("SomeRandomUser") == "unknown"
    assert "from:Reuters" in build_account_filter(max_accounts=5)


def test_infer_ticker_from_company_name():
    """Implements the `test_infer_ticker_from_company_name` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    assert infer_ticker_from_text("Tesla va mal?") == "TSLA"
    assert infer_ticker_from_text("Nvidia AI chips") == "NVDA"


def test_normalize_max_results_cap():
    """Implements the `test_normalize_max_results_cap` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    assert normalize_max_results(3) == 3
    assert normalize_max_results(25) == 25
    assert normalize_max_results(100) == 25


def test_trader_account_universe_contains_expected_handles():
    """Implements the `test_trader_account_universe_contains_expected_handles` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    from financial_sentiment.live_query_catalog import TRADER_INFLUENCER_ACCOUNTS

    assert "LizAnnSonders" in TRADER_INFLUENCER_ACCOUNTS
    assert "elerianm" in TRADER_INFLUENCER_ACCOUNTS
    assert "PeterLBrandt" in TRADER_INFLUENCER_ACCOUNTS
    assert "markminervini" in TRADER_INFLUENCER_ACCOUNTS
    assert "LindaRaschke" in TRADER_INFLUENCER_ACCOUNTS
    assert "KobeissiLetter" in TRADER_INFLUENCER_ACCOUNTS
