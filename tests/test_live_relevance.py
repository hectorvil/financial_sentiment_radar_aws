"""Automated tests for Financial Sentiment Radar.

The tests in this module protect important product behavior so that future refactors can be made safely."""

import pandas as pd

from financial_sentiment.live_relevance import apply_relevance_labels, fallback_relevance_labels


def test_fallback_relevance_filters_noise_terms():
    """Filters records according to business or data-quality rules.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    rows = [
        {"tweet_id": "1", "text": "NVDA earnings and AI chip demand push shares higher"},
        {"tweet_id": "2", "text": "NVDA giveaway free crypto airdrop promo"},
    ]
    labels = fallback_relevance_labels(rows, user_query="NVDA")
    assert labels[0].is_noise is False
    assert labels[1].is_noise is True


def test_apply_relevance_labels_adds_columns():
    """Implements the `test_apply_relevance_labels_adds_columns` step used by this module.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    rows = [{"tweet_id": "1", "text": "Tesla margins pressure shares"}]
    labels = fallback_relevance_labels(rows, user_query="Tesla")
    df = apply_relevance_labels(pd.DataFrame(rows), labels)
    assert {"is_noise", "relevance_score", "noise_reason"}.issubset(df.columns)
