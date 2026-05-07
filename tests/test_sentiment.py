import pandas as pd

from financial_sentiment.pipeline import process_tweets
from financial_sentiment.sentiment import score_sentiment


def test_score_sentiment_positive():
    result = score_sentiment("NVDA reports strong growth and record profits")
    assert result.sentiment == "positive"
    assert result.sentiment_score > 0


def test_score_sentiment_negative():
    result = score_sentiment("TSLA faces decline risk losses and volatility")
    assert result.sentiment == "negative"
    assert result.sentiment_score < 0


def test_process_tweets_end_to_end():
    raw = pd.DataFrame(
        {
            "tweet_id": ["x1", "x2"],
            "text": ["$AAPL upgrade shows growth", "$TSLA downgrade and risk"],
        }
    )
    processed = process_tweets(raw)
    assert set(processed["sentiment"]) == {"positive", "negative"}
    assert "topic" in processed.columns
