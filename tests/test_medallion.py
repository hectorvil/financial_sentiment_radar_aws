import pandas as pd

from financial_sentiment.medallion import gold_sentiment_by_ticker_daily, silverize_tweets


def test_silverize_tweets_adds_medallion_columns():
    df = pd.DataFrame(
        {
            "tweet_id": ["1"],
            "text": ["$NVDA rallies after AI demand"],
            "created_at": ["2026-05-20T10:00:00Z"],
            "primary_ticker": ["NVDA"],
            "sentiment": ["positive"],
        }
    )
    silver = silverize_tweets(df, source="twitter_live", run_id="run_test")
    assert silver.loc[0, "source"] == "twitter_live"
    assert silver.loc[0, "run_id"] == "run_test"
    assert "ingestion_date" in silver.columns


def test_gold_sentiment_by_ticker_daily_counts_sentiment():
    df = pd.DataFrame(
        {
            "created_at": ["2026-05-20T10:00:00Z", "2026-05-20T11:00:00Z"],
            "primary_ticker": ["NVDA", "NVDA"],
            "sentiment": ["positive", "negative"],
            "source": ["twitter_live", "twitter_live"],
            "run_id": ["run_test", "run_test"],
        }
    )
    gold = gold_sentiment_by_ticker_daily(df)
    assert len(gold) == 1
    assert gold.loc[0, "ticker"] == "NVDA"
    assert gold.loc[0, "positive"] == 1
    assert gold.loc[0, "negative"] == 1
    assert gold.loc[0, "total"] == 2
