import pandas as pd

from financial_sentiment.live_relevance import apply_relevance_labels, fallback_relevance_labels


def test_fallback_relevance_filters_noise_terms():
    rows = [
        {"tweet_id": "1", "text": "NVDA earnings and AI chip demand push shares higher"},
        {"tweet_id": "2", "text": "NVDA giveaway free crypto airdrop promo"},
    ]
    labels = fallback_relevance_labels(rows, user_query="NVDA")
    assert labels[0].is_noise is False
    assert labels[1].is_noise is True


def test_apply_relevance_labels_adds_columns():
    rows = [{"tweet_id": "1", "text": "Tesla margins pressure shares"}]
    labels = fallback_relevance_labels(rows, user_query="Tesla")
    df = apply_relevance_labels(pd.DataFrame(rows), labels)
    assert {"is_noise", "relevance_score", "noise_reason"}.issubset(df.columns)
