from financial_sentiment.live_query_catalog import (
    build_loose_fallback_query,
    build_reliable_broad_query,
)
from financial_sentiment.x_api_client import normalize_max_results


def test_user_can_request_three_tweets():
    assert normalize_max_results(1) == 3
    assert normalize_max_results(3) == 3
    assert normalize_max_results(25) == 25
    assert normalize_max_results(99) == 25


def test_mexico_query_is_not_exact_sentence_only():
    query, ticker, name = build_reliable_broad_query(
        "Qué se dice de México?",
        language="auto",
        search_scope="broad_all_x",
    )
    assert ticker is None
    assert name == "Qué se dice de México?"
    assert "México" in query or "Mexico" in query
    assert "Banxico" in query or "tasas" in query
    assert "Qué se dice de México?" not in query
    assert len(query) <= 512


def test_loose_fallback_query_is_compact():
    query = build_loose_fallback_query("Qué se dice de México?", language="auto")
    assert "México" in query or "Mexico" in query
    assert "-is:retweet" in query
    assert len(query) <= 512
