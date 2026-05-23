"""Automated tests for Financial Sentiment Radar.

The tests in this module protect important product behavior so that future refactors can be made safely."""

import pandas as pd

from financial_sentiment.pipeline import process_tweets
from financial_sentiment.sentiment import score_sentiment


def test_score_sentiment_positive():
    """Computes a score used by ranking, sentiment, or analytics.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    result = score_sentiment("NVDA reports strong growth and record profits")
    assert result.sentiment == "positive"
    assert result.sentiment_score > 0


def test_score_sentiment_negative():
    """Computes a score used by ranking, sentiment, or analytics.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    result = score_sentiment("TSLA faces decline risk losses and volatility")
    assert result.sentiment == "negative"
    assert result.sentiment_score < 0


def test_process_tweets_end_to_end():
    """Transforms input data into a processed representation.

    Returns:
        None: The function performs side effects or updates state in place.
    """
    raw = pd.DataFrame(
        {
            "tweet_id": ["x1", "x2"],
            "text": ["$AAPL upgrade shows growth", "$TSLA downgrade and risk"],
        }
    )
    processed = process_tweets(raw)
    assert set(processed["sentiment"]) == {"positive", "negative"}
    assert "topic" in processed.columns
