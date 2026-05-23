"""Automated tests for Financial Sentiment Radar.

The tests in this module protect important product behavior so that future refactors can be made safely."""

from __future__ import annotations

import pandas as pd

from financial_sentiment.finbert import FinBertClassifier, FinBertPrediction
from financial_sentiment.pipeline import process_tweets


def test_finbert_add_sentiment_interface_mock() -> None:
    """Implements the `test_finbert_add_sentiment_interface_mock` step used by this module.

    Returns:
        None: Result produced by the function.
    """
    classifier = object.__new__(FinBertClassifier)
    classifier.model_name = "mock-finbert"

    def fake_predict_texts(texts, *, batch_size=16, max_length=128):
        """Implements the `fake_predict_texts` step used by this module.

        Args:
            texts: Input value consumed by this function.
            batch_size: Input value consumed by this function.
            max_length: Input value consumed by this function.

        Returns:
            object: Result produced by the function.
        """
        return [
            FinBertPrediction(
                sentiment="positive",
                sentiment_confidence=0.9,
                positive_prob=0.9,
                neutral_prob=0.05,
                negative_prob=0.05,
            )
            for _ in texts
        ]

    classifier.predict_texts = fake_predict_texts

    df = pd.DataFrame({"clean_text": ["Nvidia revenue beats expectations"]})
    scored = classifier.add_sentiment(df, text_column="clean_text")

    expected_columns = {
        "sentiment",
        "sentiment_confidence",
        "positive_prob",
        "neutral_prob",
        "negative_prob",
        "sentiment_model",
        "sentiment_score",
    }
    assert expected_columns.issubset(scored.columns)
    assert scored.loc[0, "sentiment"] == "positive"
    assert scored.loc[0, "sentiment_model"] == "mock-finbert"


def test_pipeline_lexicon_still_works() -> None:
    """Implements the `test_pipeline_lexicon_still_works` step used by this module.

    Returns:
        None: Result produced by the function.
    """
    raw = pd.DataFrame({"text": ["Tesla stock drops on margin risk"]})

    processed = process_tweets(raw, sentiment_model="lexicon")

    assert not processed.empty
    assert processed.loc[0, "sentiment"] == "negative"
    assert processed.loc[0, "sentiment_model"] == "lexicon"
