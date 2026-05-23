"""Automated tests for Financial Sentiment Radar.

The tests in this module protect important product behavior so that future refactors can be made safely."""

from financial_sentiment.live_query_catalog import (
    build_broad_financial_query,
    infer_ticker_from_text,
)
from financial_sentiment.x_api_client import normalize_max_results


def test_broad_query_for_known_ticker_is_financial_and_not_account_restricted():
    """Implements the `test_broad_query_for_known_ticker_is_financial_and_not_account_restricted` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    query, ticker, name = build_broad_financial_query("NVDA", trusted_accounts_only=False)
    assert ticker == "NVDA"
    assert name == "Nvidia"
    assert "-is:retweet" in query
    assert "(from:" not in query
    assert "earnings" in query
    assert len(query) <= 512


def test_trusted_accounts_compatibility_mode_still_filters_accounts():
    """Filters records according to business or data-quality rules.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    query, ticker, name = build_broad_financial_query("NVDA", trusted_accounts_only=True)
    assert ticker == "NVDA"
    assert name == "Nvidia"
    assert "from:" in query
    assert "NVDA" in query


def test_infer_ticker_from_text_alias():
    """Implements the `test_infer_ticker_from_text_alias` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    assert infer_ticker_from_text("What happens with Google?") == "GOOGL"


def test_normalize_max_results_caps_at_25():
    """Implements the `test_normalize_max_results_caps_at_25` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    assert normalize_max_results(100) == 25
    assert normalize_max_results(2) == 3
