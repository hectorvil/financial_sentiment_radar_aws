import pandas as pd

from financial_sentiment.pipeline import process_tweets
from financial_sentiment.retrieval import TweetRetriever, build_extractive_answer


def test_retriever_finds_related_tweet():
    raw = pd.DataFrame(
        {
            "tweet_id": ["1", "2"],
            "text": ["NVIDIA NVDA GPU growth is strong", "Tesla TSLA margin risk and volatility"],
        }
    )
    processed = process_tweets(raw)
    results = TweetRetriever(processed).search("NVIDIA GPU", k=1)
    assert len(results) == 1
    assert "NVIDIA" in results[0].text


def test_extractive_answer_handles_empty_results():
    answer = build_extractive_answer("anything", [])
    assert "No encontré evidencia" in answer


def test_retriever_handles_stopword_only_documents() -> None:
    df = pd.DataFrame(
        {
            "doc_id": ["1"],
            "clean_text": ["the and or"],
            "sentiment": ["neutral"],
            "tickers": [[]],
            "topic": ["general_market"],
        }
    )
    retriever = TweetRetriever(df)
    assert retriever.search("NVDA") == []
