import pandas as pd

from financial_sentiment.preprocessing import clean_text, extract_tickers, prepare_tweets


def test_clean_text_removes_url_and_mentions():
    text = "@user $NVDA rallies https://example.com after strong demand"
    cleaned = clean_text(text)
    assert "http" not in cleaned
    assert "@user" not in cleaned
    assert "$NVDA" in cleaned


def test_extract_tickers_from_aliases_and_cashtags():
    tickers = extract_tickers("Apple and $NVDA lead AI sentiment; Microsoft follows.")
    assert tickers == ["AAPL", "MSFT", "NVDA"]


def test_prepare_tweets_adds_required_columns():
    raw = pd.DataFrame({"text": ["Tesla $TSLA faces margin risk"], "tweet_id": ["1"]})
    prepared = prepare_tweets(raw)
    assert prepared.loc[0, "primary_ticker"] == "TSLA"
    assert prepared.loc[0, "doc_id"] == "1"
    assert "clean_text" in prepared.columns
