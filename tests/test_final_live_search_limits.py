"""Automated tests for Financial Sentiment Radar.

The tests in this module protect important product behavior so that future refactors can be made safely."""

from financial_sentiment.x_api_client import normalize_max_results


def test_live_search_cap_is_25():
    """Retrieves matching records from an external service or local corpus.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    assert normalize_max_results(100) == 25
    assert normalize_max_results(25) == 25
    assert normalize_max_results(1) == 3


from financial_sentiment.live_search_service import _allocation


def test_mixed_search_allocation_respects_cap():
    """Retrieves matching records from an external service or local corpus.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    for requested in [10, 15, 20, 25]:
        broad, curated = _allocation(normalize_max_results(requested), "broad_all_x")
        assert broad + curated <= normalize_max_results(requested)
        assert broad >= 10
        assert curated in {0, 10}
